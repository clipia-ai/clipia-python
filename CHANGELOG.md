# Changelog — clipia (Python)

## 1.3.0 — 2026-10-09

- `submit()` / `subscribe()` retry transient failures (network error, 429,
  500/502/503/504) up to `max_retries` times (default 2) reusing **one**
  `Idempotency-Key` per call, so a retry never enqueues or charges twice.
  `Retry-After` is honored; otherwise capped exponential backoff seeded by
  `retry_delay` (default 0.5 s). Both knobs are constructor arguments of
  `Clipia` and `AsyncClipia`; `max_retries=0` restores the previous behaviour.
- README: speech and music example, error table (`subscription_required`,
  `concurrency_limit_exceeded`, `webhook_url_invalid`, `model_not_found`),
  audio catalog fields (`type == "audio"`, `text_limits`), MCP tool list with
  `generate_audio` / `generate_music`.
- Audio results document `output["audio"]["format"]` (container derived from
  the CDN file extension; absent when unknown).
- Internal comments reworded to describe the OpenAI-compatible catalog format.

Not published yet.
