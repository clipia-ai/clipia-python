# clipia — Python SDK

Official Python SDK for the [Clipia](https://clipia.ai) public API: queue-based
AI image, video, speech and music generation with a `submit → status → result`
flow and signed webhooks. Clipia-native from the ground up: models are addressed
by Clipia slugs and billed in credits, not USD.

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
pip install clipia
```

Requires Python 3.9+.

## Authentication

Create an API key in the Clipia Developer Console (`clipia.ai/developer`, API keys tab). The key is
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
client.models.list()             # text + image/video/audio catalog
client.models.get("nano-banana-2")

# Audio models carry `type == "audio"`; text-to-speech ones add `text_limits`
# (min/max characters of `input["prompt"]`) and per-1000-characters pricing.
tts = client.models.get("gemini-3-1-flash-tts")
print(tts["text_limits"], tts["pricing"])

# Deterministic credit cost for an input, before you submit.
est = client.models.estimate("seedance-2-fast-t2v", {"prompt": "neon city", "duration": 8})
print(est.credits)

client.account.get()             # { "balance": { "credits": ... }, "usage_30d": { ... } }
```

### Ignored parameters (`warnings`)

`submit()` and `models.estimate()` still accept an `input` key the model will
not apply (a typo, a parameter of another model), but the response then carries
`warnings` — one entry per ignored key, naming it and listing the parameters the
model declares. The list is empty when everything was accepted.

```python
for warning in job.warnings:
    print(warning.code, warning.parameter, warning.message)
    # unknown_parameter aspect_ration Parameter "aspect_ration" is not recognized and was ignored. …
```

`status()`, `result()` and `subscribe()` use the same field for a parameter
dropped while the request was running. The only reason so far is
`audio_dropped`: sound was requested, but the audio track did not pass the
model's safety check, so the video is generated without sound (the price of the
request is unchanged).

```python
if any(w.code == "audio_dropped" for w in result.warnings):
    print("The video has no sound.")
```

The unified catalog also returns OpenAI-compatible text models such as
`gpt-5.6-sol`; their entries use `id`, `context_length` and per-token
`pricing`. Use the standard OpenAI Python SDK with
`base_url="https://api.clipia.ai/v1"` for chat completions.

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

### Speech and music

Audio models use the same queue. The result carries `output["audio"]["url"]`
(a file on the Clipia CDN) and, when the extension is known,
`output["audio"]["format"]` (`mp3`, `wav`, …):

```python
speech = client.subscribe(
    "gemini-3-1-flash-tts",
    input={"prompt": "Welcome to Clipia.", "voice": "Zephyr"},
)
print(speech.output["audio"]["url"], speech.output["audio"].get("format"))

music = client.subscribe(
    "suno-music",
    input={"prompt": "warm lo-fi beat for a product demo", "instrumental": True},
)
print(music.output["audio"]["url"])
```

Text-to-speech is billed per 1000 characters of the narration text; the model
catalog exposes the bounds in `text_limits`, and `client.models.estimate()`
returns the exact credit cost before you submit.

## Idempotency and retries

Every `submit()` / `subscribe()` call fixes **one** UUID v4 `Idempotency-Key`
and reuses it for the call's own retries. A transient failure (network error,
`429`, `500`/`502`/`503`/`504`) is retried up to `max_retries` times (default
`2`, `0` disables) with capped exponential backoff seeded by `retry_delay`
(default `0.5` s); a server-sent `Retry-After` always wins. The API keeps a key
for 24 h, so a retried call resolves to the _same_ `request_id` and is never
charged twice.

Pass your own key to make _your_ retries — a second `submit()` for the same
order after a crash — resolve to the same request:

```python
client = Clipia(api_key=os.environ["CLIPIA_KEY"], max_retries=3, retry_delay=1.0)
client.submit("nano-banana-2", input={"prompt": "x"}, idempotency_key="order-42")
```

The same key with a _different_ body is rejected with `409 idempotency_key_reuse`.

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

| Status | `e.code`                                                        | Meaning                                                            |
| ------ | --------------------------------------------------------------- | ------------------------------------------------------------------ |
| 400    | `invalid_request`, `model_input_invalid`, `webhook_url_invalid` | Fix the request body                                               |
| 401    | `invalid_api_key`                                               | Missing or revoked key                                             |
| 402    | `insufficient_credits`                                          | Top up credits                                                     |
| 402    | `subscription_required`                                         | The model needs an active plan — topping up does not help          |
| 403    | `insufficient_scope`                                            | The key lacks the required scope                                   |
| 404    | `not_found`, `model_not_found`                                  | Unknown request id or model slug                                   |
| 409    | `idempotency_key_reuse`                                         | Same `Idempotency-Key`, different body                             |
| 429    | `rate_limit_exceeded`                                           | Per-key / per-account request rate; `e.retry_after` holds the wait |
| 429    | `concurrency_limit_exceeded`                                    | Too many generations in flight; wait for one to finish             |
| 5xx    | `internal_error`, `service_unavailable`                         | Retried automatically by `submit()`/`subscribe()`                  |

`e.type` groups the codes (`invalid_request_error`, `authentication_error`,
`permission_error`, `billing_error`, `rate_limit_error`, `api_error`) and
`e.retry_after` carries the parsed `Retry-After` header in seconds.

`subscribe()` raises `ClipiaTimeoutError` (a subclass of `ClipiaApiError`,
`status=0`, `code="poll_timeout"`) if the job does not reach a terminal status
within `timeout` seconds.

## Using Clipia via MCP (Claude Code / Cursor)

Clipia hosts a remote **Model Context Protocol** server, so an AI coding agent
can generate images, video, speech and music, poll results, list models, search prompt templates
and read your balance directly — **no SDK or code required**. The server is
stateless Streamable HTTP at `https://mcp.clipia.ai/mcp` and authenticates with
the same API key (as a Bearer token).

Tools exposed: `generate_image`, `generate_video`, `generate_audio`,
`generate_music`, `wait_generation`, `get_generation`, `list_models`,
`get_model`, `get_balance`, `search_templates`.

### Claude Code

```bash
claude mcp add --transport http clipia https://mcp.clipia.ai/mcp \
  --header "Authorization: Bearer clipia_live_xxxxxxxx"
```

### Cursor

Add to `~/.cursor/mcp.json` (or the project's `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "clipia": {
      "url": "https://mcp.clipia.ai/mcp",
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
