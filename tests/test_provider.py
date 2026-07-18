"""Phase 2 provider client tests with a mocked HTTP transport.

No test contacts a live LLM. The httpx transport is replaced with a
:class:`httpx.MockTransport` that returns canned responses.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

from autogovern.config_loader import ConfigNotFoundError, load_config
from autogovern.models import Config, ModelProviderConfig
from autogovern.provider import (
    MissingApiKeyError,
    ProviderClient,
    ProviderResponseError,
    ProviderUnreachableError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(api_key_env: str = "TEST_PROVIDER_KEY") -> Config:
    return Config(
        model_provider=ModelProviderConfig(
            api_base="https://provider.example.com/v1",
            model="test-model",
            api_key_env=api_key_env,
            temperature=0.0,
        )
    )


def _ok_response(content: str = "hello", *, json_mode: bool = False) -> bytes:
    if json_mode:
        # The content itself is a JSON string.
        content = json.dumps({"summary": content})
    body = {
        "choices": [
            {"message": {"role": "assistant", "content": content}},
        ],
    }
    return json.dumps(body).encode()


def _make_client(
    config: Config,
    handler: object,
    *,
    monkeypatch_key: str = "TEST_PROVIDER_KEY",
    key_value: str = "sk-test-key-do-not-log",
) -> ProviderClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    http_client = httpx.Client(transport=transport, timeout=30.0)
    os.environ[monkeypatch_key] = key_value
    return ProviderClient(config, client=http_client)


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------


def test_chat_sends_correct_request_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """The request hits /chat/completions with model, messages, and Bearer auth."""
    monkeypatch.setenv("TEST_PROVIDER_KEY", "sk-test-key-do-not-log")
    received: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["url"] = str(request.url)
        received["headers"] = dict(request.headers)
        received["body"] = json.loads(request.content)
        return httpx.Response(200, content=_ok_response("hello"))

    with _make_client(_config(), handler) as client:
        result = client.chat([{"role": "user", "content": "hi"}])

    assert result == "hello"
    assert received["url"] == "https://provider.example.com/v1/chat/completions"
    assert received["headers"]["authorization"] == "Bearer sk-test-key-do-not-log"
    assert received["headers"]["content-type"] == "application/json"
    body = received["body"]
    assert isinstance(body, dict)
    assert body["model"] == "test-model"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["temperature"] == 0.0


def test_chat_temperature_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "sk-test-key-do-not-log")
    received: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["body"] = json.loads(request.content)
        return httpx.Response(200, content=_ok_response("ok"))

    with _make_client(_config(), handler) as client:
        client.chat([{"role": "user", "content": "hi"}], temperature=0.7)

    body = received["body"]
    assert isinstance(body, dict)
    assert body["temperature"] == 0.7


# ---------------------------------------------------------------------------
# Key never logged
# ---------------------------------------------------------------------------


def test_api_key_never_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The API key value must never appear in any log output."""
    monkeypatch.setenv("TEST_PROVIDER_KEY", "sk-test-key-do-not-log")
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        # Trigger a retry to exercise the logging path.
        return httpx.Response(429, content=b'{"error": "rate limited"}')

    with (
        _make_client(_config(), handler, key_value="sk-secret-key-123") as client,
        pytest.raises((ProviderResponseError, ProviderUnreachableError)),
    ):
        client.chat([{"role": "user", "content": "hi"}])

    for record in caplog.records:
        assert "sk-secret-key-123" not in record.getMessage()


# ---------------------------------------------------------------------------
# Retry behaviour
# ---------------------------------------------------------------------------


def test_retries_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "sk-test-key-do-not-log")
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(429, content=b'{"error": "rate limited"}')
        return httpx.Response(200, content=_ok_response("recovered"))

    with _make_client(_config(), handler) as client:
        result = client.chat([{"role": "user", "content": "hi"}])

    assert call_count == 3
    assert result == "recovered"


