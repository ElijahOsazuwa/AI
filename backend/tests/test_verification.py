"""
Tests for HMAC SHA-256 signature verification logic.
Ensures webhooks are properly validated and timing-attack-safe.
"""

import hashlib
import hmac

import pytest

from verification import verify_github_signature


SECRET = "test-webhook-secret-123"


def _make_signature(payload: bytes, secret: str) -> str:
    """Helper to generate a valid GitHub-style HMAC signature."""
    digest = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


class TestVerifyGithubSignature:
    def test_valid_signature(self):
        """A correctly signed payload should pass verification."""
        payload = b'{"action": "opened"}'
        sig = _make_signature(payload, SECRET)
        assert verify_github_signature(payload, sig, SECRET) is True

    def test_invalid_signature(self):
        """A tampered signature should fail verification."""
        payload = b'{"action": "opened"}'
        assert verify_github_signature(payload, "sha256=deadbeef", SECRET) is False

    def test_missing_signature_header(self):
        """A missing header should fail immediately."""
        payload = b'{"action": "opened"}'
        assert verify_github_signature(payload, None, SECRET) is False

    def test_wrong_prefix(self):
        """A signature without the sha256= prefix should fail."""
        payload = b'{"action": "opened"}'
        digest = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_github_signature(payload, digest, SECRET) is False

    def test_wrong_secret(self):
        """A signature computed with a different secret should fail."""
        payload = b'{"action": "opened"}'
        sig = _make_signature(payload, "wrong-secret")
        assert verify_github_signature(payload, sig, SECRET) is False

    def test_empty_payload(self):
        """An empty payload with correct signature should still pass."""
        payload = b""
        sig = _make_signature(payload, SECRET)
        assert verify_github_signature(payload, sig, SECRET) is True

    def test_modified_payload(self):
        """Changing the payload after signing should fail verification."""
        original = b'{"action": "opened"}'
        sig = _make_signature(original, SECRET)
        modified = b'{"action": "closed"}'
        assert verify_github_signature(modified, sig, SECRET) is False
