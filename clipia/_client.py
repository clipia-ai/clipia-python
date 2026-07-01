"""Synchronous Clipia API client built on ``httpx.Client``."""

from __future__ import annotations

import re
import time
import uuid
from email.utils import parsedate_to_datetime
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

# Transient failures during polling are retried (bounded) so a single blip on an
# in-flight request never loses the request_id.
TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_POLL_RETRIES = 4
MAX_POLL_BACKOFF = 30.0

OnQueueUpdate = Callable[[StatusResponse], None]


def _new_idempotency_key() -> str:
    return str(uuid.uuid4())


_LOCAL_HTTP_RE = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?(/|$)")


def _validate_base_url(base_url: str) -> str:
    """Reject non-HTTPS base URLs so the API key never travels in cleartext.

    ``http://localhost`` and ``http://127.0.0.1`` (with optional port/path) are
    allowed for local development. The host must be *exactly* localhost /
    127.0.0.1 — a lookalike like ``http://localhost.evil.com`` is rejected.
    Anything else must be ``https://``.
    """
    normalized = base_url.rstrip("/")
    lowered = normalized.lower()
    if lowered.startswith("https://"):
        return normalized
    if _LOCAL_HTTP_RE.match(lowered):
        return normalized
    raise ValueError(
        "base_url must use https:// (the API key is sent as a Bearer token "
        "and would leak in cleartext over http). Only http://localhost and "
        "http://127.0.0.1 are allowed for local development. "
        f"Got: {base_url!r}"
    )


def _parse_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _parse_retry_after(response: httpx.Response) -> Optional[float]:
    """Parse an HTTP ``Retry-After`` header (delta-seconds or HTTP-date) to
    seconds. Returns ``None`` when absent or unparseable."""
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    raw = raw.strip()
    try:
        seconds = float(raw)
        return seconds if seconds >= 0 else None
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    delta = when.timestamp() - time.time()
    return delta if delta > 0 else 0.0


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    raise ClipiaApiError.from_response(
        response.status_code,
        _parse_json(response),
        retry_after=_parse_retry_after(response),
    )


def _is_retryable_poll_error(exc: Exception) -> bool:
    """Transient errors worth retrying mid-poll: throttling/5xx or a network
    failure (httpx ``TransportError``)."""
    if isinstance(exc, ClipiaApiError):
        return exc.status in TRANSIENT_STATUSES
    return isinstance(exc, httpx.TransportError)


def _poll_backoff(exc: Exception, attempt: int, poll_interval: float) -> float:
    """Delay before the next retry: server-provided ``Retry-After`` if present,
    otherwise capped exponential backoff seeded by ``poll_interval``."""
    if isinstance(exc, ClipiaApiError) and exc.retry_after is not None:
        return exc.retry_after
    return min(poll_interval * (2 ** attempt), MAX_POLL_BACKOFF)


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
        self.base_url = _validate_base_url(base_url)
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
        # Consecutive transient failures while polling. A single 5xx/429/network
        # blip on an in-flight request must not lose the request_id.
        transient_failures = 0
        while True:
            try:
                status = self.status(job.request_id)
                transient_failures = 0
            except Exception as exc:  # noqa: BLE001 - re-raised unless transient
                if (
                    not _is_retryable_poll_error(exc)
                    or transient_failures >= MAX_POLL_RETRIES
                ):
                    raise
                transient_failures += 1
                if time.monotonic() >= deadline:
                    raise ClipiaTimeoutError(job.request_id, timeout) from exc
                time.sleep(_poll_backoff(exc, transient_failures, poll_interval))
                continue
            if on_queue_update is not None:
                on_queue_update(status)
            if status.is_terminal:
                return self.result(job.request_id)
            if time.monotonic() >= deadline:
                raise ClipiaTimeoutError(job.request_id, timeout)
            time.sleep(poll_interval)


__all__ = ["Clipia"]
