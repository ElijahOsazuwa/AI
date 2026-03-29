"""
Background worker that drains the in-memory job queue and processes review jobs.
Runs as a background task inside the FastAPI process (shared asyncio event loop).
"""

import asyncio
import datetime

import structlog

from database import async_session
from models import Review, ReviewStatus
from ollama_client import review_diff
from github_client import fetch_pr_diff, post_review_comment, format_review_as_markdown
from job_queue import dequeue_job, push_failed_job

logger = structlog.get_logger(__name__)


async def process_job(job: dict) -> None:
    """
    Process a single review job end-to-end:
    1. Fetch the PR diff from GitHub
    2. Send it to Ollama for AI review
    3. Store the result in the database
    4. Post the review comment back to GitHub
    """
    repo = job["repo"]
    pr_number = job["pr_number"]
    commit_sha = job["commit_sha"]
    pr_event_id = job.get("pr_event_id")
    pr_title = job.get("pr_title", "")

    # Parse owner/repo from the full name (e.g. "octocat/hello-world")
    owner, repo_name = repo.split("/", 1)

    logger.info("job_processing_start", repo=repo, pr=pr_number, commit=commit_sha[:8])

    # Create the review record as "processing"
    async with async_session() as session:
        review = Review(
            pr_event_id=pr_event_id or 0,
            repo_full_name=repo,
            pr_number=pr_number,
            pr_title=pr_title,
            commit_sha=commit_sha,
            status=ReviewStatus.processing,
        )
        session.add(review)
        await session.commit()
        await session.refresh(review)
        review_id = review.id

    try:
        # Step 1: Fetch the diff from GitHub
        logger.info("fetching_diff", repo=repo, pr=pr_number)
        diff_text = await fetch_pr_diff(owner, repo_name, pr_number)

        if not diff_text.strip():
            logger.warning("empty_diff", repo=repo, pr=pr_number)
            diff_text = "(No file changes found in this PR)"

        # Step 2: Send diff to Ollama for review
        logger.info("calling_ollama", repo=repo, pr=pr_number, diff_length=len(diff_text))
        review_result = await review_diff(diff_text)

        # Step 3: Store the result in the database
        async with async_session() as session:
            review = await session.get(Review, review_id)
            review.status = ReviewStatus.done
            review.response_json = review_result
            review.summary = review_result.get("summary", "")
            review.approved = review_result.get("approved", False)
            review.completed_at = datetime.datetime.now(datetime.timezone.utc)
            await session.commit()

        logger.info("review_stored", repo=repo, pr=pr_number, review_id=review_id)

        # Step 4: Post review comment back to GitHub
        comment_body = format_review_as_markdown(review_result)
        await post_review_comment(owner, repo_name, pr_number, commit_sha, comment_body)
        logger.info("job_completed", repo=repo, pr=pr_number, review_id=review_id)

    except Exception as e:
        # Mark the review as failed in the DB
        logger.error("job_processing_failed", repo=repo, pr=pr_number, error=str(e))
        try:
            async with async_session() as session:
                review = await session.get(Review, review_id)
                if review:
                    review.status = ReviewStatus.failed
                    review.error_message = str(e)[:1000]
                    review.completed_at = datetime.datetime.now(datetime.timezone.utc)
                    await session.commit()
        except Exception as db_err:
            logger.error("failed_to_update_review_status", error=str(db_err))

        # Push to dead-letter queue for later inspection
        await push_failed_job(job, str(e))


async def run_worker() -> None:
    """Main worker loop — continuously drains the in-memory job queue."""
    logger.info("worker_starting")
    logger.info("worker_ready", message="Listening for jobs on in-memory queue")

    try:
        while True:
            try:
                job = await dequeue_job()
                if job is None:
                    # No job available — timeout expired, loop back
                    continue
                await process_job(job)
            except asyncio.CancelledError:
                # Raised when the FastAPI app shuts down — exit cleanly
                logger.info("worker_shutting_down")
                raise
            except Exception as e:
                # Catch-all so the worker never crashes on unexpected errors
                logger.error("worker_unexpected_error", error=str(e))
                await asyncio.sleep(2)
    except asyncio.CancelledError:
        logger.info("worker_stopped")
