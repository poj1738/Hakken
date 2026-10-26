"""Meterless Nightshift provider -- the app's primary AI provider.

Every model call in the product goes through `MeterlessClient` (CLAUDE.md rule 2).
It implements the Power contract (`REFERENCE_NOTES` 2.1) and the behaviour
established by live testing (`docs/DECISIONS.md`):

  - Record `meterless.routed_model` as the model that answered -- NOT
    `provider_model`, which returns "meterless/auto" on every call.
  - Read the whole `meterless` compute receipt from the response BODY; this
    build returns no `meterless-*` response headers. Read it defensively: it is
    an undocumented, build-specific shape, and every field is optional.
  - Never send a tight `max_tokens`: hidden reasoning tokens made a one-word
    answer cost 42-49 completion tokens, and one hard prompt used 3001.
  - DETECT TRUNCATION BY TOKEN COUNT, NOT `finish_reason`. A response cut off at
    exactly max_tokens still reported `finish_reason: "stop"`. Truncation raises;
    the partial text is never returned.
  - Lane pinning is not honoured; role -> route is declared intent only.
  - Structured output is "reply with JSON matching this schema" + pydantic
    validation + exactly one repair retry. No native tool calling (`REFERENCE_NOTES` 2.5).

`SAMPLE_MODE` never touches the network and never replays saved model text
(README, "Sample mode"). A call made in sample mode runs the caller's
deterministic `offline` function instead, and the result is labelled
`offline-heuristic` wherever a model id would appear.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings, normalise_meterless_base
from app.schemas import ModelCall

__all__ = [
    "DEFAULT_MAX_TOKENS",
    "MIN_MAX_TOKENS",
    "OFFLINE_MODEL",
    "ChatResult",
    "MeterlessClient",
    "MeterlessError",
    "ProviderStatus",
    "TruncatedResponse",
    "auto_detect",
    "normalise_meterless_base",
    "receipt_summary",
]

#: Generous on purpose: a hard analytical prompt legitimately used 3001
#: completion tokens, and a 2048 cap truncated it (DECISIONS, 24 Oct).
DEFAULT_MAX_TOKENS = 8192
#: Below this a reasoning lane can spend the whole budget before any visible
#: text and fail as `<model>_empty_response`, which reads like an outage.
MIN_MAX_TOKENS = 512
#: The model id recorded for work done by an offline function in SAMPLE_MODE.
OFFLINE_MODEL = "offline-heuristic"

AUTO_DETECT_HOSTS = ("127.0.0.1", "localhost", "[::1]")
AUTO_DETECT_PORTS = (8088, 8090, 8787, 11434)
_RETRYABLE_STATUS = {502, 503, 504}
_ROLES = ("Planner", "Executor", "Evaluator", "Writer")

ProviderState = Literal["online", "unauthorized", "offline"]
ErrorKind = Literal[
    "not_configured", "unauthorized", "offline", "upstream", "truncated",
    "bad_response", "invalid_json", "sample_mode",
]
T = TypeVar("T", bound=BaseModel)


class MeterlessError(RuntimeError):
    """A failed Nightshift call. `kind` says whose problem it is.

    `upstream` means Nightshift answered but its provider failed -- read
    `detail` (`meterless_detail`) before blaming our own code: its prefix names
    the culprit (`nvidia_401`, `<model>_empty_response`, ...).
    """

    def __init__(self, kind: ErrorKind, message: str, *, status: int | None = None,
                 detail: str | None = None) -> None:
        super().__init__(f"{kind}: {message}" + (f" ({detail})" if detail else ""))
        self.kind = kind
        self.status = status
        self.detail = detail
        #: Every request this failure spent, answered or not (scan S9: rule 3 wants each one in
        #: the trace). Filled by `chat`/`chat_json`; empty when nothing was sent.
        self.calls: list[ChatResult] = []


class TruncatedResponse(MeterlessError):
    """`completion_tokens` reached `max_tokens`: the text is cut off, so it is discarded."""

    def __init__(self, completion_tokens: int, max_tokens: int, routed_model: str | None) -> None:
        super().__init__("truncated", f"completion_tokens={completion_tokens} reached max_tokens={max_tokens}",
                         detail=routed_model)
        self.completion_tokens = completion_tokens
        self.max_tokens = max_tokens
        self.routed_model = routed_model


@dataclass(frozen=True)
class ProviderStatus:
    """The Power contract's three states, decided by `GET /v1/models` (never `/healthz`)."""

    state: ProviderState
    routes: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class ChatResult:
    """One answered call: the text, and the evidence of which model produced it."""

    text: str
    role: str
    requested_route: str
    routed_model: str | None
    request_id: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    receipt: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    max_tokens: int = DEFAULT_MAX_TOKENS
    offline: bool = False
    #: HTTP attempts this answer took. >1 means upstream failures were retried --
    #: usually `<model>_empty_response`, i.e. reasoning exhausted the budget.
    attempts: int = 1
    #: A request that failed (`MeterlessError.calls`): why, and whether it was cut off.
    error: str | None = None
    truncated: bool = False

    def model_call(self) -> ModelCall:
        """The `RunResponse.model_calls` entry for this call."""
        role = self.role.capitalize()
        return ModelCall(
            role=role if role in _ROLES else "Executor",
            requested_route=self.requested_route,
            routed_model=self.routed_model,
            request_id=self.request_id,
            tokens=dict(self.usage),
            truncated=self.truncated,
        )

    def trace_fields(self) -> dict[str, Any]:
        """Fields for a `TraceEvent`: model, route, tokens, latency and the receipt summary."""
        return {
            "model": self.routed_model,
            "route": self.requested_route,
            "tokens": dict(self.usage) or None,
            "latency_ms": self.latency_ms,
            "retry_count": self.attempts - 1,
            "meterless": receipt_summary(self.receipt) or None,
            **({"error": self.error, "status": "error"} if self.error else {}),
        }


