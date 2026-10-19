"""OpenAI-compatible provider: format translation, retries and model fallback (no network)."""

import json

import httpx
import pytest

from app.agent.llm import LLMUnavailable, OpenAICompatProvider, to_openai_messages

TOOLS = [{"name": "forecast_cash_flow", "description": "[read_only] Forecast",
          "input_schema": {"type": "object", "properties": {"weeks": {"type": "integer"}}}}]


def _reply(message: dict) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": message}]})


def _provider(handler, models=("model-a",), sleeps=None) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        base_url="https://llm.test/v4", api_key="test-key", models=list(models),
        extra_body={"thinking": {"type": "disabled"}}, max_retries=2,
        transport=httpx.MockTransport(handler),
        sleep=(sleeps.append if sleeps is not None else lambda _s: None),
    )


def _complete(provider):
    return provider.complete(system="sys", messages=[{"role": "user", "content": "hi"}],
                             tools=TOOLS)


def test_tool_round_trip_is_translated_to_openai_format():
    messages = [
        {"role": "user", "content": "Can I cover payroll?"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "Checking."},
            {"type": "tool_use", "id": "t1", "name": "forecast_cash_flow", "input": {"weeks": 8}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": '{"status": "ok"}'},
        ]},
    ]
    out = to_openai_messages("sys", messages)
    assert out[0] == {"role": "system", "content": "sys"}
    assert out[2]["tool_calls"][0]["function"] == {
        "name": "forecast_cash_flow", "arguments": '{"weeks": 8}'}
    assert out[3] == {"role": "tool", "tool_call_id": "t1", "content": '{"status": "ok"}'}


def test_request_carries_tools_extra_body_and_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return _reply({"content": "ok"})

    _complete(_provider(handler))
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == "model-a"
    assert seen["body"]["thinking"] == {"type": "disabled"}
    assert seen["body"]["tools"][0]["function"]["name"] == "forecast_cash_flow"


def test_tool_calls_are_parsed_and_bad_arguments_become_empty():
    resp = _complete(_provider(lambda _r: _reply({"content": "", "tool_calls": [
        {"id": "c1", "function": {"name": "forecast_cash_flow", "arguments": '{"weeks": 8}'}},
        {"id": "c2", "function": {"name": "forecast_cash_flow", "arguments": "{not json"}},
    ]})))
    assert resp.stop_reason == "tool_use"
    assert [b["input"] for b in resp.content] == [{"weeks": 8}, {}]


def test_busy_model_is_retried_with_backoff():
    codes, sleeps = iter([429, 503, 200]), []

    def handler(_r):
        code = next(codes)
        return _reply({"content": "ok"}) if code == 200 else httpx.Response(code)

    resp = _complete(_provider(handler, sleeps=sleeps))
    assert resp.content == [{"type": "text", "text": "ok"}]
    assert sleeps == [1.5, 3.0]


def test_falls_back_to_next_model():
    tried = []

    def handler(request):
        model = json.loads(request.content)["model"]
        tried.append(model)
        return httpx.Response(429) if model == "model-a" else _reply({"content": "from b"})

    resp = _complete(_provider(handler, models=("model-a", "model-b")))
    assert resp.content[0]["text"] == "from b"
    assert tried == ["model-a"] * 3 + ["model-b"]


def test_non_retryable_error_skips_straight_to_next_model():
    tried = []

    def handler(request):
        model = json.loads(request.content)["model"]
        tried.append(model)
        return httpx.Response(400) if model == "retired" else _reply({"content": "ok"})

    _complete(_provider(handler, models=("retired", "model-b")))
    assert tried == ["retired", "model-b"]


def test_raises_when_every_model_is_busy():
    with pytest.raises(LLMUnavailable, match="HTTP 429"):
        _complete(_provider(lambda _r: httpx.Response(429), models=("a", "b")))
