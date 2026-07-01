"""Clipia — official Python SDK for the Clipia public API.

Quickstart (sync)::

    from clipia import Clipia

    client = Clipia(api_key="clipia_live_...")
    result = client.subscribe("nano-banana-2", input={"prompt": "a sunset over mountains"})
    print(result.output)

Quickstart (async)::

    import asyncio
    from clipia import AsyncClipia

    async def main():
        async with AsyncClipia(api_key="clipia_live_...") as client:
            result = await client.subscribe("nano-banana-2", input={"prompt": "a cat"})
            print(result.output)

    asyncio.run(main())
"""

from __future__ import annotations

from ._async_client import AsyncClipia
from ._client import Clipia
from ._errors import ClipiaApiError, ClipiaTimeoutError
from ._types import (
    CANCELED,
    COMPLETED,
    FAILED,
    IN_PROGRESS,
    IN_QUEUE,
    TERMINAL_STATUSES,
    EstimateResponse,
    ResultResponse,
    StatusResponse,
    SubmitResponse,
)
from ._version import __version__
from .webhooks import verify_signature

__all__ = [
    "Clipia",
    "AsyncClipia",
    "ClipiaApiError",
    "ClipiaTimeoutError",
    "SubmitResponse",
    "StatusResponse",
    "ResultResponse",
    "EstimateResponse",
    # Lifecycle status constants (parity with the TS SDK's `export *`). All five
    # are valid `status` values; the three in TERMINAL_STATUSES stop polling.
    "IN_QUEUE",
    "IN_PROGRESS",
    "COMPLETED",
    "FAILED",
    "CANCELED",
    "TERMINAL_STATUSES",
    "verify_signature",
    "__version__",
]