def _pick(d: Any, *keys: str) -> dict[str, Any]:
    return {k: d[k] for k in keys if isinstance(d, dict) and d.get(k) is not None}


def receipt_summary(receipt: dict[str, Any] | None) -> dict[str, Any]:
    """The receipt fields we rely on, read defensively. Missing fields are omitted, never invented."""
    if not isinstance(receipt, dict):
        return {}
    out = _pick(receipt, "request_id", "receipt_id", "decision_id", "routed_model", "provider_model",
                "requested_model", "mode", "mode_coerced", "served")
    for key, sub in (
        ("winning_route", ("model", "label", "provider", "kind", "tier")),
        ("routing", ("policy", "width", "predicted", "winner", "confidence", "reason")),
        ("cross_check", ("status", "recommended_action", "requires_review")),
        ("egress", ("destination",)),
        ("cost", ("actual_usd", "naive_usd")),
        ("consensus", ("raced",)),
    ):
        picked = _pick(receipt.get(key), *sub)
        if picked:
            out[key] = picked
    phases = receipt.get("phases")
    if isinstance(phases, list):
        out["phases"] = [_pick(p, "phase", "model", "ms", "tokensIn", "tokensOut") for p in phases[:8]]
    return out


def _routed_model(body: dict[str, Any], receipt: dict[str, Any]) -> str | None:
    """`routed_model`, then `winning_route.model`, then the top-level `model` (DECISIONS, 23 Oct)."""
    winning = receipt.get("winning_route") if isinstance(receipt.get("winning_route"), dict) else {}
    for value in (receipt.get("routed_model"), winning.get("model"), body.get("model")):
        if isinstance(value, str) and value:
            return value
    return None


def _error_detail(response: httpx.Response) -> str | None:
    try:
        err = response.json().get("error") or {}
    except (ValueError, AttributeError):
        return None
    if not isinstance(err, dict):
        return None
    detail = err.get("meterless_detail") or err.get("message") or err.get("code")
    return str(detail)[:300] if detail else None


def _extract_json(text: str) -> Any:
    """The JSON object in a reply: bare, fenced in ```json, or surrounded by prose."""
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.S)
    if fence:
        stripped = fence.group(1).strip()
    try:
        return json.loads(stripped)
    except ValueError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(stripped[start:end + 1])


def _schema_instruction(schema: type[BaseModel]) -> str:
    return ("Respond with ONLY a single JSON object that validates against this JSON Schema. "
            "No prose, no markdown fences.\n" + json.dumps(schema.model_json_schema(), separators=(",", ":")))


