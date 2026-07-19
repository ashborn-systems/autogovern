"""Provider client: OpenAI-compatible chat completions over httpx.

A deep module with a small interface. The key is read from the environment
variable named in the config (``api_key_env``) at call time and never written
to disk, logs, or manifests.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from autogovern.models import Config

logger = logging.getLogger(__name__)

# Retryable HTTP status codes: rate-limited and server errors.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# Retry defaults. Exponential backoff with a cap.
_MAX_RETRIES = 3
_INITIAL_BACKOFF_SECONDS = 0.5
_MAX_BACKOFF_SECONDS = 5.0


class ProviderError(Exception):
    """Base error for provider failures."""


class MissingApiKeyError(ProviderError):
    """The configured environment variable is not set."""


class ProviderUnreachableError(ProviderError):
    """The provider endpoint could not be reached."""


class ProviderResponseError(ProviderError):
    """The provider returned a malformed or error response."""


class ProviderClient:
    """OpenAI-compatible chat completions client.

    The interface is intentionally small: callers pass messages and receive
    either the raw text or a parsed, validated JSON object. Auth, retry,
    and transport details stay inside.
    """

    def __init__(
        self,
        config: Config,
        *,
        client: httpx.Client | None = None,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self._config = config
        self._max_retries = max_retries
        self._client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None
        self._usage_prompt = 0
        self._usage_completion = 0
        self._usage_total = 0
        self._usage_reported = False
        self._call_log: list[dict[str, Any]] = []

    @property
    def total_usage(self) -> dict[str, int | None] | None:
        """Aggregated token usage across all calls on this client.

        Returns None when the provider never reported usage (counts are
        never fabricated). Individual fields are None when that count was
        not reported.
        """
        if not self._usage_reported:
            return None
        return {
            "prompt": self._usage_prompt if self._usage_prompt else None,
            "completion": self._usage_completion if self._usage_completion else None,
            "total": self._usage_total if self._usage_total else None,
        }

    @property
    def call_log(self) -> list[dict[str, Any]]:
        """Per-call usage records, attributed to the pipeline stage that made them."""
        return list(self._call_log)

    def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> ProviderClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        label: str = "",
    ) -> str:
        """Send a chat completion request and return the assistant's text.

        Args:
            messages: OpenAI-style message list (role + content).
            temperature: Override the config temperature for this call.
            label: Attribution for per-call token tracking (e.g. "system-card").

        Returns:
            The assistant's message content as a string.
        """
        payload = self._build_payload(messages, temperature)
        response_body = self._request_with_retry(payload, label=label)
        return self._extract_text(response_body)

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        schema: type[BaseModel] | None = None,
        label: str = "",
    ) -> Any:
        """Send a chat completion request and return parsed JSON.

        The request asks the model for a JSON object. If ``schema`` is given,
        the response is validated against that pydantic model and returned as
        an instance; otherwise the raw parsed JSON is returned.

        Args:
            messages: OpenAI-style message list.
            temperature: Override the config temperature for this call.
            schema: Optional pydantic model to validate the response against.
            label: Attribution for per-call token tracking (e.g. "normalise").

        Returns:
            A validated model instance if ``schema`` is given, else a parsed
            JSON object (typically a dict).
        """
        messages = [*messages, {"role": "user", "content": "Respond with valid JSON only."}]
        payload = self._build_payload(messages, temperature, json_mode=True)
        response_body = self._request_with_retry(payload, label=label)
        text = self._extract_text(response_body)
        parsed = self._parse_json(text)
        if schema is not None:
            try:
                return schema.model_validate(parsed)
            except ValidationError as exc:
                raise ProviderResponseError(
                    f"Provider response did not validate against {schema.__name__}: {exc}"
                ) from exc
        return parsed

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        temperature: float | None,
        *,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        provider = self._config.model_provider
        payload: dict[str, Any] = {
            "model": provider.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else provider.temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _request_with_retry(self, payload: dict[str, Any], *, label: str = "") -> dict[str, Any]:
        url = f"{self._config.model_provider.api_base.rstrip('/')}/chat/completions"
        headers = self._build_headers()

        backoff = _INITIAL_BACKOFF_SECONDS
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.warning(
                    "Provider request failed (attempt %d/%d): %s",
                    attempt + 1,
                    self._max_retries + 1,
                    exc.__class__.__name__,
                )
                if attempt < self._max_retries:
                    time.sleep(min(backoff, _MAX_BACKOFF_SECONDS))
                    backoff *= 2
                    continue
                raise ProviderUnreachableError(f"Could not reach provider at {url}: {exc}") from exc

            if response.status_code in _RETRYABLE_STATUS and attempt < self._max_retries:
                logger.warning(
                    "Provider returned %d (attempt %d/%d), retrying",
                    response.status_code,
                    attempt + 1,
                    self._max_retries + 1,
                )
                time.sleep(min(backoff, _MAX_BACKOFF_SECONDS))
                backoff *= 2
                continue

            if response.status_code != 200:
                raise ProviderResponseError(
                    f"Provider returned HTTP {response.status_code}: {response.text[:500]}"
                )

            try:
                result: dict[str, Any] = response.json()
            except json.JSONDecodeError as exc:
                raise ProviderResponseError(f"Provider returned non-JSON body: {exc}") from exc
            usage = result.get("usage")
            if isinstance(usage, dict):
                self._record_usage(usage, label=label)
            return result

        # Unreachable, but keeps mypy happy.
        raise ProviderUnreachableError(f"Exhausted retries contacting provider: {last_exc}")

    def _record_usage(self, usage: dict[str, Any], *, label: str = "") -> None:
        """Accumulate a response's usage block, when the provider sends one."""
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        total = usage.get("total_tokens")
        if not any(isinstance(v, int) for v in (prompt, completion, total)):
            return
        self._usage_reported = True
        self._usage_prompt += prompt if isinstance(prompt, int) else 0
        self._usage_completion += completion if isinstance(completion, int) else 0
        self._usage_total += total if isinstance(total, int) else 0
        self._call_log.append(
            {
                "label": label,
                "prompt": prompt if isinstance(prompt, int) else None,
                "completion": completion if isinstance(completion, int) else None,
                "total": total if isinstance(total, int) else None,
            }
        )

    def _build_headers(self) -> dict[str, str]:
        key = self._read_key()
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _read_key(self) -> str:
        env_var = self._config.model_provider.api_key_env
        key = os.environ.get(env_var)
        if not key:
            raise MissingApiKeyError(
                f"Environment variable {env_var} is not set. Set it to your provider API key."
            )
        return key

    def _extract_text(self, body: dict[str, Any]) -> str:
        try:
            choices = body["choices"]
            content = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(
                f"Provider response missing expected choices/message/content: {exc}"
            ) from exc
        if not isinstance(content, str):
            raise ProviderResponseError(
                f"Provider returned non-string content: {type(content).__name__}"
            )
        return content

    def _parse_json(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(f"Provider response was not valid JSON: {exc}") from exc


def build_provider(config: Config) -> ProviderClient:
    """Construct a ProviderClient from config.

    This factory is the seam tests monkeypatch to inject a mocked transport
    without touching the CLI's config-loading logic.
    """
    return ProviderClient(config)


__all__ = [
    "MissingApiKeyError",
    "ProviderClient",
    "ProviderError",
    "ProviderResponseError",
    "ProviderUnreachableError",
    "build_provider",
]
