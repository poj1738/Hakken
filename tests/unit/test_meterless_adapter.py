"""The Nightshift adapter against the Power contract (REFERENCE_NOTES 2.1) and DECISIONS.

No network: every test injects an httpx.MockTransport. Where shape matters, the
responses are the real ones recorded in tests/fixtures/meterless/.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.adapters.meterless import (
    MIN_MAX_TOKENS,
    OFFLINE_MODEL,
    MeterlessClient,
    MeterlessError,
    TruncatedResponse,
    auto_detect,
    receipt_summary,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "meterless"
TOKEN = "example-runtime-token"  # a dummy; "example" is on the secret scan's allowlist


def recorded(name: str) -> tuple[int, dict[str, Any]]:
    d = json.loads((FIX / name).read_text())
    return d["status_code"], d["body"]


def chat_body(content: str = "ok", *, completion: int = 50, model: str = "nvidia/x",
              receipt: dict[str, Any] | None = None, finish: str = "stop") -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "chatcmpl-1", "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 10, "completion_tokens": completion, "total_tokens": 10 + completion},
    }
    if receipt is not None:
        body["meterless"] = receipt
    return body


class Recorder:
    """A MockTransport handler that records requests and replays queued responses."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.queue = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        if isinstance(item, Exception):
            raise item
        return item


def client(make_settings: Callable[..., Any], handler: Recorder, **overrides: Any) -> MeterlessClient:
    settings = make_settings(meterless_runtime_token=TOKEN, **overrides)
    return MeterlessClient(settings, transport=httpx.MockTransport(handler), sleep=lambda _s: None)


MSG = [{"role": "user", "content": "hi"}]


# -- status --------------------------------------------------------------------


def test_status_online_from_the_recorded_models_list(make_settings) -> None:
    code, body = recorded("models.json")
    st = client(make_settings, Recorder(httpx.Response(code, json=body))).status()
    assert st.state == "online"
    assert "meterless/auto" in st.routes and all(r.startswith("meterless/") for r in st.routes)


@pytest.mark.parametrize("code", [401, 403])
def test_status_unauthorized_is_not_offline(make_settings, code: int) -> None:
    """The contract's first done-check: a wrong token shows unauthorized, not offline."""
    _, body = recorded("models_unauthorized.json")
    st = client(make_settings, Recorder(httpx.Response(code, json=body))).status()
    assert st.state == "unauthorized"


@pytest.mark.parametrize("response", [
    httpx.Response(500, json={}),
    httpx.Response(200, json={"data": [{"id": "nvidia/only-concrete"}]}),
    httpx.ConnectError("refused"),
])
def test_status_offline_otherwise(make_settings, response) -> None:
    assert client(make_settings, Recorder(response)).status().state == "offline"


def test_status_uses_models_not_healthz_and_never_doubles_v1(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=recorded("models.json")[1]))
    client(make_settings, rec, meterless_base_url="127.0.0.1:8088/v1/chat/completions").status()
    url = str(rec.requests[0].url)
    assert url == "http://127.0.0.1:8088/v1/models" and "/v1/v1" not in url
    assert rec.requests[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert rec.requests[0].headers["meterless-app"] == "hakken-agent"
    assert "meterless-scope" not in rec.requests[0].headers


# -- chat ------------------------------------------------------------------------


def test_chat_parses_the_recorded_answer_and_receipt(make_settings) -> None:
    code, body = recorded("chat_auto_text.json")
    res = client(make_settings, Recorder(httpx.Response(code, json=body))).chat("Writer", MSG, max_tokens=1024)
    assert isinstance(res.text, str) and res.text.strip()
    assert res.routed_model == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert res.usage["completion_tokens"] == 502
    assert res.model_call().routed_model == res.routed_model
    assert res.trace_fields()["meterless"]["routed_model"] == res.routed_model


def test_chat_sends_the_contract_headers_and_route(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=chat_body()))
    c = client(make_settings, rec, meterless_model_deep="meterless/deep")
    c.chat("Writer", MSG)
    req = rec.requests[0]
    sent = json.loads(req.content)
    assert req.headers["Authorization"] == f"Bearer {TOKEN}"
    assert req.headers["meterless-app"] == "hakken-agent"
    assert req.headers["meterless-scope"] == "user"
    assert sent["model"] == "meterless/deep" and sent["max_tokens"] >= MIN_MAX_TOKENS
    assert str(req.url).endswith("/v1/chat/completions")


def test_routed_model_prefers_receipt_then_winning_route_then_model(make_settings) -> None:
    def routed(receipt):
        rec = Recorder(httpx.Response(200, json=chat_body(model="top/level", receipt=receipt)))
        return client(make_settings, rec).chat("Planner", MSG).routed_model

    assert routed({"routed_model": "nvidia/a", "winning_route": {"model": "nvidia/b"}}) == "nvidia/a"
    assert routed({"winning_route": {"model": "nvidia/b"}, "provider_model": "meterless/auto"}) == "nvidia/b"
    assert routed(None) == "top/level"  # no receipt: degrade to response.model


