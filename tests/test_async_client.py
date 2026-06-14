"""Tests for the asynchronous Clipia client (respx-mocked httpx)."""

from __future__ import annotations

import httpx
import pytest
import respx

from clipia import AsyncClipia, ClipiaApiError, ClipiaTimeoutError

BASE_URL = "https://api.clipia.ai"
RID = "764cabcf-b745-4b3e-ae38-1200304cf45b"


def make_client() -> AsyncClipia:
    return AsyncClipia(api_key="clipia_live_test_key", base_url=BASE_URL)


@respx.mock
@pytest.mark.asyncio
async def test_async_submit_sends_bearer_header() -> None:
    route = respx.post(f"{BASE_URL}/v1/models/nano-banana-2").mock(
        return_value=httpx.Response(
            200, json={"request_id": RID, "status": "IN_QUEUE", "cost": 12}
        )
    )
    async with make_client() as client:
        job = await client.submit("nano-banana-2", input={"prompt": "a cat"})
    assert job.request_id == RID
    assert job.cost == 12
    assert (
        route.calls.last.request.headers["authorization"]
        == "Bearer clipia_live_test_key"
    )


@respx.mock
@pytest.mark.asyncio
async def test_async_status_result_estimate() -> None:
    respx.get(f"{BASE_URL}/v1/requests/{RID}/status").mock(
        return_value=httpx.Response(200, json={"request_id": RID, "status": "COMPLETED"})
    )
    respx.get(f"{BASE_URL}/v1/requests/{RID}").mock(
        return_value=httpx.Response(
            200, json={"request_id": RID, "status": "COMPLETED", "output": {"images": []}}
        )
    )
    respx.post(f"{BASE_URL}/v1/models/nano-banana-2/estimate").mock(
        return_value=httpx.Response(200, json={"credits": 12})
    )
    async with make_client() as client:
        assert (await client.status(RID)).status == "COMPLETED"
        assert (await client.result(RID)).output == {"images": []}
        est = await client.models.estimate("nano-banana-2", {"prompt": "x"})
        assert est.credits == 12


@respx.mock
@pytest.mark.asyncio
async def test_async_subscribe_polls_until_completed() -> None:
    respx.post(f"{BASE_URL}/v1/models/nano-banana-2").mock(
        return_value=httpx.Response(200, json={"request_id": RID, "status": "IN_QUEUE"})
    )
    respx.get(f"{BASE_URL}/v1/requests/{RID}/status").mock(
        side_effect=[
            httpx.Response(200, json={"request_id": RID, "status": "IN_PROGRESS"}),
            httpx.Response(200, json={"request_id": RID, "status": "COMPLETED"}),
        ]
    )
    respx.get(f"{BASE_URL}/v1/requests/{RID}").mock(
        return_value=httpx.Response(
            200, json={"request_id": RID, "status": "COMPLETED", "output": {"ok": True}}
        )
    )
    seen = []
    async with make_client() as client:
        result = await client.subscribe(
            "nano-banana-2",
            input={"prompt": "x"},
            on_queue_update=lambda s: seen.append(s.status),
            poll_interval=0.0,
            timeout=10.0,
        )
    assert result.status == "COMPLETED"
    assert seen == ["IN_PROGRESS", "COMPLETED"]


@respx.mock
@pytest.mark.asyncio
async def test_async_subscribe_async_callback() -> None:
    respx.post(f"{BASE_URL}/v1/models/m").mock(
        return_value=httpx.Response(200, json={"request_id": RID, "status": "IN_QUEUE"})
    )
    respx.get(f"{BASE_URL}/v1/requests/{RID}/status").mock(
        return_value=httpx.Response(200, json={"request_id": RID, "status": "COMPLETED"})
    )
    respx.get(f"{BASE_URL}/v1/requests/{RID}").mock(
        return_value=httpx.Response(200, json={"request_id": RID, "status": "COMPLETED"})
    )
    seen = []

    async def cb(status) -> None:
        seen.append(status.status)

    async with make_client() as client:
        await client.subscribe("m", input={}, on_queue_update=cb, poll_interval=0.0)
    assert seen == ["COMPLETED"]


@respx.mock
@pytest.mark.asyncio
async def test_async_subscribe_times_out() -> None:
    respx.post(f"{BASE_URL}/v1/models/m").mock(
        return_value=httpx.Response(200, json={"request_id": RID, "status": "IN_QUEUE"})
    )
    respx.get(f"{BASE_URL}/v1/requests/{RID}/status").mock(
        return_value=httpx.Response(200, json={"request_id": RID, "status": "IN_PROGRESS"})
    )
    async with make_client() as client:
        with pytest.raises(ClipiaTimeoutError):
            await client.subscribe("m", input={}, poll_interval=0.0, timeout=0.0)


@respx.mock
@pytest.mark.asyncio
async def test_async_error_401() -> None:
    respx.get(f"{BASE_URL}/v1/account").mock(
        return_value=httpx.Response(
            401, json={"error": {"code": "invalid_api_key", "message": "bad"}}
        )
    )
    async with make_client() as client:
        with pytest.raises(ClipiaApiError) as exc:
            await client.account.get()
    assert exc.value.status == 401
    assert exc.value.code == "invalid_api_key"


def test_async_api_key_not_exposed_as_public_attr() -> None:
    client = make_client()
    assert not hasattr(client, "api_key")
    assert client._api_key == "clipia_live_test_key"
    assert "clipia_live_test_key" not in repr(client)
    assert "clipia_live_test_key" not in str(client)
    public_attrs = {k: v for k, v in vars(client).items() if not k.startswith("_")}
    assert "clipia_live_test_key" not in str(public_attrs)


@respx.mock
@pytest.mark.asyncio
async def test_async_slug_is_url_encoded() -> None:
    encoded = "weird%2Fslug%20x"
    route = respx.get(f"{BASE_URL}/v1/models/{encoded}").mock(
        return_value=httpx.Response(200, json={"slug": "weird/slug x", "type": "image"})
    )
    async with make_client() as client:
        detail = await client.models.get("weird/slug x")
    assert detail["type"] == "image"
    assert route.called
    assert encoded in str(route.calls.last.request.url)
