# clipia — Python SDK

Official Python SDK for the [Clipia](https://clipia.ai) public API: queue-based
AI image & video generation with a `submit → status → result` flow and signed
webhooks. The DX mirrors fal.ai, but is Clipia-native (credits, not USD).

- Sync (`Clipia`) and async (`AsyncClipia`) clients
- High-level `subscribe()` that submits and polls until the job finishes
- Typed responses (`SubmitResponse`, `StatusResponse`, `ResultResponse`, ...)
- HMAC-SHA256 webhook signature verification
- Single runtime dependency: [`httpx`](https://www.python-httpx.org/)

> Prefer driving Clipia from an AI agent (Claude Code / Cursor) instead of
> writing code? Clipia ships a hosted **MCP server** — no SDK required. See
> [Using Clipia via MCP](#using-clipia-via-mcp-claude-code--cursor) below.

## Install

```bash
pip install clipia-ai
```

Requires Python 3.9+.

## Authentication

Create an API key in your Clipia dashboard (`Settings → API keys`). The key is
shown once — store it as a server-side secret (never ship it to browsers or
mobile apps). It is sent as `Authorization: Bearer <key>`.

```bash
export CLIPIA_KEY="clipia_live_xxxxxxxxxxxxxxxxxxxxxx"
```

Keys come in two flavours: `clipia_live_…` (production, charges credits) and
`clipia_test_…` (sandbox — instant mock results, no credits charged). Use a
test key to validate your integration before going live.

## Quickstart (sync)

```python
import os
from clipia import Clipia

client = Clipia(api_key=os.environ["CLIPIA_KEY"])

# One call: submit + poll until COMPLETED / FAILED.
result = client.subscribe(
    "nano-banana-2",
    input={"prompt": "a sunset over mountains, cinematic"},
    on_queue_update=lambda s: print("status:", s.status, s.progress),
)
print(result.output["images"][0]["url"])
```

### Manual queue control

```python
job = client.submit("nano-banana-2", input={"prompt": "a cat"})
print(job.request_id, job.cost)

status = client.status(job.request_id)   # IN_QUEUE | IN_PROGRESS | COMPLETED | FAILED
result = client.result(job.request_id)   # result.pending == True while still running (HTTP 202)
```

> A generation cannot be canceled: credits are reserved the moment it starts
> and the underlying compute cannot be interrupted. Submit deliberately — and
> use a `clipia_test_…` sandbox key while iterating.

### Models, cost estimate & account

```python
client.models.list()             # { "data": [ ... ] }
client.models.get("nano-banana-2")

# Deterministic credit cost for an input, before you submit.
est = client.models.estimate("seedance-2-fast-t2v", {"prompt": "neon city", "duration": 8})
print(est.credits)

client.account.get()             # { "balance": { "credits": ... }, "usage_30d": { ... } }
```

The client is also a context manager:

```python
with Clipia(api_key=os.environ["CLIPIA_KEY"]) as client:
    client.account.get()
```

## Quickstart (async)

```python
import asyncio, os
from clipia import AsyncClipia

async def main():
    async with AsyncClipia(api_key=os.environ["CLIPIA_KEY"]) as client:
        result = await client.subscribe(
            "seedance-2-fast-i2v",
            input={"image_url": "https://.../in.png", "duration": 4},
        )
        print(result.output["video"]["url"])

asyncio.run(main())
```

`on_queue_update` may be a plain function or an `async def` coroutine.

## Idempotency

`submit()` (and `subscribe()`) automatically attach a UUID v4 `Idempotency-Key`
header so network retries are safe. Pass your own to control retries:

```python
client.submit("nano-banana-2", input={"prompt": "x"}, idempotency_key="order-42")
```

## Webhooks

Pass `webhook_url` to `submit()`/`subscribe()` and Clipia will POST the result to
your server. Always verify the signature on the **raw** request body:

```python
from clipia import verify_signature

# In your web handler (Flask/FastAPI/etc.):
ok = verify_signature(
    secret=WEBHOOK_SIGNING_SECRET,   # from your dashboard
    headers=request.headers,         # X-Clipia-Signature: t=...,v1=...
    body=raw_request_body,           # bytes or str, exactly as received
    tolerance_seconds=300,           # freshness window (default 5 min)
)
if not ok:
    return ("invalid signature", 400)
```

The delivery payload carries `status` `"OK"` (success) or `"ERROR"` (failed).
Verification is constant-time and rejects deliveries whose timestamp is outside
the tolerance window. Treat webhooks as **idempotent by `request_id`** —
deliveries can repeat.

## Errors

Non-2xx responses raise `ClipiaApiError`:

```python
from clipia import ClipiaApiError

try:
    client.submit("nano-banana-2", input={"prompt": "x"})
except ClipiaApiError as e:
    print(e.status, e.code, e.message)   # e.g. 402 insufficient_credits "..."
```

`subscribe()` raises `ClipiaTimeoutError` (a subclass of `ClipiaApiError`,
`status=0`, `code="poll_timeout"`) if the job does not reach a terminal status
within `timeout` seconds.

## Using Clipia via MCP (Claude Code / Cursor)

Clipia hosts a remote **Model Context Protocol** server, so an AI coding agent
can generate images/video, poll results, list models, search prompt templates
and read your balance directly — **no SDK or code required**. The server is
stateless Streamable HTTP at `https://api.clipia.ai/mcp` and authenticates with
the same API key (as a Bearer token).

Tools exposed: `generate_image`, `generate_video`, `wait_generation`,
`get_generation`, `list_models`, `get_model`, `get_balance`, `search_templates`.

### Claude Code

```bash
claude mcp add --transport http clipia https://api.clipia.ai/mcp \
  --header "Authorization: Bearer clipia_live_xxxxxxxx"
```

### Cursor

Add to `~/.cursor/mcp.json` (or the project's `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "clipia": {
      "url": "https://api.clipia.ai/mcp",
      "headers": {
        "Authorization": "Bearer clipia_live_xxxxxxxx"
      }
    }
  }
}
```

Use a `clipia_test_…` key first to exercise the integration with instant mock
results and no credit charges.

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

## License

MIT — see [LICENSE](./LICENSE).
