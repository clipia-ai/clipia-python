"""Webhook signature verification for Clipia delivery callbacks.

Each delivery is signed with HMAC-SHA256. The signature header has the form::

    X-Clipia-Signature: t=<unix_ts>,v1=<hex_hmac>

where the signed payload is ``"{t}.{raw_body}"`` and the secret is the
webhook signing secret from your Clipia dashboard. Verification is
constant-time (``hmac.compare_digest``) and enforces a freshness window to
reject replayed deliveries.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Mapping, Optional, Union

SIGNATURE_HEADER = "x-clipia-signature"
TIMESTAMP_HEADER = "x-clipia-timestamp"
DEFAULT_TOLERANCE_SECONDS = 300


def _lower_keyed(headers: Mapping[str, str]) -> Mapping[str, str]:
    """Return a case-insensitive view of header names."""
    return {str(k).lower(): v for k, v in headers.items()}


def _parse_signature(raw: str) -> dict:
    """Parse ``t=...,v1=...`` into a dict. Tolerant of extra fields/spaces."""
    parts: dict = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        parts[key.strip()] = value.strip()
    return parts


def _compute_signature(secret: str, timestamp: str, body: str) -> str:
    signed = f"{timestamp}.{body}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def verify_signature(
    secret: str,
    headers: Mapping[str, str],
    body: Union[str, bytes],
    *,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """Verify a Clipia webhook delivery.

    Args:
        secret: the webhook signing secret from your dashboard.
        headers: the incoming request headers (case-insensitive lookup).
        body: the **raw** request body (string or bytes) exactly as received.
        tolerance_seconds: max allowed clock skew between ``t`` and now.
        now: override the current unix time (testing).

    Returns:
        ``True`` only when the signature matches AND the timestamp is within
        ``tolerance_seconds``. Never raises on malformed input; returns
        ``False`` instead so callers can safely reject.
    """
    if not secret:
        return False

    lowered = _lower_keyed(headers)
    raw_sig = lowered.get(SIGNATURE_HEADER)
    if not raw_sig:
        return False

    parts = _parse_signature(raw_sig)
    # The timestamp MUST come from the signed payload (``t=`` in the signature
    # header). A standalone ``X-Clipia-Timestamp`` header is not covered by the
    # HMAC, so trusting it would open an unauditable timestamp-spoofing path.
    timestamp = parts.get("t")
    provided = parts.get("v1")
    if not timestamp or not provided:
        return False

    # Freshness window.
    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = now if now is not None else time.time()
    if abs(current - ts_int) > tolerance_seconds:
        return False

    body_str = body.decode("utf-8") if isinstance(body, bytes) else body
    expected = _compute_signature(secret, timestamp, body_str)

    # Constant-time comparison.
    return hmac.compare_digest(provided, expected)


__all__ = ["verify_signature", "SIGNATURE_HEADER", "TIMESTAMP_HEADER"]
