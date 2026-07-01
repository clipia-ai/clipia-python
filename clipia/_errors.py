"""Error type raised by the Clipia SDK."""

from __future__ import annotations

from typing import Any, Dict, Optional


class ClipiaApiError(Exception):
    """Raised when the Clipia API returns a non-2xx response.

    Attributes:
        status: HTTP status code (e.g. ``401``, ``402``, ``429``).
        code: machine-readable error code from the API envelope
            (e.g. ``invalid_api_key``, ``insufficient_credits``). May be empty
            if the response body was not the expected ``{"error": {...}}`` shape.
        message: human-readable error message.
        type: error category from the envelope (e.g. ``invalid_request_error``).
        body: the parsed JSON body, when available.
        retry_after: parsed ``Retry-After`` delay in seconds, when the server
            sent one (typically on ``429``/``503``). ``None`` otherwise. Used by
            ``subscribe`` to pace transient retries.
    """

    def __init__(
        self,
        status: int,
        code: str = "",
        message: str = "",
        *,
        type: str = "",  # noqa: A002 - mirrors the API field name
        body: Optional[Dict[str, Any]] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        self.status = status
        self.code = code
        self.message = message or code or f"HTTP {status}"
        self.type = type
        self.body = body
        self.retry_after = retry_after
        super().__init__(f"[{status}] {self.code or 'error'}: {self.message}")

    @classmethod
    def from_response(
        cls,
        status: int,
        body: Optional[Dict[str, Any]],
        *,
        retry_after: Optional[float] = None,
    ) -> "ClipiaApiError":
        """Build an error from a parsed response body (``{"error": {...}}``)."""
        err: Dict[str, Any] = {}
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            err = body["error"]
        return cls(
            status=status,
            code=str(err.get("code", "")),
            message=str(err.get("message", "")),
            type=str(err.get("type", "")),
            body=body if isinstance(body, dict) else None,
            retry_after=retry_after,
        )


class ClipiaTimeoutError(ClipiaApiError):
    """Raised by ``subscribe`` when a request does not reach a terminal status
    within the configured timeout. Carries ``status=0`` (no HTTP response)."""

    def __init__(self, request_id: str, timeout: float) -> None:
        self.request_id = request_id
        self.timeout = timeout
        super().__init__(
            status=0,
            code="poll_timeout",
            message=(
                f"Request {request_id} did not reach a terminal status "
                f"within {timeout}s"
            ),
        )


__all__ = ["ClipiaApiError", "ClipiaTimeoutError"]
