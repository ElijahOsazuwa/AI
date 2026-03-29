"""
SQLAlchemy ORM models for storing webhook events and AI review results.
"""

import datetime
import enum
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
    Boolean,
    JSON,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ReviewStatus(str, enum.Enum):
    """Tracks the lifecycle of a review job through the queue."""
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class PREvent(Base):
    """
    Records every incoming pull_request webhook event.
    Kept separate from Review so we can track events even if review fails.
    """
    __tablename__ = "pr_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # opened, synchronize, etc.
    sender: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    diff_url: Mapped[str] = mapped_column(Text, nullable=False)
    pr_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    received_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Review(Base):
    """
    Stores the AI-generated code review result for a PR.
    The response_json column holds the raw Ollama output parsed as JSON.
    """
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pr_event_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pr_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus), default=ReviewStatus.pending, nullable=False
    )
    # Full Ollama response stored as JSON for flexible querying
    response_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
