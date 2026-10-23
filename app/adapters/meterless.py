"""Meterless Nightshift provider -- the app's primary AI provider.

PHASE 2 STUB. The URL normaliser below is real and already unit-tested; the
client is not written yet. Nothing here fabricates a model response.

Implementation notes already established by live testing (docs/DECISIONS.md):
  - Record `meterless.routed_model` as the model that answered. NOT
    `provider_model`, which returns "meterless/auto" on every call.
  - Read the whole `meterless` compute receipt from the response BODY; this
    build returns no `meterless-*` response headers.
  - Never send a tight `max_tokens`: hidden reasoning tokens made a one-word
    answer cost 42-49 completion tokens, and max_tokens=16 failed as
    `<model>_empty_response`. One hard analytical prompt legitimately used
    3001 completion tokens.
  - DETECT TRUNCATION BY TOKEN COUNT, NOT `finish_reason`. A response cut off
    mid-sentence at exactly max_tokens still reported `finish_reason: "stop"`.
    Treat `usage.completion_tokens == max_tokens` as truncation and raise;
    never return the partial text. Otherwise the Writer emits half an evidence
    table and the Evaluator validates truncated JSON as whole.
  - Lane pinning is not honoured; role->disposition routing is intent only.
"""

from __future__ import annotations

from app.config import normalise_meterless_base

__all__ = ["normalise_meterless_base", "MeterlessClient"]


class MeterlessClient:
    """OpenAI-compatible client against the Nightshift Runtime. Not yet built."""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError(
            "MeterlessClient is a Phase 2 stub. app.config.normalise_meterless_base "
            "is implemented and tested; the client is not."
        )
