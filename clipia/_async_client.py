"""Asynchronous Clipia API client built on ``httpx.AsyncClient``.

Mirrors :class:`clipia.Clipia` with ``async``/``await`` methods.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional, Union
from urllib.parse import quote

import httpx

from ._errors import ClipiaApiError, ClipiaTimeoutError
from ._types import (
    Account,
    EstimateResponse,
    Model,
    ModelList,
    ResultResponse,
    StatusResponse,
    SubmitResponse,
)
from ._version import __version__

DEFAULT_BASE_URL = "https://api.clipia.ai"
DEFAULT_TIMEOUT = 60.0
DEFAULT_POLL_INTERVAL = 1.0
DEFAULT_SUBSCRIBE_TIMEOUT = 600.0

# An async subscribe callback may be sync or return an awaitable.
AsyncOnQueueUpdate = Callable[[StatusResponse], Union[None, Awaitable[None]]]


def _new_idempotency_key() -> str:
    return str(uuid.uuid4())


def _parse_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    raise ClipiaApiError.from_response(response.status_code, _parse_json(response))


class _AsyncModels:
    def __init__(self, client: "AsyncClipia") -> None:
        self._client = client

    async def list(self) -> ModelList:
        return await self._client._get_json("/v1/models")

    async def get(self, slug: str) -> Model:
        return await self._client._get_json(f"/v1/models/{quote(slug, safe='')}")

    async def estimate(
        self,
        slug: str,
        input: Dict[str, Any],  # noqa: A002
    ) -> EstimateResponse:
        """Estimate the deterministic credit cost of an ``input`` for a model."""
        response = await self._client._http.post(
            f"/v1/models/{quote(slug, safe='')}/estimate", json={"input": input}
        )
        _raise_for_status(response)
        return EstimateResponse.from_dict(_parse_json(response))


class _AsyncAccount:
    def __init__(self, client: "AsyncClipia") -> None:
        self._client = client

    async def get(self) -> Account:
        return await self._client._get_json("/v1/account")


class AsyncClipia:
    """Asynchronous client for the Clipia public API.

    Example:
        >>> async with AsyncClipia(api_key="clipia_live_...") as client:
        ...     result = await client.subscribe("nano-banana-2", input={"prompt": "a cat"})
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: Union[float, httpx.Timeout, None] = DEFAULT_TIMEOUT,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        # Protected: never expose the key via ``vars()``/``pprint``/repr.
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": f"clipia-sdk-python/{__version__}",
            },
        )
        self.models = _AsyncModels(self)
        self.account = _AsyncAccount(self)

    def __repr__(self) -> str:
        # Deliberately omit the API key so it never leaks via repr/logging.
        return f"AsyncClipia(base_url={self.base_url!r})"

    __str__ = __repr__

    # -- context manager / lifecycle ------------------------------------
    async def __aenter__(self) -> "AsyncClipia":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    # -- low-level helpers ----------------------------------------------
    async def _get_json(self, path: str) -> Any:
        response = await self._http.get(path)
        _raise_for_status(response)
        return _parse_json(response)

    # -- queue API ------------------------------------------------------
    async def submit(
        self,
        model: str,
        input: Dict[str, Any],  # noqa: A002
        *,
        webhook_url: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> SubmitResponse:
        body: Dict[str, Any] = {"input": input}
        if webhook_url is not None:
            body["webhook_url"] = webhook_url
        headers = {"Idempotency-Key": idempotency_key or _new_idempotency_key()}
        response = await self._http.post(
            f"/v1/models/{quote(model, safe='')}", json=body, headers=headers
        )
        _raise_for_status(response)
        return SubmitResponse.from_dict(_parse_json(response))

    async def status(self, request_id: str) -> StatusResponse:
        response = await self._http.get(
            f"/v1/requests/{quote(request_id, safe='')}/status"
        )
        _raise_for_status(response)
        return StatusResponse.from_dict(_parse_json(response))

    async def result(self, request_id: str) -> ResultResponse:
        response = await self._http.get(f"/v1/requests/{quote(request_id, safe='')}")
        if response.status_code == 202:
            return ResultResponse.from_dict(_parse_json(response), pending=True)
        _raise_for_status(response)
        return ResultResponse.from_dict(_parse_json(response))

    async def subscribe(
        self,
        model: str,
        input: Dict[str, Any],  # noqa: A002
        *,
        webhook_url: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        on_queue_update: Optional[AsyncOnQueueUpdate] = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_SUBSCRIBE_TIMEOUT,
    ) -> ResultResponse:
        """Submit then poll until a terminal status. ``on_queue_update`` may be
        a sync callback or an async coroutine function."""
        job = await self.submit(
            model,
            input,
            webhook_url=webhook_url,
            idempotency_key=idempotency_key,
        )
        deadline = time.monotonic() + timeout
        while True:
            status = await self.status(job.request_id)
            if on_queue_update is not None:
                maybe = on_queue_update(status)
                if asyncio.iscoroutine(maybe):
                    await maybe
            if status.is_terminal:
                return await self.result(job.request_id)
            if time.monotonic() >= deadline:
                raise ClipiaTimeoutError(job.request_id, timeout)
            await asyncio.sleep(poll_interval)


__all__ = ["AsyncClipia"]