def test_provider_model_is_never_taken_as_the_answering_model(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=chat_body(model="", receipt={"provider_model": "meterless/auto"})))
    assert client(make_settings, rec).chat("Planner", MSG).routed_model is None


def test_truncation_is_detected_by_token_count_even_when_finish_reason_says_stop(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=chat_body("half a sent", completion=2048, finish="stop")))
    with pytest.raises(TruncatedResponse) as exc:
        client(make_settings, rec).chat("Writer", MSG, max_tokens=2048)
    assert exc.value.completion_tokens == 2048 and exc.value.kind == "truncated"


def test_tight_max_tokens_is_refused_before_any_call(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=chat_body()))
    with pytest.raises(ValueError, match="below"):
        client(make_settings, rec).chat("Planner", MSG, max_tokens=16)
    assert rec.requests == []


@pytest.mark.parametrize("token", ["", "rt-local", "your-nightshift-runtime-token"])
def test_missing_or_placeholder_token_never_reaches_the_network(make_settings, token: str) -> None:
    rec = Recorder(httpx.Response(200, json=chat_body()))
    c = MeterlessClient(make_settings(meterless_runtime_token=token), transport=httpx.MockTransport(rec))
    with pytest.raises(MeterlessError) as exc:
        c.chat("Planner", MSG)
    assert exc.value.kind == "not_configured" and rec.requests == []


def test_unauthorized_chat_is_not_retried(make_settings) -> None:
    rec = Recorder(httpx.Response(401, json={"error": {"message": "unauthorized"}}))
    with pytest.raises(MeterlessError) as exc:
        client(make_settings, rec).chat("Planner", MSG)
    assert exc.value.kind == "unauthorized" and len(rec.requests) == 1


def test_upstream_failure_is_retried_a_bounded_number_of_times_and_names_the_culprit(make_settings) -> None:
    bad = httpx.Response(502, json={"error": {"meterless_detail": "nvidia/x_empty_response"}})
    rec = Recorder(bad)
    with pytest.raises(MeterlessError) as exc:
        client(make_settings, rec, max_retries=2).chat("Planner", MSG)
    assert exc.value.kind == "upstream" and exc.value.detail == "nvidia/x_empty_response"
    assert len(rec.requests) == 3  # 1 + max_retries, never unbounded


def test_upstream_blip_then_success(make_settings) -> None:
    rec = Recorder(httpx.Response(503, json={}), httpx.Response(200, json=chat_body("fine")))
    assert client(make_settings, rec).chat("Planner", MSG).text == "fine"
    assert len(rec.requests) == 2


def test_timeout_is_offline_and_not_retried(make_settings) -> None:
    rec = Recorder(httpx.ReadTimeout("slow"))
    with pytest.raises(MeterlessError) as exc:
        client(make_settings, rec, max_retries=2).chat("Planner", MSG)
    assert exc.value.kind == "offline" and len(rec.requests) == 1


def test_empty_content_is_an_error_not_an_answer(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=chat_body("   ")))
    with pytest.raises(MeterlessError, match="empty content"):
        client(make_settings, rec).chat("Planner", MSG)


def test_errors_never_contain_the_token(make_settings) -> None:
    rec = Recorder(httpx.Response(500, json={"error": {"message": "boom"}}))
    with pytest.raises(MeterlessError) as exc:
        client(make_settings, rec).chat("Planner", MSG)
    assert TOKEN not in str(exc.value)


# -- structured output -----------------------------------------------------------


class Pick(BaseModel):
    generic: str
    confidence: float


def test_chat_json_parses_the_recorded_bare_json(make_settings) -> None:
    code, body = recorded("chat_fast_json.json")
    obj, calls = client(make_settings, Recorder(httpx.Response(code, json=body))).chat_json("Executor", MSG, Pick)
    assert obj.generic == "famotidine" and len(calls) == 1


def test_chat_json_sends_the_schema_instruction(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=chat_body('{"generic": "x", "confidence": 0.5}')))
    client(make_settings, rec).chat_json("Executor", MSG, Pick)
    system = json.loads(rec.requests[0].content)["messages"][0]
    assert system["role"] == "system" and '"confidence"' in system["content"]


def test_chat_json_accepts_a_fenced_reply(make_settings) -> None:
    fenced = 'Here you go:\n```json\n{"generic": "warfarin", "confidence": 0.9}\n```'
    obj, _ = client(make_settings, Recorder(httpx.Response(200, json=chat_body(fenced)))).chat_json(
        "Executor", MSG, Pick)
    assert obj.generic == "warfarin"


def test_chat_json_repairs_exactly_once(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=chat_body('{"generic": "x"}')),
                   httpx.Response(200, json=chat_body('{"generic": "x", "confidence": 0.4}')))
    obj, calls = client(make_settings, rec).chat_json("Executor", MSG, Pick)
    assert obj.confidence == 0.4 and len(calls) == 2
    repair = json.loads(rec.requests[1].content)["messages"]
    assert repair[-2]["role"] == "assistant" and "did not validate" in repair[-1]["content"]


