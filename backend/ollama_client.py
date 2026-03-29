"""
Ollama API wrapper for local LLM code review via the /api/chat endpoint.
Includes retry logic with exponential backoff for resilience.
"""

import asyncio
import json
import os
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "codellama")
# 120s timeout because local models can be slow on consumer hardware
OLLAMA_TIMEOUT = 120.0
MAX_RETRIES = 3

# System prompt instructs the LLM to return structured JSON for easy parsing
SYSTEM_PROMPT = (
    "You are a senior software engineer doing a pull request code review. "
    "Analyse the provided git diff and respond in this exact JSON format: "
    '{"summary": "one sentence describing the change", '
    '"issues": [{"severity": "high|medium|low", "line": <int>, "message": "<string>"}], '
    '"suggestions": ["<string>"], '
    '"approved": true|false} '
    "Focus on: security vulnerabilities, logic errors, performance issues, "
    "missing error handling. Be concise. Return only valid JSON, no markdown."
)


async def check_ollama_health() -> dict:
    """Check if Ollama is reachable and which models are available."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            return {"status": "ok", "models": models}
    except Exception as e:
        logger.error("ollama_health_check_failed", error=str(e))
        return {"status": "error", "error": str(e)}


async def _try_model(client: httpx.AsyncClient, model: str, diff_text: str) -> Optional[dict]:
    """Attempt a chat completion with a specific model. Returns None on failure."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Review this diff:\n\n{diff_text}"},
        ],
        "stream": False,  # We want the full response at once for JSON parsing
    }

    resp = await client.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()

    data = resp.json()
    content = data.get("message", {}).get("content", "")

    # Strip markdown code fences if the model wraps its JSON output
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    content = content.strip()

    return json.loads(content)


async def review_diff(diff_text: str) -> dict:
    """
    Send a PR diff to Ollama for AI code review.
    Retries up to MAX_RETRIES times with exponential backoff.
    Falls back from codellama to llama3 if the primary model is unavailable.
    """
    models_to_try = [OLLAMA_MODEL]
    # Add llama3 as fallback if the primary model is different
    if OLLAMA_MODEL != "llama3":
        models_to_try.append("llama3")

    last_error = None

    async with httpx.AsyncClient() as client:
        for model in models_to_try:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    logger.info(
                        "ollama_request_start",
                        model=model,
                        attempt=attempt,
                        diff_length=len(diff_text),
                    )
                    result = await _try_model(client, model, diff_text)
                    if result is not None:
                        logger.info("ollama_request_success", model=model, attempt=attempt)
                        return result
                except httpx.HTTPStatusError as e:
                    last_error = e
                    # 404 means model not found — skip retries and try fallback
                    if e.response.status_code == 404:
                        logger.warning("ollama_model_not_found", model=model)
                        break
                    logger.warning(
                        "ollama_request_failed",
                        model=model,
                        attempt=attempt,
                        status=e.response.status_code,
                    )
                except (httpx.RequestError, json.JSONDecodeError) as e:
                    last_error = e
                    logger.warning(
                        "ollama_request_error",
                        model=model,
                        attempt=attempt,
                        error=str(e),
                    )

                if attempt < MAX_RETRIES:
                    # Exponential backoff: 2s, 4s between retries
                    wait = 2 ** attempt
                    logger.info("ollama_retry_wait", seconds=wait)
                    await asyncio.sleep(wait)

    # All models and retries exhausted
    raise RuntimeError(f"Ollama review failed after all retries: {last_error}")
