"""
FastAPI application entry point.
Handles webhook ingestion, health checks, and review API endpoints.
"""

import os
import sys

# Ensure the backend directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env BEFORE any local imports — they read env vars at module level
from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import FastAPI, Request, Response, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, init_db, check_db_health
from models import PREvent, Review, ReviewStatus
from verification import verify_github_signature
from job_queue import enqueue_job, check_rate_limit
from ollama_client import check_ollama_health

# Configure structlog for consistent, parseable logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger(__name__)

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup; run background worker; clean up on shutdown."""
    import asyncio
    from worker import run_worker

    logger.info("app_starting")
    await init_db()

    # Start the background worker in the same event loop (in-memory queue)
    worker_task = asyncio.create_task(run_worker())
    logger.info("app_ready", message="Backend + worker running in same process")
    yield
    # Cancel the worker on shutdown
    worker_task.cancel()
    logger.info("app_shutting_down")


app = FastAPI(
    title="AI Code Reviewer",
    description="GitHub webhook service with Ollama-powered code review",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow frontend to call the API from a different origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Internal tool — open CORS is acceptable
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health Check ────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    """Aggregate health status of all dependencies for monitoring."""
    db_ok = await check_db_health()
    ollama_status = await check_ollama_health()

    all_healthy = db_ok and ollama_status.get("status") == "ok"

    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={
            "status": "healthy" if all_healthy else "degraded",
            "database": "ok" if db_ok else "error",
            "queue": "ok (in-memory)",
            "ollama": ollama_status,
        },
    )


# ─── Webhook Endpoint ───────────────────────────────────────────────────────


@app.post("/webhook")
async def github_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Receive GitHub pull_request webhook events.
    1. Read raw body and verify HMAC signature
    2. Check rate limit per repository
    3. Return 200 immediately so GitHub doesn't timeout
    4. Queue the job for async processing by the worker
    """
    # Read the RAW body bytes BEFORE any JSON parsing — critical for HMAC
    raw_body = await request.body()

    # Verify the HMAC-SHA256 signature
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_github_signature(raw_body, signature, GITHUB_WEBHOOK_SECRET):
        logger.warning("webhook_rejected", reason="invalid_signature", ip=request.client.host)
        return JSONResponse(status_code=401, content={"error": "Invalid signature"})

    # Parse the JSON payload after verification succeeds
    try:
        payload = await request.json()
    except Exception:
        logger.error("webhook_invalid_json")
        return JSONResponse(status_code=400, content={"error": "Invalid JSON payload"})

    event_type = request.headers.get("X-GitHub-Event", "")
    logger.info("webhook_received", github_event=event_type)

    # Handle GitHub's initial ping event when webhook is first registered
    if event_type == "ping":
        logger.info("webhook_ping_received")
        return JSONResponse(status_code=200, content={"message": "pong"})

    # Only process pull_request events
    if event_type != "pull_request":
        logger.info("webhook_ignored", github_event=event_type, reason="not a pull_request event")
        return JSONResponse(status_code=200, content={"message": f"Ignored event: {event_type}"})

    # Only review on opened or synchronized (new commits pushed) actions
    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        logger.info("webhook_action_ignored", action=action)
        return JSONResponse(status_code=200, content={"message": f"Ignored action: {action}"})

    pr = payload.get("pull_request", {})
    repo_full_name = payload.get("repository", {}).get("full_name", "")
    pr_number = pr.get("number", 0)
    commit_sha = pr.get("head", {}).get("sha", "")
    diff_url = pr.get("diff_url", "")
    sender = payload.get("sender", {}).get("login", "")
    pr_title = pr.get("title", "")

    logger.info(
        "webhook_verified",
        repo=repo_full_name,
        pr=pr_number,
        action=action,
        sender=sender,
    )

    # Rate limiting — max 10 events per minute per repo
    allowed, retry_after = await check_rate_limit(repo_full_name)
    if not allowed:
        logger.warning("webhook_rate_limited", repo=repo_full_name)
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={"error": "Rate limit exceeded", "retry_after": retry_after},
        )

    # Persist the webhook event in the database
    try:
        pr_event = PREvent(
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            action=action,
            sender=sender,
            commit_sha=commit_sha,
            diff_url=diff_url,
            pr_title=pr_title,
        )
        db.add(pr_event)
        await db.flush()  # Get the auto-generated ID without committing yet
        pr_event_id = pr_event.id
    except Exception as e:
        logger.error("webhook_db_save_failed", error=str(e))
        # Still queue the job even if DB insert fails — review is more important
        pr_event_id = None

    # Queue the review job for the background worker
    try:
        await enqueue_job({
            "repo": repo_full_name,
            "pr_number": pr_number,
            "diff_url": diff_url,
            "commit_sha": commit_sha,
            "pr_event_id": pr_event_id,
            "pr_title": pr_title,
            "action": action,
            "sender": sender,
        })
        logger.info("webhook_queued", repo=repo_full_name, pr=pr_number)
    except Exception as e:
        logger.error("webhook_queue_failed", error=str(e))
        return JSONResponse(status_code=500, content={"error": "Failed to queue review job"})

    # Return 200 immediately — GitHub requires a response within 10 seconds
    return JSONResponse(
        status_code=200,
        content={"message": "Webhook received and queued", "pr_event_id": pr_event_id},
    )


# ─── Reviews API (for frontend dashboard) ───────────────────────────────────


@app.get("/reviews")
async def list_reviews(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Paginated list of reviews for the frontend dashboard."""
    try:
        # Count total reviews for pagination metadata
        count_result = await db.execute(select(func.count(Review.id)))
        total = count_result.scalar()

        # Fetch reviews ordered by most recent first
        result = await db.execute(
            select(Review)
            .order_by(desc(Review.created_at))
            .limit(limit)
            .offset(offset)
        )
        reviews = result.scalars().all()

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "reviews": [
                {
                    "id": r.id,
                    "repo_full_name": r.repo_full_name,
                    "pr_number": r.pr_number,
                    "pr_title": r.pr_title,
                    "commit_sha": r.commit_sha,
                    "status": r.status.value,
                    "summary": r.summary,
                    "approved": r.approved,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                }
                for r in reviews
            ],
        }
    except Exception as e:
        logger.error("reviews_list_failed", error=str(e))
        return JSONResponse(status_code=500, content={"error": "Failed to fetch reviews"})


@app.get("/reviews/{review_id}")
async def get_review(review_id: int, db: AsyncSession = Depends(get_db)):
    """Single review detail — includes the full Ollama response JSON."""
    try:
        review = await db.get(Review, review_id)
        if not review:
            return JSONResponse(status_code=404, content={"error": "Review not found"})

        return {
            "id": review.id,
            "repo_full_name": review.repo_full_name,
            "pr_number": review.pr_number,
            "pr_title": review.pr_title,
            "commit_sha": review.commit_sha,
            "status": review.status.value,
            "summary": review.summary,
            "approved": review.approved,
            "response_json": review.response_json,
            "error_message": review.error_message,
            "created_at": review.created_at.isoformat() if review.created_at else None,
            "completed_at": review.completed_at.isoformat() if review.completed_at else None,
        }
    except Exception as e:
        logger.error("review_detail_failed", error=str(e), review_id=review_id)
        return JSONResponse(status_code=500, content={"error": "Failed to fetch review"})