class MeterlessClient:
    """OpenAI-compatible client against the Nightshift Runtime.

    Pass `transport` (an `httpx.MockTransport`) in tests; production uses the
    default network transport. `sleep` is injectable so retry backoff is not
    waited out in tests.
    """

    def __init__(self, settings: Settings | None = None, *, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.settings = settings or get_settings()
        self.base_url = normalise_meterless_base(self.settings.meterless_base_url)
        self._transport = transport
        self._sleep = sleep

    # -- plumbing ------------------------------------------------------------

    @property
    def sample_mode(self) -> bool:
        return self.settings.sample_mode

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=timeout, transport=self._transport)

    def _headers(self, *, chat: bool) -> dict[str, str]:
        headers = {"meterless-app": self.settings.meterless_app_id}
        if self.settings.has_meterless_token:
            headers["Authorization"] = f"Bearer {self.settings.meterless_runtime_token.get_secret_value()}"
        if chat:
            headers["meterless-scope"] = "user"
        return headers

    # -- status --------------------------------------------------------------

    def status(self, timeout: float = 10.0) -> ProviderStatus:
        """`GET /v1/models` decides: 401/403 unauthorized, 200 with meterless ids online, else offline."""
        if self.sample_mode:
            return ProviderStatus("offline", [], "SAMPLE_MODE: Nightshift is not contacted")
        try:
            with self._client(timeout) as client:
                response = client.get("/models", headers=self._headers(chat=False))
        except httpx.HTTPError as exc:
            return ProviderStatus("offline", [], f"unreachable: {type(exc).__name__}")
        if response.status_code in (401, 403):
            return ProviderStatus("unauthorized", [], f"HTTP {response.status_code}")
        if response.status_code != 200:
            return ProviderStatus("offline", [], f"HTTP {response.status_code}")
        try:
            ids = [m.get("id") for m in response.json().get("data", []) if isinstance(m, dict)]
        except (ValueError, AttributeError):
            return ProviderStatus("offline", [], "unreadable /v1/models body")
        routes = sorted(i for i in ids if isinstance(i, str) and i.startswith("meterless/"))
        if not routes:
            return ProviderStatus("offline", [], "no meterless/* routes listed")
        return ProviderStatus("online", routes, f"{len(routes)} routes")

    # -- chat ----------------------------------------------------------------

    def chat(self, role: str, messages: list[dict[str, str]], *, route: str | None = None,
             max_tokens: int = DEFAULT_MAX_TOKENS, temperature: float | None = None,
             offline: Callable[[], str] | None = None) -> ChatResult:
        """One plain-text completion. Returns the text as a string, exactly like OpenAI."""
        route = route or self.settings.lane_for(role)
        if self.sample_mode:
            if offline is None:
                raise MeterlessError("sample_mode", f"{role}: no offline function for SAMPLE_MODE")
            start = time.monotonic()
            text = offline()
            return ChatResult(text=text, role=role, requested_route=route, routed_model=OFFLINE_MODEL,
                              latency_ms=int((time.monotonic() - start) * 1000), max_tokens=max_tokens,
                              offline=True)
        if max_tokens < MIN_MAX_TOKENS:
            raise ValueError(f"max_tokens={max_tokens} is below {MIN_MAX_TOKENS}: hidden reasoning tokens "
                             "would empty the response (docs/DECISIONS.md)")
        if not self.settings.has_meterless_token:
            raise MeterlessError("not_configured", "METERLESS_RUNTIME_TOKEN is unset or a placeholder")

        payload: dict[str, Any] = {"model": route, "messages": messages, "max_tokens": max_tokens, "stream": False}
        if temperature is not None:
            payload["temperature"] = temperature
        start = time.monotonic()
        try:
            response, latency_ms, attempts = self._post_with_retry(payload)
            result = self._parse_chat(response, role=role, route=route, max_tokens=max_tokens,
                                      latency_ms=latency_ms)
        except MeterlessError as exc:
            # The request was sent, so it is a model call: keep it, with whatever is known of who
            # answered (a truncated reply names its model; an upstream failure may name none).
            routed = exc.routed_model if isinstance(exc, TruncatedResponse) else None
            exc.calls = [ChatResult(text="", role=role, requested_route=route, routed_model=routed,
                                    latency_ms=int((time.monotonic() - start) * 1000), max_tokens=max_tokens,
                                    error=str(exc)[:300], truncated=isinstance(exc, TruncatedResponse),
                                    usage={"completion_tokens": exc.completion_tokens}
                                    if isinstance(exc, TruncatedResponse) else {})]
            raise
        result.attempts = attempts
        return result

    def _post_with_retry(self, payload: dict[str, Any]) -> tuple[httpx.Response, int, int]:
        """Bounded retries on connection failures and 502/503/504 only. A read timeout is not
        retried: three 180 s waits would spend the whole run budget."""
        attempts = 1 + self.settings.max_retries
        last: MeterlessError | None = None
        for attempt in range(attempts):
            if attempt:
                self._sleep(min(2.0 * attempt, 5.0))
            start = time.monotonic()
            try:
                with self._client(self.settings.meterless_timeout_s) as client:
                    response = client.post("/chat/completions", json=payload, headers=self._headers(chat=True))
            except httpx.TimeoutException as exc:
                raise MeterlessError("offline", f"no answer within {self.settings.meterless_timeout_s:.0f}s "
                                     f"({type(exc).__name__})") from exc
            except httpx.TransportError as exc:
                last = MeterlessError("offline", f"cannot reach Nightshift at {self.base_url} "
                                      f"({type(exc).__name__})")
                continue
            latency_ms = int((time.monotonic() - start) * 1000)
            if response.status_code in (401, 403):
                raise MeterlessError("unauthorized", "the Runtime token was rejected", status=response.status_code)
            if response.status_code in _RETRYABLE_STATUS:
                last = MeterlessError("upstream", f"HTTP {response.status_code}", status=response.status_code,
                                      detail=_error_detail(response))
                continue
            if response.status_code != 200:
                raise MeterlessError("bad_response", f"HTTP {response.status_code}", status=response.status_code,
                                     detail=_error_detail(response))
            return response, latency_ms, attempt + 1
        assert last is not None
        raise last

    def _parse_chat(self, response: httpx.Response, *, role: str, route: str, max_tokens: int,
                    latency_ms: int) -> ChatResult:
        try:
            body = response.json()
        except ValueError as exc:
            raise MeterlessError("bad_response", "response body is not JSON") from exc
        receipt = body.get("meterless") if isinstance(body.get("meterless"), dict) else {}
        routed = _routed_model(body, receipt)
        usage = {k: v for k, v in (body.get("usage") or {}).items() if isinstance(v, int)}
        completion = usage.get("completion_tokens")
        # The tell is the token count, never finish_reason (DECISIONS, 24 Oct).
        if completion is not None and completion >= max_tokens:
            raise TruncatedResponse(completion, max_tokens, routed)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise MeterlessError("bad_response", "no choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise MeterlessError("bad_response", "empty content", detail=routed)
        return ChatResult(text=content, role=role, requested_route=route, routed_model=routed,
                          request_id=receipt.get("request_id") or body.get("id"), usage=usage,
                          receipt=receipt, latency_ms=latency_ms, max_tokens=max_tokens)

    # -- structured ----------------------------------------------------------

    def chat_json(self, role: str, messages: list[dict[str, str]], schema: type[T], *,
                  route: str | None = None, max_tokens: int = DEFAULT_MAX_TOKENS,
                  offline: Callable[[], T | dict[str, Any]] | None = None) -> tuple[T, list[ChatResult]]:
        """A schema-validated object, with exactly one repair retry. Returns every call made."""
        if self.sample_mode:
            if offline is None:
                raise MeterlessError("sample_mode", f"{role}: no offline function for SAMPLE_MODE")
            value = offline()
            parsed = value if isinstance(value, schema) else schema.model_validate(value)
            result = self.chat(role, messages, route=route, max_tokens=max_tokens,
                               offline=lambda: parsed.model_dump_json())
            return parsed, [result]

        convo = [{"role": "system", "content": _schema_instruction(schema)}, *messages]
        calls: list[ChatResult] = []
        error = ""
        for attempt in range(2):
            try:
                result = self.chat(role, convo, route=route, max_tokens=max_tokens)
            except MeterlessError as exc:
                exc.calls = [*calls, *exc.calls]  # the first, unvalidated answer was a real call too
                raise
            calls.append(result)
            try:
                return schema.model_validate(_extract_json(result.text)), calls
            except (ValueError, ValidationError) as exc:
                error = str(exc)[:500]
                if attempt == 0:
                    convo = [*convo, {"role": "assistant", "content": result.text},
                             {"role": "user", "content": "That reply did not validate against the schema: "
                              f"{error}\nReply with ONLY the corrected JSON object."}]
        exc = MeterlessError("invalid_json", f"{role}: no valid JSON after one repair retry", detail=error)
        exc.calls = calls  # both answered by a model: they belong in model_calls (scan S9)
        raise exc


def auto_detect(settings: Settings | None = None, *, timeout: float = 1.5,
                transport: httpx.BaseTransport | None = None) -> tuple[str, ProviderStatus] | None:
    """The contract's Auto Detect: the first online-or-unauthorized runtime on the usual ports."""
    base = settings or get_settings()
    for host in AUTO_DETECT_HOSTS:
        for port in AUTO_DETECT_PORTS:
            url = f"http://{host}:{port}/v1"
            probe = MeterlessClient(base.model_copy(update={"meterless_base_url": url, "sample_mode": False}),
                                    transport=transport)
            status = probe.status(timeout=timeout)
            if status.state in ("online", "unauthorized"):
                return url, status
    return None