def test_chat_json_gives_up_after_one_repair(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=chat_body("not json at all")))
    with pytest.raises(MeterlessError) as exc:
        client(make_settings, rec).chat_json("Executor", MSG, Pick)
    assert exc.value.kind == "invalid_json" and len(rec.requests) == 2


# -- SAMPLE_MODE -----------------------------------------------------------------


def test_sample_mode_never_touches_the_network(make_settings) -> None:
    rec = Recorder(AssertionError("network used in SAMPLE_MODE"))
    c = client(make_settings, rec, sample_mode=True)
    res = c.chat("Writer", MSG, offline=lambda: "templated explanation")
    obj, calls = c.chat_json("Executor", MSG, Pick, offline=lambda: {"generic": "x", "confidence": 0.1})
    assert c.status().state == "offline"
    assert res.text == "templated explanation" and res.offline and res.routed_model == OFFLINE_MODEL
    assert obj.generic == "x" and calls[0].routed_model == OFFLINE_MODEL
    assert rec.requests == []


def test_sample_mode_without_an_offline_function_refuses_rather_than_inventing(make_settings) -> None:
    c = client(make_settings, Recorder(AssertionError("network")), sample_mode=True)
    with pytest.raises(MeterlessError) as exc:
        c.chat("Writer", MSG)
    assert exc.value.kind == "sample_mode"


def test_sample_mode_offline_output_is_still_schema_validated(make_settings) -> None:
    c = client(make_settings, Recorder(AssertionError("network")), sample_mode=True)
    with pytest.raises(Exception):
        c.chat_json("Executor", MSG, Pick, offline=lambda: {"generic": "x"})


# -- receipt and auto-detect -----------------------------------------------------


def test_receipt_summary_is_defensive() -> None:
    assert receipt_summary(None) == {}
    assert receipt_summary({"routing": "not a dict", "phases": "nope"}) == {}
    s = receipt_summary(recorded("chat_auto_text.json")[1]["meterless"])
    assert s["routed_model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert s["egress"] == {"destination": "nvidia"}


def test_auto_detect_returns_the_first_live_runtime(make_settings) -> None:
    models = recorded("models.json")[1]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "127.0.0.1" and request.url.port == 8090:
            return httpx.Response(200, json=models)
        raise httpx.ConnectError("refused")

    found = auto_detect(make_settings(meterless_runtime_token=TOKEN), transport=httpx.MockTransport(handler))
    assert found is not None and found[0] == "http://127.0.0.1:8090/v1" and found[1].state == "online"


def test_auto_detect_none_when_nothing_answers(make_settings) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    assert auto_detect(make_settings(), transport=httpx.MockTransport(handler)) is None


# -- failed calls stay visible (scan S9, CLAUDE.md rule 3) -------------------------


def test_invalid_json_keeps_both_answered_calls(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=chat_body("not json at all", model="nvidia/nemotron-a")))
    with pytest.raises(MeterlessError) as exc:
        client(make_settings, rec).chat_json("Writer", MSG, Pick)
    calls = exc.value.calls
    assert len(calls) == 2 and {c.routed_model for c in calls} == {"nvidia/nemotron-a"}
    assert all(c.model_call().role == "Writer" for c in calls)


def test_a_truncated_call_is_recorded_as_truncated_with_its_model(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=chat_body("cut", completion=MIN_MAX_TOKENS, model="nvidia/nemotron-b")))
    with pytest.raises(TruncatedResponse) as exc:
        client(make_settings, rec).chat("Writer", MSG, max_tokens=MIN_MAX_TOKENS)
    (call,) = exc.value.calls
    mc = call.model_call()
    assert mc.truncated and mc.routed_model == "nvidia/nemotron-b" and mc.tokens["completion_tokens"] == MIN_MAX_TOKENS
    assert call.trace_fields()["status"] == "error"


def test_an_upstream_failure_is_recorded_without_inventing_a_model(make_settings) -> None:
    rec = Recorder(httpx.Response(502, json={"error": "x"}))
    with pytest.raises(MeterlessError) as exc:
        client(make_settings, rec).chat("Evaluator", MSG)
    (call,) = exc.value.calls
    assert call.routed_model is None and call.error and call.model_call().role == "Evaluator"


def test_a_failure_on_the_repair_keeps_the_first_answer_too(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=chat_body("not json", model="nvidia/nemotron-a")),
                   httpx.Response(502, json={"error": "x"}))
    with pytest.raises(MeterlessError) as exc:
        client(make_settings, rec).chat_json("Writer", MSG, Pick)
    assert [c.routed_model for c in exc.value.calls] == ["nvidia/nemotron-a", None]


def test_nothing_sent_means_no_call_recorded(make_settings) -> None:
    c = MeterlessClient(make_settings(meterless_runtime_token=""), sleep=lambda _s: None)
    with pytest.raises(MeterlessError) as exc:
        c.chat("Writer", MSG)
    assert exc.value.kind == "not_configured" and exc.value.calls == []
