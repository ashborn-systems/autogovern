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
    """Return a canned FreeTextSummary JSON for any chat request."""
    content = json.dumps({"data_categories": ["personal"]})
    body = {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
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
