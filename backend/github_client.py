"""
GitHub REST API client for fetching PR diffs and posting review comments.
Uses httpx async client with Bearer token auth.
"""

import asyncio
import os
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")


def _auth_headers() -> dict:
    """Build auth headers — separate function so token is read at call time, not import time."""
    return {
        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN', GITHUB_TOKEN)}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _handle_rate_limit(response: httpx.Response) -> None:
    """
    If GitHub returns 403 or 429, respect the x-ratelimit-reset header
    by sleeping until the reset time. Prevents hammering the API.
    """
    if response.status_code in (403, 429):
        reset_timestamp = response.headers.get("x-ratelimit-reset")
        if reset_timestamp:
            import time
            wait_seconds = max(int(reset_timestamp) - int(time.time()), 1)
            logger.warning("github_rate_limited", wait_seconds=wait_seconds)
            await asyncio.sleep(min(wait_seconds, 60))  # Cap wait at 60s to avoid infinite sleep


async def fetch_pr_diff(owner: str, repo: str, pull_number: int) -> str:
    """
    Fetch the file-level diff for a pull request.
    Returns a concatenated string of all file patches.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}/files"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=_auth_headers())

            # Handle GitHub rate limiting before raising for status
            if response.status_code in (403, 429):
                await _handle_rate_limit(response)
                # Retry once after waiting
                response = await client.get(url, headers=_auth_headers())

            response.raise_for_status()
            files = response.json()

            # Combine all file patches into one diff string for the LLM
            diff_parts = []
            for f in files:
                filename = f.get("filename", "unknown")
                patch = f.get("patch", "")
                if patch:
                    diff_parts.append(f"--- {filename} ---\n{patch}")

            full_diff = "\n\n".join(diff_parts)
            logger.info("github_diff_fetched", owner=owner, repo=repo, pr=pull_number, files=len(files))
            return full_diff

    except httpx.HTTPStatusError as e:
        logger.error("github_diff_fetch_failed", status=e.response.status_code, url=url)
        raise
    except httpx.RequestError as e:
        logger.error("github_diff_request_error", error=str(e), url=url)
        raise


async def post_review_comment(
    owner: str,
    repo: str,
    pull_number: int,
    commit_sha: str,
    body: str,
    event: str = "COMMENT",
) -> Optional[dict]:
    """
    Post a review comment on a GitHub pull request.
    event can be: COMMENT, APPROVE, or REQUEST_CHANGES.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
    payload = {
        "commit_id": commit_sha,
        "body": body,
        "event": event,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=_auth_headers(), json=payload)

            if response.status_code in (403, 429):
                await _handle_rate_limit(response)
                response = await client.post(url, headers=_auth_headers(), json=payload)

            response.raise_for_status()
            logger.info(
                "github_review_posted",
                owner=owner,
                repo=repo,
                pr=pull_number,
                event=event,
            )
            return response.json()

    except httpx.HTTPStatusError as e:
        logger.error("github_review_post_failed", status=e.response.status_code, url=url)
        raise
    except httpx.RequestError as e:
        logger.error("github_review_request_error", error=str(e), url=url)
        raise


def format_review_as_markdown(review_data: dict) -> str:
    """Convert the structured Ollama JSON response into a readable GitHub comment."""
    parts = []

    # Header with approval status
    approved = review_data.get("approved", False)
    status_emoji = "✅" if approved else "⚠️"
    parts.append(f"## {status_emoji} AI Code Review\n")

    # Summary
    summary = review_data.get("summary", "No summary provided.")
    parts.append(f"**Summary:** {summary}\n")

    # Issues
    issues = review_data.get("issues", [])
    if issues:
        parts.append("### Issues Found\n")
        severity_icons = {"high": "🔴", "medium": "🟡", "low": "🔵"}
        for issue in issues:
            sev = issue.get("severity", "low")
            icon = severity_icons.get(sev, "⚪")
            line = issue.get("line", "?")
            msg = issue.get("message", "")
            parts.append(f"- {icon} **{sev.upper()}** (line {line}): {msg}")
        parts.append("")

    # Suggestions
    suggestions = review_data.get("suggestions", [])
    if suggestions:
        parts.append("### Suggestions\n")
        for s in suggestions:
            parts.append(f"- {s}")
        parts.append("")

    parts.append("\n---\n*Generated by AI Code Reviewer (Ollama)*")
    return "\n".join(parts)
