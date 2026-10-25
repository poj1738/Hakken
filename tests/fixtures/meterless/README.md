# Recorded Nightshift responses — parser fixtures

**Real responses, recorded once [live — Arnav's machine, 25 Oct], response bodies only.**
No request headers are stored, so no token is in these files. Each file is
`{"status_code": ..., "body": ...}` exactly as the Runtime returned it, with one edit:
`receipt_envelope.body.llama_cpp_ref` (a git commit hash) and `.manifest_hash` (a
SHA-256) read `<redacted: build hash>`. They are build identifiers, not secrets, but
they are secret-shaped and the pre-commit scan rightly refuses them.

| File | Request | What it pins |
|---|---|---|
| `models.json` | `GET /v1/models` with the token | `online`: 18 `meterless/*` routes plus `nvidia/*` and `local-runtime/*` lanes |
| `models_unauthorized.json` | `GET /v1/models` without a token | the 401 body behind `unauthorized` |
| `chat_auto_text.json` | `meterless/auto`, plain text, `max_tokens` 1024 | a string answer, the receipt, `routed_model` |
| `chat_fast_json.json` | `meterless/fast`, "reply with JSON" | a bare JSON object as `content` |

**These are test fixtures for the adapter's parsing, never answers.** `SAMPLE_MODE`
does not replay them: it runs offline functions labelled `offline-heuristic` and never
replays saved model text (README, "Sample mode").

Observations, one machine, one day:
- A one-sentence answer cost **502 completion tokens** (hidden reasoning), which is why
  `max_tokens` is never tight.
- This build's receipt has no `routing` block (Arpon's 23 Oct build did) and adds
  `job`, `lineage`, `mcp`. Field shapes vary by build; the adapter reads every field as
  optional.
- This runtime also lists `local-runtime/*` models, so `meterless/auto` *can* route to
  a non-NVIDIA model. Both recorded calls went to
  `nvidia/nemotron-3.5-lightning-30b-a3b`. Always record `routed_model`.
