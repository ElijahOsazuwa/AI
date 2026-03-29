"""
Utility helpers shared across the backend.
"""

import datetime


def utc_now() -> datetime.datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.datetime.now(datetime.timezone.utc)


def truncate(text: str, max_length: int = 500) -> str:
    """Safely truncate a string, appending '...' if it exceeds max_length."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def format_bytes(size: int) -> str:
    """Convert bytes to a human-readable string (KB, MB, etc.)."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
