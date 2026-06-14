"""Typed response shapes for the Clipia public API.

The API returns plain JSON objects. We expose lightweight dataclasses for the
queue lifecycle responses (the ones the high-level helpers reason about) and
``TypedDict`` definitions for the open-ended catalog/account payloads. All raw
JSON is preserved on ``.data`` so callers never lose fields the SDK does not
model explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:  # TypedDict lives in typing on 3.9+, but total= keyword needs care
    from typing import TypedDict
except ImportError:  # pragma: no cover - 3.9 always has it, defensive only
    from typing_extensions import TypedDict  # type: ignore

# Queue lifecycle statuses (mirror the HTTP API contract).
IN_QUEUE = "IN_QUEUE"
IN_PROGRESS = "IN_PROGRESS"
COMPLETED = "COMPLETED"
FAILED = "FAILED"

TERMINAL_STATUSES = frozenset({COMPLETED, FAILED})


@dataclass
class SubmitResponse:
    """Response of ``POST /v1/models/{model}`` (a freshly queued request)."""

    request_id: str
    status: str
    queue_position: Optional[int] = None
    status_url: Optional[str] = None
    response_url: Optional[str] = None
    cost: Optional[int] = None
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubmitResponse":
        return cls(
            request_id=data["request_id"],
            status=data["status"],
            queue_position=data.get("queue_position"),
            status_url=data.get("status_url"),
            response_url=data.get("response_url"),
            cost=data.get("cost"),
            data=data,
        )


@dataclass
class StatusResponse:
    """Response of ``GET /v1/requests/{id}/status``."""

    request_id: str
    status: str
    queue_position: Optional[int] = None
    progress: Optional[int] = None
    logs: List[Any] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StatusResponse":
        return cls(
            request_id=data["request_id"],
            status=data["status"],
            queue_position=data.get("queue_position"),
            progress=data.get("progress"),
            logs=data.get("logs") or [],
            data=data,
        )


@dataclass
class ResultResponse:
    """Response of ``GET /v1/requests/{id}``.

    For non-terminal statuses the API replies ``202`` and only the lifecycle
    fields are present; ``output`` stays ``None`` until ``COMPLETED``.
    """

    request_id: str
    status: str
    model: Optional[str] = None
    output: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    cost: Optional[int] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    pending: bool = False
    data: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, pending: bool = False) -> "ResultResponse":
        return cls(
            request_id=data["request_id"],
            status=data["status"],
            model=data.get("model"),
            output=data.get("output"),
            error=data.get("error"),
            cost=data.get("cost"),
            created_at=data.get("created_at"),
            completed_at=data.get("completed_at"),
            pending=pending,
            data=data,
        )


@dataclass
class EstimateResponse:
    """Response of ``POST /v1/models/{model}/estimate``."""

    credits: int
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EstimateResponse":
        return cls(
            credits=data["credits"],
            data=data,
        )


# --- Open-ended catalog / account payloads ----------------------------------
# Modelled as TypedDict because their inner shape is model-dependent and we
# pass the JSON through verbatim.


class ModelPricing(TypedDict, total=False):
    credits: int
    credits_base: int
    multipliers: Dict[str, Any]
    note: str


class Model(TypedDict, total=False):
    slug: str
    type: str
    name: str
    capabilities: List[str]
    pricing: ModelPricing
    input_schema: Dict[str, Any]


class ModelList(TypedDict):
    data: List[Model]


class AccountBalance(TypedDict, total=False):
    credits: int


class AccountUsage(TypedDict, total=False):
    requests: int
    credits_spent: int


class Account(TypedDict, total=False):
    account_id: str
    balance: AccountBalance
    usage_30d: AccountUsage


__all__ = [
    "IN_QUEUE",
    "IN_PROGRESS",
    "COMPLETED",
    "FAILED",
    "TERMINAL_STATUSES",
    "SubmitResponse",
    "StatusResponse",
    "ResultResponse",
    "EstimateResponse",
    "Model",
    "ModelList",
    "ModelPricing",
    "Account",
    "AccountBalance",
    "AccountUsage",
]
