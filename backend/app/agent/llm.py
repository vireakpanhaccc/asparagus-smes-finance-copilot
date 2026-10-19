"""LLM provider interface.

Content blocks are plain dicts (the agent loop's internal format):
  {"type": "text", "text": ...}
  {"type": "tool_use", "id": ..., "name": ..., "input": {...}}
The agent loop only ever sees this format. OpenAICompatProvider translates it to and
from the OpenAI chat-completions format, which Z.ai (GLM), Groq, OpenRouter and Ollama
all accept. FakeProvider replays scripted turns so tests run without an API key.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config import settings

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMUnavailable(Exception):
    """No model answered after all retries and fallbacks."""


@dataclass
class LLMResponse:
    content: list[dict[str, Any]]
    stop_reason: str = "end_turn"


class LLMProvider(Protocol):
    def complete(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResponse: ...


def get_provider() -> LLMProvider:
    """The model service configured in .env."""
    return OpenAICompatProvider()


class OpenAICompatProvider:
    """Any OpenAI-compatible /chat/completions endpoint (default: Z.ai GLM free tier).

    Tries LLM_MODEL, then each of LLM_FALLBACK_MODELS. Each model gets LLM_MAX_RETRIES
    retries with exponential backoff on 429 / 5xx / timeouts; any other error moves
    straight on to the next model.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        models: list[str] | None = None,
        extra_body: dict[str, Any] | None = None,
        max_retries: int | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.url = (base_url or settings.llm_base_url).rstrip("/") + "/chat/completions"
        self.api_key = settings.llm_api_key if api_key is None else api_key
        self.models = models or [settings.llm_model, *settings.fallback_models]
        self.extra_body = settings.llm_extra_body_dict if extra_body is None else extra_body
        self.max_retries = settings.llm_max_retries if max_retries is None else max_retries
        self.client = httpx.Client(timeout=settings.llm_timeout_seconds, transport=transport)
        self.sleep = sleep

    def complete(self, *, system, messages, tools) -> LLMResponse:
        body = {
            "messages": to_openai_messages(system, messages),
            "tools": [to_openai_tool(t) for t in tools],
            "max_tokens": 1500,
            **self.extra_body,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_error = "no model configured"
        for model in self.models:
            for attempt in range(self.max_retries + 1):
                try:
                    r = self.client.post(self.url, json={"model": model, **body}, headers=headers)
                except httpx.TimeoutException:
                    last_error = f"{model}: timeout"
                except httpx.TransportError as err:
                    last_error = f"{model}: {type(err).__name__}"
                else:
                    if r.status_code == 200:
                        return from_openai_response(r.json())
                    last_error = f"{model}: HTTP {r.status_code}"
                    if r.status_code not in RETRYABLE_STATUS:
                        break  # e.g. unknown model: no point retrying it
                if attempt < self.max_retries:
                    self.sleep(1.5 * 2**attempt)
        raise LLMUnavailable(last_error)


def to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }


def to_openai_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
            continue
        texts = [b["text"] for b in content if b.get("type") == "text"]
        if m["role"] == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": "\n".join(texts)}
            calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b.get("input", {}))},
                }
                for b in content
                if b.get("type") == "tool_use"
            ]
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        else:  # user turn: tool results become "tool" messages
            for b in content:
                if b.get("type") == "tool_result":
                    out.append(
                        {"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]}
                    )
            if texts:
                out.append({"role": "user", "content": "\n".join(texts)})
    return out


def from_openai_response(data: dict[str, Any]) -> LLMResponse:
    msg = data["choices"][0]["message"]
    blocks: list[dict[str, Any]] = []
    if msg.get("content"):
        blocks.append({"type": "text", "text": msg["content"]})
    calls = msg.get("tool_calls") or []
    for i, call in enumerate(calls):
        fn = call.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}  # the policy engine's input validation then decides
        blocks.append(
            {
                "type": "tool_use",
                "id": call.get("id") or f"call_{i}",
                "name": fn.get("name", ""),
                "input": args if isinstance(args, dict) else {},
            }
        )
    return LLMResponse(blocks, "tool_use" if calls else "end_turn")


class FakeProvider:
    """Returns scripted responses in order. Used by tests and offline demos."""

    def __init__(self, script: list[list[dict[str, Any]]]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, system, messages, tools) -> LLMResponse:
        self.calls.append({"system": system, "messages": list(messages), "tools": tools})
        if not self.script:
            return LLMResponse([{"type": "text", "text": "(no more scripted turns)"}])
        return LLMResponse(self.script.pop(0))
