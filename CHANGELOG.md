# Changelog — clipia (Python)

## Unreleased

- Types: `InputWarning` and `warnings` (a list, empty when nothing was ignored)
  on `SubmitResponse` and `EstimateResponse` — `input` keys the model will not
  apply (a typo, a parameter of another model). The request is still accepted
  and handled exactly as before.

## 1.4.0 — 2026-10-12

- Types: `ModelPricing.estimate_required` (the price depends on the input:
  call `estimate`); audio results document `output["audios"]` (every track —
  music models return several variants; the first equals `audio`);
  `ResultResponse.cost` documented as the charged amount (0 for `FAILED` /
  `CANCELED`).

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
