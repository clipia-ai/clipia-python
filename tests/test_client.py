"""Tests for the synchronous Clipia client (respx-mocked httpx)."""

from __future__ import annotations

import httpx
import pytest
import respx

from clipia import Clipia, ClipiaApiError, ClipiaTimeoutError

BASE_URL = "https://api.clipia.ai"
RID = "764cabcf-b745-4b3e-ae38-1200304cf45b"


def make_client() -> Clipia:
    return Clipia(api_key="clipia_live_test_key", base_url=BASE_URL)


@respx.mock
def test_submit_sends_bearer_header_and_body() -> None:
    route = respx.post(f"{BASE_URL}/v1/models/nano-banana-2").mock(
        return_value=httpx.Response(
            200,
            json={
                "request_id": RID,
                "status": "IN_QUEUE",
                "queue_position": 2,
                "status_url": f"{BASE_URL}/v1/requests/{RID}/status",
                "response_url": f"{BASE_URL}/v1/requests/{RID}",
                "cost": 12,
            },
        )
    )
    client = make_client()
    job = client.submit("nano-banana-2", input={"prompt": "a cat"})

    assert job.request_id == RID
    assert job.status == "IN_QUEUE"
    assert job.queue_position == 2
    assert job.cost == 12

    request = route.calls.last.request
    # Auth header uses the "Bearer <token>" scheme.
    assert request.headers["authorization"] == "Bearer clipia_live_test_key"
    # Body wraps params under "input".
    import json

    assert json.loads(request.content) == {"input": {"prompt": "a cat"}}


@respx.mock
def test_submit_auto_generates_idempotency_key() -> None:
    respx.post(f"{BASE_URL}/v1/models/nano-banana-2").mock(
        return_value=httpx.Response(200, json={"request_id": RID, "status": "IN_QUEUE"})
    )
    client = make_client()
    client.submit("nano-banana-2", input={"prompt": "x"})

    request = respx.calls.last.request
    key = request.headers.get("idempotency-key")
    assert key is not None
    # Looks like a UUID v4.
    import uuid

    parsed = uuid.UUID(key)
    assert parsed.version == 4


@respx.mock
def test_submit_explicit_idempotency_key_and_webhook() -> None:
    respx.post(f"{BASE_URL}/v1/models/nano-banana-2").mock(
        return_value=httpx.Response(200, json={"request_id": RID, "status": "IN_QUEUE"})
    )
    client = make_client()
    client.submit(
        "nano-banana-2",
        input={"prompt": "x"},
        webhook_url="https://hook.example.com/clipia",
        idempotency_key="fixed-key-123",
    )

    request = respx.calls.last.request
    assert request.headers["idempotency-key"] == "fixed-key-123"
    import json

    body = json.loads(request.content)
    assert body["webhook_url"] == "https://hook.example.com/clipia"


@respx.mock
def test_status() -> None:
    respx.get(f"{BASE_URL}/v1/requests/{RID}/status").mock(
        return_value=httpx.Response(
            200,
            json={
                "request_id": RID,
                "status": "IN_PROGRESS",
                "queue_position": None,
                "progress": 45,
                "logs": [],
            },
        )
    )
    client = make_client()
    status = client.status(RID)
    assert status.status == "IN_PROGRESS"
    assert status.progress == 45
    assert status.is_terminal is False


@respx.mock
def test_result_completed() -> None:
    respx.get(f"{BASE_URL}/v1/requests/{RID}").mock(
        return_value=httpx.Response(
            200,
            json={
                "request_id": RID,
                "status": "COMPLETED",
                "model": "nano-banana-2",
                "output": {"images": [{"url": "https://media.clipia.ai/works/x.png"}]},
                "cost": 12,
            },
        )
    )
    client = make_client()
    result = client.result(RID)
    assert result.status == "COMPLETED"
    assert result.pending is False
    assert result.is_terminal is True
    assert result.output["images"][0]["url"].endswith("x.png")


@respx.mock
def test_result_pending_returns_202_flag() -> None:
    respx.get(f"{BASE_URL}/v1/requests/{RID}").mock(
        return_value=httpx.Response(
            202, json={"request_id": RID, "status": "IN_PROGRESS"}
        )
    )
    client = make_client()
    result = client.result(RID)
    assert result.pending is True
    assert result.status == "IN_PROGRESS"
    # 202 must not raise.


@respx.mock
def test_estimate() -> None:
    route = respx.post(f"{BASE_URL}/v1/models/nano-banana-2/estimate").mock(
        return_value=httpx.Response(200, json={"credits": 12})
    )
    client = make_client()
    est = client.models.estimate("nano-banana-2", {"prompt": "x", "aspect_ratio": "16:9"})
    assert est.credits == 12

    import json

    assert json.loads(route.calls.last.request.content) == {
        "input": {"prompt": "x", "aspect_ratio": "16:9"}
    }


@respx.mock
def test_models_list_and_get() -> None:
    respx.get(f"{BASE_URL}/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"slug": "nano-banana-2"}]})
    )
    respx.get(f"{BASE_URL}/v1/models/nano-banana-2").mock(
        return_value=httpx.Response(200, json={"slug": "nano-banana-2", "type": "image"})
    )
    client = make_client()
    listing = client.models.list()
    assert listing["data"][0]["slug"] == "nano-banana-2"
    detail = client.models.get("nano-banana-2")
    assert detail["type"] == "image"


