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
# CANCELED is terminal: a generation can be canceled out-of-band (e.g. from the
# Clipia web UI) — the public API has no cancel endpoint, but ``status`` may
# still report CANCELED, so ``subscribe`` must stop polling on it.
IN_QUEUE = "IN_QUEUE"
IN_PROGRESS = "IN_PROGRESS"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
CANCELED = "CANCELED"

TERMINAL_STATUSES = frozenset({COMPLETED, FAILED, CANCELED})


@dataclass
class InputWarning:
    """An ``input`` key the model will not apply.

    The request is still accepted and handled exactly as before; the warning
    only reports the key. ``code`` is ``unknown_parameter`` (the key is not known to the API at
    all, e.g. a typo) or ``unsupported_parameter`` (the key exists, but this
    model neither declares nor uses it); new reasons may be added.
    """

    code: str
    parameter: str
    message: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InputWarning":
        return cls(
            code=str(data.get("code", "")),
            parameter=str(data.get("parameter", "")),
            message=str(data.get("message", "")),
        )


def _parse_warnings(data: Dict[str, Any]) -> List[InputWarning]:
    raw = data.get("warnings")
    if not isinstance(raw, list):
        return []
    return [InputWarning.from_dict(item) for item in raw if isinstance(item, dict)]


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
    #: ``input`` keys the model will not apply; empty when everything was accepted.
    warnings: List[InputWarning] = field(default_factory=list)

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
            warnings=_parse_warnings(data),
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

    Audio results carry ``output["audio"]`` (the first track) and
    ``output["audios"]`` (every track — music models return several variants;
    the first element equals ``audio``).

    ``cost`` is the reserve while the request is running and the amount actually
    charged once it is finished (``0`` for ``FAILED`` / ``CANCELED``).
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
    #: ``input`` keys the model will not apply; empty when everything was accepted.
    warnings: List[InputWarning] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EstimateResponse":
        return cls(
            credits=data["credits"],
            data=data,
            warnings=_parse_warnings(data),
        )


# --- Open-ended catalog / account payloads ----------------------------------
# Modelled as TypedDict because their inner shape is model-dependent and we
# pass the JSON through verbatim.


class ModelPricing(TypedDict, total=False):
    credits: int
    billing_unit: str
    unit_size: int
    character_count: str
    rounding: str
    minimum_credits: int
    available: bool
    # True when the model works but its price depends on the submitted input
    # (e.g. the length of the source media): ``credits`` is absent — call
    # ``estimate`` with the actual input.
    estimate_required: bool
    credits_base: int
    multipliers: Dict[str, Any]
    note: str
    # LLM catalog rates in the OpenAI-compatible format (USD per token strings).
    prompt: str
    completion: str


class ModelTextLimits(TypedDict, total=False):
    """Character bounds for the narration text of a text-to-speech model.

    The text travels in ``input["prompt"]`` and is also described in
    ``input_schema["parameters"]``; a request outside these bounds is rejected with 400
    before the generation is created, so no credits are reserved.
    """

    min_chars: int
    max_chars: int


class ModelInputParameter(TypedDict, total=False):
    name: str
    type: str
    required: bool
    default: Any
    label: str
    hint: str
    options: List[Dict[str, Any]]
    validation: Dict[str, Any]
    min: float
    max: float
    step: float
    minLength: int
    maxLength: int


class ModelInputSchema(TypedDict, total=False):
    parameters: List[ModelInputParameter]
    parameterGroups: List[Dict[str, Any]]


class Model(TypedDict, total=False):
    # Unified OpenAI-compatible catalog fields (text + generation models).
    id: str
    object: str
    created: int
    owned_by: str
    canonical_slug: str
    slug: str
    type: str
    name: str
    description: str
    capabilities: List[str]
    context_length: int
    architecture: Dict[str, Any]
    top_provider: Dict[str, Any]
    supported_parameters: List[str]
    per_request_limits: Any
    pricing: ModelPricing
    input_schema: Optional[ModelInputSchema]
    # Text-to-speech models only: character bounds of the narration text.
    text_limits: ModelTextLimits


class _ModelListRequired(TypedDict):
    data: List[Model]


class ModelList(_ModelListRequired, total=False):
    object: str


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
    "CANCELED",
    "TERMINAL_STATUSES",
    "SubmitResponse",
    "StatusResponse",
    "ResultResponse",
    "EstimateResponse",
    "InputWarning",
    "Model",
    "ModelList",
    "ModelPricing",
    "ModelInputSchema",
    "ModelInputParameter",
    "ModelTextLimits",
    "Account",
    "AccountBalance",
    "AccountUsage",
]
