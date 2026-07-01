"""Tests for the public export surface (parity with the TS SDK)."""

from __future__ import annotations

import clipia
from clipia import _types
from clipia import webhooks


def test_canceled_is_in_types_all() -> None:
    # Regression (L8): CANCELED is a valid terminal status and must be exported
    # alongside the other lifecycle constants, not silently omitted.
    assert "CANCELED" in _types.__all__
    for name in ("IN_QUEUE", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELED"):
        assert name in _types.__all__


def test_status_constants_reexported_from_package_root() -> None:
    # Parity with the TS SDK, which re-exports the status constants via `export *`.
    for name in (
        "IN_QUEUE",
        "IN_PROGRESS",
        "COMPLETED",
        "FAILED",
        "CANCELED",
        "TERMINAL_STATUSES",
    ):
        assert name in clipia.__all__
        assert hasattr(clipia, name)
    assert clipia.CANCELED == "CANCELED"
    assert clipia.CANCELED in clipia.TERMINAL_STATUSES


def test_canceled_is_terminal() -> None:
    assert _types.CANCELED in _types.TERMINAL_STATUSES


def test_timestamp_header_documented_not_used_for_verification() -> None:
    # L10: TIMESTAMP_HEADER is exported for information only. verify_signature
    # must rely on the signed `t=` field, never this unsigned header.
    assert "TIMESTAMP_HEADER" in webhooks.__all__
    assert webhooks.TIMESTAMP_HEADER == "x-clipia-timestamp"
