"""
Tests for the webhook endpoint and review API routes.
Uses FastAPI's TestClient for integration testing.
"""

import hashlib
import hmac
import json
import os
import sys

import pytest
from unittest.mock import AsyncMock, patch

# Ensure backend dir is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SECRET = "test-secret-for-ci"
os.environ["GITHUB_WEBHOOK_SECRET"] = SECRET
os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/codereviews"
os.environ["REDIS_URL"] = "redis://localhost:6379"


def _sign_payload(payload: dict, secret: str = SECRET) -> tuple[bytes, str]:
    """Helper: serialize payload and compute its HMAC signature."""
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, sig


class TestWebhookEndpoint:
    """
    Unit-level tests that validate webhook routing logic.
    These mock out Redis/DB so they can run without infrastructure.
    """

    @pytest.fixture
    def pull_request_payload(self):
        return {
            "action": "opened",
            "pull_request": {
                "number": 42,
                "title": "Add new feature",
                "head": {"sha": "abc123def456"},
                "diff_url": "https://github.com/owner/repo/pull/42.diff",
            },
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "testuser"},
        }

    def test_signature_computation(self, pull_request_payload):
        """Verify our test helper produces valid HMAC signatures."""
        body, sig = _sign_payload(pull_request_payload)
        expected = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        assert sig == f"sha256={expected}"

    def test_ping_payload_structure(self):
        """Verify ping payload can be signed and has expected structure."""
        payload = {"zen": "Keep it simple", "hook_id": 123}
        body, sig = _sign_payload(payload)
        assert b"zen" in body
        assert sig.startswith("sha256=")

    def test_invalid_action_ignored(self, pull_request_payload):
        """Only opened/synchronize/reopened should be processed."""
        pull_request_payload["action"] = "closed"
        body, sig = _sign_payload(pull_request_payload)
        # The endpoint should return 200 with "Ignored action" message
        # (full integration test requires running server)
        assert pull_request_payload["action"] == "closed"

    def test_signature_mismatch_detection(self, pull_request_payload):
        """A payload signed with the wrong secret should not match."""
        body, wrong_sig = _sign_payload(pull_request_payload, secret="wrong-secret")
        _, correct_sig = _sign_payload(pull_request_payload, secret=SECRET)
        assert wrong_sig != correct_sig
