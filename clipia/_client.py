"""Synchronous Clipia API client built on ``httpx.Client``."""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, Optional, Union
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

OnQueueUpdate = Callable[[StatusResponse], None]


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


class _Models:
    """Sub-resource: ``client.models.list()`` / ``client.models.get(slug)`` /
    ``client.models.estimate(slug, input)``."""

    def __init__(self, client: "Clipia") -> None:
        self._client = client

    def list(self) -> ModelList:
        return self._client._get_json("/v1/models")

    def get(self, slug: str) -> Model:
        return self._client._get_json(f"/v1/models/{quote(slug, safe='')}")

    def estimate(
        self,
        slug: str,
        input: Dict[str, Any],  # noqa: A002 - mirrors the API/contract field
    ) -> EstimateResponse:
        """Estimate the deterministic credit cost of an ``input`` for a model."""
        response = self._client._http.post(
            f"/v1/models/{quote(slug, safe='')}/estimate", json={"input": input}
        )
        _raise_for_status(response)
        return EstimateResponse.from_dict(_parse_json(response))


class _Account:
    """Sub-resource: ``client.account.get()``."""

    def __init__(self, client: "Clipia") -> None:
        self._client = client

    def get(self) -> Account:
        return self._client._get_json("/v1/account")


class Clipia:
    """Synchronous client for the Clipia public API.

    Example:
        >>> client = Clipia(api_key="clipia_live_...")
        >>> job = client.submit("nano-banana-2", input={"prompt": "a cat"})
        >>> result = client.subscribe("nano-banana-2", input={"prompt": "a cat"})
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: Union[float, httpx.Timeout, None] = DEFAULT_TIMEOUT,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        # Protected: never expose the key via ``vars()``/``pprint``/repr.
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": f"clipia-sdk-python/{__version__}",
            },
        )
        self.models = _Models(self)
        self.account = _Account(self)

    def __repr__(self) -> str:
        # Deliberately omit the API key so it never leaks via repr/logging.
        return f"Clipia(base_url={self.base_url!r})"

    __str__ = __repr__

    # -- context manager / lifecycle ------------------------------------
    def __enter__(self) -> "Clipia":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # -- low-level helpers ----------------------------------------------
    def _get_json(self, path: str) -> Any:
        response = self._http.get(path)
        _raise_for_status(response)
        return _parse_json(response)

    # -- queue API ------------------------------------------------------
    def submit(
        self,
        model: str,
        input: Dict[str, Any],  # noqa: A002 - mirrors the API/contract field
        *,
        webhook_url: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> SubmitResponse:
        """Queue a generation. Returns immediately with a ``request_id``."""
        body: Dict[str, Any] = {"input": input}
        if webhook_url is not None:
            body["webhook_url"] = webhook_url
        headers = {"Idempotency-Key": idempotency_key or _new_idempotency_key()}
        response = self._http.post(
            f"/v1/models/{quote(model, safe='')}", json=body, headers=headers
        )
        _raise_for_status(response)
        return SubmitResponse.from_dict(_parse_json(response))

    def status(self, request_id: str) -> StatusResponse:
        """Fetch the current status of a queued request."""
        response = self._http.get(
            f"/v1/requests/{quote(request_id, safe='')}/status"
        )
        _raise_for_status(response)
        return StatusResponse.from_dict(_parse_json(response))

    def result(self, request_id: str) -> ResultResponse:
        """Fetch the result. Non-terminal requests come back with ``pending=True``
        (HTTP ``202``); terminal ones (``COMPLETED``/``FAILED``) carry the final
        payload."""
        response = self._http.get(f"/v1/requests/{quote(request_id, safe='')}")
        if response.status_code == 202:
            return ResultResponse.from_dict(_parse_json(response), pending=True)
        _raise_for_status(response)
        return ResultResponse.from_dict(_parse_json(response))

    def subscribe(
        self,
        model: str,
        input: Dict[str, Any],  # noqa: A002
        *,
        webhook_url: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        on_queue_update: Optional[OnQueueUpdate] = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_SUBSCRIBE_TIMEOUT,
    ) -> ResultResponse:
        """High-level helper: submit then poll until a terminal status.

        Calls ``on_queue_update`` (if given) on every poll with the latest
        :class:`StatusResponse`. Raises :class:`ClipiaTimeoutError` if the
        request does not finish within ``timeout`` seconds.
        """
        job = self.submit(
            model,
            input,
            webhook_url=webhook_url,
            idempotency_key=idempotency_key,
        )
        deadline = time.monotonic() + timeout
        while True:
            status = self.status(job.request_id)
            if on_queue_update is not None:
                on_queue_update(status)
            if status.is_terminal:
                return self.result(job.request_id)
            if time.monotonic() >= deadline:
                raise ClipiaTimeoutError(job.request_id, timeout)
            time.sleep(poll_interval)


__all__ = ["Clipia"]
