"""Shared fixtures for scan tests.

The mocked provider returns a canned FreeTextSummary so no test contacts a
live LLM. The same pattern (httpx.MockTransport) is used as in test_provider.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from autogovern.models import Config, ModelProviderConfig
from autogovern.provider import ProviderClient

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# The env var named by mock_config; set so the provider's key read succeeds.
_MOCK_KEY_ENV = "AUTOGOVERN_TEST_KEY"
_MOCK_KEY_VALUE = "sk-test-not-a-real-key"


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Return canned responses for scan, generation, and verification calls.

    Detection uses the ``response_format`` flag (set by ``chat_json``) plus
    message content: verification prompts mention "verify". This keeps a
    single mock serving all three LLM seams reliably, even when the style
    authority text happens to contain words like "summary".
    """
    payload = json.loads(request.content)
    messages = payload.get("messages", [])
    combined = " ".join(m.get("content", "") for m in messages).lower()
    is_json = payload.get("response_format") is not None

    if is_json and "verify" in combined:
        # All-supported: no claims, no findings. Verifier-specific tests
        # build their own mocks for the unsupported-claim case.
        content = json.dumps({"section": "", "claims": [], "rubric_findings": []})
    else:
        # Summarisation (chat_json, no "verify") and generation (chat) both
        # get the canned FreeTextSummary-shaped content.
        content = json.dumps({"data_categories": ["personal"]})

    body = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    return httpx.Response(200, content=json.dumps(body).encode())


def make_mock_provider(config: Config | None = None) -> ProviderClient:
    """Build a ProviderClient backed by a MockTransport.

    Each call returns a fresh client the caller is responsible for closing
    (or pass it to scan_repo, which leaves externally-supplied clients open).
    """
    cfg = config or mock_config()
    transport = httpx.MockTransport(_mock_handler)
    http_client = httpx.Client(transport=transport, timeout=30.0)
    return ProviderClient(cfg, client=http_client)


def mock_config() -> Config:
    """A minimal Config pointing at a mocked provider."""
    return Config(
        model_provider=ModelProviderConfig(
            api_base="https://mock-provider.example.com/v1",
            model="mock-model",
            api_key_env=_MOCK_KEY_ENV,
            temperature=0.0,
        )
    )


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def mock_config_fixture() -> Config:
    return mock_config()


@pytest.fixture
def mock_provider() -> ProviderClient:
    """A ready mocked provider for library-level scan tests."""
    os.environ[_MOCK_KEY_ENV] = _MOCK_KEY_VALUE
    client = make_mock_provider()
    yield client
    client.close()


@pytest.fixture
def provider_factory():
    """A factory returning fresh mocked providers, for CLI monkeypatching."""
    os.environ[_MOCK_KEY_ENV] = _MOCK_KEY_VALUE
    return make_mock_provider
