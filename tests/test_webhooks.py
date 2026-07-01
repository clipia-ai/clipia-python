"""Tests for webhook signature verification (no network)."""

from __future__ import annotations

import hashlib
import hmac
import time

from clipia.webhooks import verify_signature

SECRET = "whsec_test_secret"


def _sign(secret: str, timestamp: int, body: str) -> str:
    signed = f"{timestamp}.{body}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def test_verify_valid_signature() -> None:
    ts = int(time.time())
    body = '{"request_id":"abc","status":"OK"}'
    sig = _sign(SECRET, ts, body)
    headers = {"X-Clipia-Signature": f"t={ts},v1={sig}"}
    assert verify_signature(SECRET, headers, body) is True


def test_verify_valid_signature_with_bytes_body() -> None:
    ts = int(time.time())
    body = '{"x":1}'
    sig = _sign(SECRET, ts, body)
    headers = {"x-clipia-signature": f"t={ts},v1={sig}"}
    assert verify_signature(SECRET, headers, body.encode("utf-8")) is True


def test_verify_invalid_signature() -> None:
    ts = int(time.time())
    body = '{"x":1}'
    headers = {"X-Clipia-Signature": f"t={ts},v1=deadbeef"}
    assert verify_signature(SECRET, headers, body) is False


def test_verify_wrong_secret() -> None:
    ts = int(time.time())
    body = '{"x":1}'
    sig = _sign("other_secret", ts, body)
    headers = {"X-Clipia-Signature": f"t={ts},v1={sig}"}
    assert verify_signature(SECRET, headers, body) is False


def test_verify_expired_timestamp() -> None:
    ts = int(time.time()) - 10_000  # well outside the 300s window
    body = '{"x":1}'
    sig = _sign(SECRET, ts, body)
    headers = {"X-Clipia-Signature": f"t={ts},v1={sig}"}
    assert verify_signature(SECRET, headers, body) is False


def test_verify_future_timestamp_outside_tolerance() -> None:
    ts = int(time.time()) + 10_000
    body = '{"x":1}'
    sig = _sign(SECRET, ts, body)
    headers = {"X-Clipia-Signature": f"t={ts},v1={sig}"}
    assert verify_signature(SECRET, headers, body) is False


def test_verify_custom_tolerance_allows_skew() -> None:
    ts = int(time.time()) - 250
    body = '{"x":1}'
    sig = _sign(SECRET, ts, body)
    headers = {"X-Clipia-Signature": f"t={ts},v1={sig}"}
    # Default 300s window passes; a tight 60s window rejects.
    assert verify_signature(SECRET, headers, body) is True
    assert verify_signature(SECRET, headers, body, tolerance_seconds=60) is False


def test_verify_missing_header() -> None:
    assert verify_signature(SECRET, {}, "{}") is False


def test_verify_malformed_header() -> None:
    headers = {"X-Clipia-Signature": "garbage-without-parts"}
    assert verify_signature(SECRET, headers, "{}") is False


def test_verify_empty_secret() -> None:
    ts = int(time.time())
    headers = {"X-Clipia-Signature": f"t={ts},v1=abc"}
    assert verify_signature("", headers, "{}") is False


def test_verify_ignores_standalone_timestamp_header() -> None:
    # The timestamp MUST come from the signed "t=" field; a standalone
    # X-Clipia-Timestamp header is not covered by the HMAC and must NOT be
    # used as a fallback (would allow unauditable timestamp spoofing).
    ts = int(time.time())
    body = '{"x":1}'
    sig = _sign(SECRET, ts, body)
    headers = {
        # Signature header carries a valid v1 but NO t= field.
        "X-Clipia-Signature": f"v1={sig}",
        "X-Clipia-Timestamp": str(ts),
    }
    assert verify_signature(SECRET, headers, body) is False


def test_verify_non_utf8_body_returns_false_not_raises() -> None:
    # A non-UTF-8 body must yield False (fail-closed), never raise
    # UnicodeDecodeError — the docstring promises a bool return.
    ts = int(time.time())
    bad_body = b"\xff\xfe\x00bad-bytes"  # invalid UTF-8
    # Sign over *some* valid string so only the body decode can fail.
    sig = _sign(SECRET, ts, "{}")
    headers = {"X-Clipia-Signature": f"t={ts},v1={sig}"}
    result = verify_signature(SECRET, headers, bad_body)
    assert result is False
    assert isinstance(result, bool)


def test_verify_always_returns_bool_on_garbage_headers() -> None:
    # Even a wildly malformed headers mapping must return a bool, not raise.
    class Weird:
        def __str__(self) -> str:
            return "x-clipia-signature"

    headers = {Weird(): "t=oops,v1=zz"}
    result = verify_signature(SECRET, headers, b"\xff\xfe")
    assert result is False
    assert isinstance(result, bool)


def test_verify_uses_now_override() -> None:
    ts = 1_717_243_200
    body = '{"request_id":"abc"}'
    sig = _sign(SECRET, ts, body)
    headers = {"X-Clipia-Signature": f"t={ts},v1={sig}"}
    # "now" exactly at the timestamp -> within tolerance.
    assert verify_signature(SECRET, headers, body, now=float(ts)) is True
    # "now" 301s later -> just outside the default window.
    assert verify_signature(SECRET, headers, body, now=float(ts + 301)) is False
