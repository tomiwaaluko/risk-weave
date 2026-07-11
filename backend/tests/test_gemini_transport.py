"""Unit tests for the live Gemini REST transport (RIS-24).

These are hermetic: urllib is monkeypatched, so no network or key is needed.
They pin the verified generateContent request/response contract and the
secrets-hygiene guarantee that the API key never appears in error output.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest
from pydantic import SecretStr

from riskweave_api.extraction.gemini import (
    GEMINI_EXTRACTION_MODEL,
    GeminiResponseError,
    GeminiRestTransport,
)
from riskweave_api.extraction.schemas import relationship_response_schema


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


# A recorded real v1beta/models/{model}:generateContent response shape.
_RECORDED_RESPONSE: dict[str, object] = {
    "candidates": [
        {
            "content": {"role": "model", "parts": [{"text": '{"relationships": []}'}]},
            "finishReason": "STOP",
        }
    ],
    "usageMetadata": {
        "promptTokenCount": 145,
        "candidatesTokenCount": 363,
        "totalTokenCount": 508,
    },
}


def test_transport_parses_generatecontent_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 60
        return _FakeHTTPResponse(_RECORDED_RESPONSE)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    response = GeminiRestTransport(SecretStr("server-only")).create_interaction(
        model=GEMINI_EXTRACTION_MODEL,
        input="prompt",
        temperature=0,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": relationship_response_schema(),
        },
    )
    assert response["output_text"] == '{"relationships": []}'
    assert response["usage"] == {"input_tokens": 145, "output_tokens": 363}


def test_transport_targets_generatecontent_endpoint_with_structured_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> _FakeHTTPResponse:
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        captured["headers"] = {k.lower(): v for k, v in request.header_items()}
        return _FakeHTTPResponse(_RECORDED_RESPONSE)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    schema = relationship_response_schema()
    GeminiRestTransport(SecretStr("secret-key-xyz")).create_interaction(
        model="gemini-3.5-flash",
        input="find relationships",
        temperature=0,
        response_format={"type": "text", "mime_type": "application/json", "schema": schema},
    )

    assert str(captured["url"]).endswith("/v1beta/models/gemini-3.5-flash:generateContent")
    body = captured["body"]
    assert body["contents"] == [{"role": "user", "parts": [{"text": "find relationships"}]}]
    generation_config = body["generationConfig"]
    assert generation_config["temperature"] == 0
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseJsonSchema"] == schema
    # The key travels in the header, never in the URL.
    assert "secret-key-xyz" not in str(captured["url"])
    assert captured["headers"]["x-goog-api-key"] == "secret-key-xyz"


def test_transport_never_leaks_api_key_in_error(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "AQ.super-secret-key-value"

    def fake_urlopen(request: object, timeout: int) -> None:
        # Worst case: the upstream error body echoes the key back.
        body = json.dumps({"error": {"message": f"invalid key {secret}"}}).encode()
        raise urllib.error.HTTPError("https://host/x", 400, "Bad Request", {}, io.BytesIO(body))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(GeminiResponseError) as excinfo:
        GeminiRestTransport(SecretStr(secret)).create_interaction(
            model="gemini-3.5-flash",
            input="prompt",
            temperature=0,
            response_format={"mime_type": "application/json", "schema": {}},
        )
    assert secret not in str(excinfo.value)
    assert secret not in "".join(excinfo.value.failures)


def test_transport_raises_when_response_has_no_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: int) -> _FakeHTTPResponse:
        return _FakeHTTPResponse({"promptFeedback": {"blockReason": "SAFETY"}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(GeminiResponseError):
        GeminiRestTransport(SecretStr("server-only")).create_interaction(
            model="gemini-3.5-flash",
            input="prompt",
            temperature=0,
            response_format={"mime_type": "application/json", "schema": {}},
        )