def test_retries_on_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "sk-test-key-do-not-log")
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return httpx.Response(503, content=b'{"error": "unavailable"}')
        return httpx.Response(200, content=_ok_response("ok"))

    with _make_client(_config(), handler) as client:
        result = client.chat([{"role": "user", "content": "hi"}])

    assert call_count == 2
    assert result == "ok"


def test_no_retry_on_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client errors (4xx except 429) are not retried."""
    monkeypatch.setenv("TEST_PROVIDER_KEY", "sk-test-key-do-not-log")
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(400, content=b'{"error": "bad request"}')

    with (
        _make_client(_config(), handler) as client,
        pytest.raises(ProviderResponseError, match="400"),
    ):
        client.chat([{"role": "user", "content": "hi"}])

    assert call_count == 1


def test_retries_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transport-level failures are retried then raise ProviderUnreachableError."""
    monkeypatch.setenv("TEST_PROVIDER_KEY", "sk-test-key-do-not-log")
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("connection refused")

    with (
        _make_client(_config(), handler) as client,
        pytest.raises(ProviderUnreachableError, match="Could not reach"),
    ):
        client.chat([{"role": "user", "content": "hi"}])

    assert call_count == 4  # initial + 3 retries


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def test_chat_json_returns_parsed_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "sk-test-key-do-not-log")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ok_response("summarised", json_mode=True))

    with _make_client(_config(), handler) as client:
        result = client.chat_json([{"role": "user", "content": "summarise this"}])

    assert result == {"summary": "summarised"}


class _SummarySchema(BaseModel):
    summary: str


def test_chat_json_validates_against_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "sk-test-key-do-not-log")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ok_response("summarised", json_mode=True))

    with _make_client(_config(), handler) as client:
        result = client.chat_json([{"role": "user", "content": "summarise"}], schema=_SummarySchema)

    assert isinstance(result, _SummarySchema)
    assert result.summary == "summarised"


def test_chat_json_rejects_invalid_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "sk-test-key-do-not-log")

    def handler(request: httpx.Request) -> httpx.Response:
        # Valid JSON but wrong shape for the schema.
        body = json.dumps({"title": "no summary field"})
        return httpx.Response(200, content=_ok_response(body, json_mode=False))

    with (
        _make_client(_config(), handler) as client,
        pytest.raises(ProviderResponseError, match="did not validate"),
    ):
        client.chat_json([{"role": "user", "content": "summarise"}], schema=_SummarySchema)


def test_chat_json_rejects_non_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "sk-test-key-do-not-log")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ok_response("not json at all"))

    with (
        _make_client(_config(), handler) as client,
        pytest.raises(ProviderResponseError, match="not valid JSON"),
    ):
        client.chat_json([{"role": "user", "content": "hi"}])


def test_extracts_text_from_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "sk-test-key-do-not-log")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ok_response("extracted text"))

    with _make_client(_config(), handler) as client:
        result = client.chat([{"role": "user", "content": "hi"}])

    assert result == "extracted text"


def test_response_missing_choices_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "sk-test-key-do-not-log")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"error": "no choices"}).encode())

    with (
        _make_client(_config(), handler) as client,
        pytest.raises(ProviderResponseError, match="missing expected"),
    ):
        client.chat([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# Hard failure paths
# ---------------------------------------------------------------------------


def test_missing_api_key_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_PROVIDER_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ok_response("ok"))

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, timeout=30.0)
    client = ProviderClient(_config(), client=http_client)
    with pytest.raises(MissingApiKeyError, match="TEST_PROVIDER_KEY"):
        client.chat([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# Config loader: no config → exit non-zero with init remedy
# ---------------------------------------------------------------------------


def test_generate_with_no_config_exits_nonzero(tmp_path: Path) -> None:
    """`autogovern generate` with no config exits 1 and mentions init."""
    from typer.testing import CliRunner

    from autogovern.cli import app

    runner = CliRunner()
    # Run in a temp dir with no .autogovern/config.yaml.
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(app, ["generate"])
    finally:
        os.chdir(original_cwd)

    assert result.exit_code == 1
    assert "init" in result.output.lower()


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigNotFoundError, match="init"):
        load_config(tmp_path / ".autogovern" / "config.yaml")
