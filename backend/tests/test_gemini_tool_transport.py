"""Unit tests for the Gemini function-calling transport (RIS-19, `RW-AI-002`).

Hermetic: urllib is monkeypatched, so no network or key is needed. They pin the
function-calling request/response contract — abstract Q&A turns render to Gemini
``contents``, the closed registry travels as ``functionDeclarations``, and one
turn normalizes to either a function call or a final answer — plus the
secrets-hygiene guarantee shared with the extraction transport.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest
from pydantic import SecretStr

from riskweave_api.extraction.gemini import GeminiResponseError, GeminiToolTransport


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


_FUNCTION_CALL_RESPONSE = {
    "candidates": [
        {
            "content": {
                "role": "model",
                "parts": [{"functionCall": {"name": "resolve_entity", "args": {"name": "Boston"}}}],
            }
        }
    ]
}

_TEXT_RESPONSE = {
    "candidates": [
        {"content": {"role": "model", "parts": [{"text": '{"answer": "ok", "citations": []}'}]}}
    ],
    "usageMetadata": {"promptTokenCount": 42, "candidatesTokenCount": 7},
}


def test_parses_function_call_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: _FakeHTTPResponse(_FUNCTION_CALL_RESPONSE),
    )
    turn = GeminiToolTransport(SecretStr("server-only")).create_tool_interaction(
        model="gemini-3.1-pro-preview",
        messages=[{"kind": "user_text", "text": "hi"}],
        tools=[{"name": "resolve_entity"}],
        temperature=0,
    )
    assert turn == {
        "function_call": {"name": "resolve_entity", "args": {"name": "Boston"}},
        "usage": {},
    }


def test_parses_final_answer_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda request, timeout: _FakeHTTPResponse(_TEXT_RESPONSE)
    )
    turn = GeminiToolTransport(SecretStr("server-only")).create_tool_interaction(
        model="gemini-3.1-pro-preview",
        messages=[],
        tools=[],
        temperature=0,
    )
    assert turn == {
        "output_text": '{"answer": "ok", "citations": []}',
        "usage": {"input_tokens": 42, "output_tokens": 7},
    }


def test_renders_turns_to_contents_and_attaches_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> _FakeHTTPResponse:
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        return _FakeHTTPResponse(_TEXT_RESPONSE)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    GeminiToolTransport(SecretStr("k")).create_tool_interaction(
        model="gemini-3.1-pro-preview",
        messages=[
            {"kind": "user_text", "text": "why?"},
            {"kind": "model_call", "name": "resolve_entity", "args": {"name": "b"}},
            {"kind": "tool_result", "name": "resolve_entity", "response": {"node_id": "b"}},
            {"kind": "tool_error", "name": "bad", "error": "refused"},
        ],
        tools=[{"name": "resolve_entity"}],
        temperature=0,
    )

    body = captured["body"]
    assert str(captured["url"]).endswith(":generateContent")
    assert body["tools"] == [{"functionDeclarations": [{"name": "resolve_entity"}]}]
    roles = [c["role"] for c in body["contents"]]
    assert roles == ["user", "model", "user", "user"]
    assert body["contents"][1]["parts"][0]["functionCall"]["name"] == "resolve_entity"
    assert body["contents"][2]["parts"][0]["functionResponse"]["response"] == {"node_id": "b"}
    assert body["contents"][3]["parts"][0]["functionResponse"]["response"] == {"error": "refused"}


def test_never_leaks_api_key_in_error(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "AQ.super-secret"

    def fake_urlopen(request: object, timeout: int) -> None:
        body = json.dumps({"error": {"message": f"invalid {secret}"}}).encode()
        raise urllib.error.HTTPError("https://host/x", 400, "Bad", {}, io.BytesIO(body))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(GeminiResponseError) as excinfo:
        GeminiToolTransport(SecretStr(secret)).create_tool_interaction(
            model="gemini-3.1-pro-preview", messages=[], tools=[], temperature=0
        )
    assert secret not in str(excinfo.value)
