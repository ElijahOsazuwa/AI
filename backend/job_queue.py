"""
In-memory async job queue for decoupling webhook receipt from review processing.
Jobs are pushed immediately on webhook receipt so GitHub gets a fast 200 response.

Uses asyncio.Queue instead of Redis — zero external dependencies.
State is lost on restart, but that's fine for a local dev tool.

Named job_queue.py (not queue.py) to avoid shadowing Python's built-in queue module.
"""

import asyncio
import time
from collections import defaultdict

import structlog

logger = structlog.get_logger(__name__)

RATE_LIMIT_MAX = 10  # Max 10 webhook events per minute per repository
RATE_LIMIT_WINDOW = 60  # 60 second window

# In-memory job queue (replaces Redis)
_job_queue: asyncio.Queue = asyncio.Queue()

# In-memory failed jobs list (replaces Redis dead-letter queue)
_failed_jobs: list[dict] = []

# In-memory rate limit counters: repo_name -> list of timestamps
_rate_counters: dict[str, list[float]] = defaultdict(list)


async def check_rate_limit(repo_full_name: str) -> tuple[bool, int]:
    """
    Check if a repo has exceeded the webhook rate limit.
    Returns (is_allowed, retry_after_seconds).
    Uses a sliding window of timestamps in memory.
    """
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW

    # Prune old entries outside the window
    _rate_counters[repo_full_name] = [
        ts for ts in _rate_counters[repo_full_name] if ts > window_start
    ]

    if len(_rate_counters[repo_full_name]) >= RATE_LIMIT_MAX:
        # Calculate how long until the oldest entry expires
        oldest = _rate_counters[repo_full_name][0]
        retry_after = max(int(oldest + RATE_LIMIT_WINDOW - now), 1)
        logger.warning(
            "rate_limit_exceeded",
            repo=repo_full_name,
            count=len(_rate_counters[repo_full_name]),
            retry_after=retry_after,
        )
        return False, retry_after

    _rate_counters[repo_full_name].append(now)
    return True, 0


async def enqueue_job(job_data: dict) -> None:
    """
    Push a review job onto the in-memory queue.
    Job data should include: repo, pr_number, diff_url, commit_sha, pr_event_id, etc.
    """
    job_data["queued_at"] = time.time()
    await _job_queue.put(job_data)
    logger.info("job_enqueued", repo=job_data.get("repo"), pr=job_data.get("pr_number"))


async def dequeue_job() -> dict | None:
    """
    Pop the next job from the queue. Returns None after a 5-second timeout.
    """
    try:
        return await asyncio.wait_for(_job_queue.get(), timeout=5.0)
    except asyncio.TimeoutError:
        return None


async def push_failed_job(job_data: dict, error: str) -> None:
    """
    Move a failed job to the dead-letter list for later inspection.
    Preserves the original job data plus the error message.
    """
    job_data["error"] = error
    job_data["failed_at"] = time.time()
    _failed_jobs.append(job_data)
    logger.error("job_failed", repo=job_data.get("repo"), pr=job_data.get("pr_number"), error=error)