@respx.mock
def test_account_get() -> None:
    respx.get(f"{BASE_URL}/v1/account").mock(
        return_value=httpx.Response(200, json={"balance": {"credits": 1840}})
    )
    client = make_client()
    acct = client.account.get()
    assert acct["balance"]["credits"] == 1840


@respx.mock
def test_subscribe_polls_until_completed() -> None:
    respx.post(f"{BASE_URL}/v1/models/nano-banana-2").mock(
        return_value=httpx.Response(200, json={"request_id": RID, "status": "IN_QUEUE"})
    )
    # status: IN_QUEUE -> IN_PROGRESS -> COMPLETED
    respx.get(f"{BASE_URL}/v1/requests/{RID}/status").mock(
        side_effect=[
            httpx.Response(200, json={"request_id": RID, "status": "IN_QUEUE"}),
            httpx.Response(200, json={"request_id": RID, "status": "IN_PROGRESS", "progress": 50}),
            httpx.Response(200, json={"request_id": RID, "status": "COMPLETED"}),
        ]
    )
    respx.get(f"{BASE_URL}/v1/requests/{RID}").mock(
        return_value=httpx.Response(
            200,
            json={"request_id": RID, "status": "COMPLETED", "output": {"images": []}},
        )
    )

    updates = []
    client = make_client()
    result = client.subscribe(
        "nano-banana-2",
        input={"prompt": "x"},
        on_queue_update=updates.append,
        poll_interval=0.0,
        timeout=10.0,
    )
    assert result.status == "COMPLETED"
    assert [u.status for u in updates] == ["IN_QUEUE", "IN_PROGRESS", "COMPLETED"]


@respx.mock
def test_subscribe_times_out() -> None:
    respx.post(f"{BASE_URL}/v1/models/nano-banana-2").mock(
        return_value=httpx.Response(200, json={"request_id": RID, "status": "IN_QUEUE"})
    )
    respx.get(f"{BASE_URL}/v1/requests/{RID}/status").mock(
        return_value=httpx.Response(200, json={"request_id": RID, "status": "IN_PROGRESS"})
    )
    client = make_client()
    with pytest.raises(ClipiaTimeoutError) as exc:
        client.subscribe(
            "nano-banana-2",
            input={"prompt": "x"},
            poll_interval=0.0,
            timeout=0.0,
        )
    assert exc.value.request_id == RID
    assert exc.value.code == "poll_timeout"


@respx.mock
def test_error_401_raises_clipia_api_error() -> None:
    respx.get(f"{BASE_URL}/v1/account").mock(
        return_value=httpx.Response(
            401,
            json={
                "error": {
                    "type": "invalid_request_error",
                    "code": "invalid_api_key",
                    "message": "Key revoked",
                }
            },
        )
    )
    client = make_client()
    with pytest.raises(ClipiaApiError) as exc:
        client.account.get()
    assert exc.value.status == 401
    assert exc.value.code == "invalid_api_key"
    assert exc.value.message == "Key revoked"
    assert exc.value.type == "invalid_request_error"


@respx.mock
def test_error_402_insufficient_credits_on_submit() -> None:
    respx.post(f"{BASE_URL}/v1/models/nano-banana-2").mock(
        return_value=httpx.Response(
            402,
            json={"error": {"code": "insufficient_credits", "message": "no credits"}},
        )
    )
    client = make_client()
    with pytest.raises(ClipiaApiError) as exc:
        client.submit("nano-banana-2", input={"prompt": "x"})
    assert exc.value.status == 402
    assert exc.value.code == "insufficient_credits"


def test_requires_api_key() -> None:
    with pytest.raises(ValueError):
        Clipia(api_key="")


def test_api_key_not_exposed_as_public_attr() -> None:
    client = make_client()
    # Key is stored as a protected attribute, never a public one.
    assert not hasattr(client, "api_key")
    assert client._api_key == "clipia_live_test_key"
    # repr/str never reveal the key (the surfaces that auto-print in logs/debug).
    assert "clipia_live_test_key" not in repr(client)
    assert "clipia_live_test_key" not in str(client)
    assert "base_url" in repr(client)
    # The key only lives under the protected name, not a public one.
    public_attrs = {k: v for k, v in vars(client).items() if not k.startswith("_")}
    assert "clipia_live_test_key" not in str(public_attrs)


@respx.mock
def test_slug_is_url_encoded() -> None:
    # A slug with reserved characters must be percent-encoded in the path,
    # not concatenated raw (which could alter the request target).
    encoded = "weird%2Fslug%20x"
    route = respx.get(f"{BASE_URL}/v1/models/{encoded}").mock(
        return_value=httpx.Response(200, json={"slug": "weird/slug x", "type": "image"})
    )
    client = make_client()
    detail = client.models.get("weird/slug x")
    assert detail["type"] == "image"
    assert route.called
    assert encoded in str(route.calls.last.request.url)


@respx.mock
def test_context_manager_closes() -> None:
    respx.get(f"{BASE_URL}/v1/account").mock(
        return_value=httpx.Response(200, json={"balance": {"credits": 1}})
    )
    with make_client() as client:
        client.account.get()
    # After exit, the underlying httpx client is closed.
    assert client._http.is_closed
