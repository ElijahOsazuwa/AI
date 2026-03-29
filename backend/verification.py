"""
HMAC SHA-256 signature verification for GitHub webhooks.
Prevents unauthorized requests by validating the shared secret.
"""

import hashlib
import hmac
import logging

import structlog

logger = structlog.get_logger(__name__)


def verify_github_signature(payload_body: bytes, signature_header: str | None, secret: str) -> bool:
    """
    Verify the HMAC-SHA256 signature sent by GitHub.

    Args:
        payload_body: Raw request body bytes — must be read BEFORE any JSON parsing
        signature_header: Value of X-Hub-Signature-256 header (e.g. "sha256=abc123...")
        secret: The shared webhook secret from GITHUB_WEBHOOK_SECRET env var

    Returns:
        True if signature is valid, False otherwise
    """
    if not signature_header:
        logger.warning("webhook_signature_missing", reason="No X-Hub-Signature-256 header present")
        return False

    # Strip the "sha256=" prefix that GitHub prepends to the signature
    if not signature_header.startswith("sha256="):
        logger.warning("webhook_signature_malformed", header=signature_header)
        return False

    received_signature = signature_header[len("sha256="):]

    # Compute the expected HMAC-SHA256 digest using the shared secret
    expected_signature = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Use compare_digest to prevent timing attacks — NOT ==
    is_valid = hmac.compare_digest(expected_signature, received_signature)

    if not is_valid:
        logger.warning(
            "webhook_signature_invalid",
            expected_prefix=expected_signature[:8] + "...",
            received_prefix=received_signature[:8] + "...",
        )

    return is_valid
