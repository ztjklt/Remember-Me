"""HTTP adapter for providers exposing an OpenAI-compatible chat endpoint."""

from __future__ import annotations

import json
from typing import Any

import httpx

from ..errors import AIOutputInvalid, ProviderTimeout, ProviderUnavailable
from .base import ModelRequest


def _strict_schema(value: Any) -> Any:
    """A provider-only projection; the shared integration schema is unchanged.

    Nullable optional fields become required. Phase 1 does not generate free-form
    metadata or future updates, so open objects are restricted to empty objects.
    """
    if isinstance(value, list):
        return [_strict_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: _strict_schema(item) for key, item in value.items() if key != "default"}
    if result.get("type") == "object":
        result.setdefault("properties", {})
        result["required"] = list(result["properties"])
        result["additionalProperties"] = False
    return result


def _reject_non_json_number(value: str) -> None:
    raise ValueError("Non-finite numbers are not valid JSON")


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 30.0,
        max_response_bytes: int = 1_048_576,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def generate(self, request: ModelRequest) -> dict[str, Any]:
        versions = json.dumps({
            "model_version": request.model_version,
            "prompt_version": request.prompt_version,
            "schema_version": request.schema_version,
        })
        body = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt + "\nDeployment versions: " + versions},
                {
                    "role": "user",
                    "content": json.dumps(
                        # No verified context-evidence resolver exists in Phase 1.
                        # Keep subject_context, subject_id and trace_id local.
                        {"episode_id": request.payload.episode_id, "transcript": request.payload.transcript},
                        ensure_ascii=True,
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "remember_me_ai_core_output",
                    "strict": True,
                    "schema": _strict_schema(request.response_schema),
                },
            },
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            with self._client.stream(
                "POST", self.base_url + "chat/completions", json=body, headers=headers,
                timeout=self.timeout_seconds, follow_redirects=False,
            ) as response:
                if response.status_code in {408, 504}:
                    raise ProviderTimeout("AI provider request timed out")
                if response.status_code == 429 or response.status_code >= 500:
                    raise ProviderUnavailable("AI provider is temporarily unavailable")
                if not response.is_success:
                    raise AIOutputInvalid("AI provider rejected the structured request")
                chunks = bytearray()
                for chunk in response.iter_bytes(chunk_size=65_536):
                    if len(chunks) + len(chunk) > self.max_response_bytes:
                        raise AIOutputInvalid("AI provider response exceeds the configured size limit")
                    chunks.extend(chunk)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("AI provider request timed out") from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailable("AI provider connection failed") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailable("AI provider transport failed") from exc

        try:
            envelope = json.loads(chunks, parse_constant=_reject_non_json_number)
        except (ValueError, RecursionError) as exc:
            raise AIOutputInvalid("AI provider returned invalid JSON") from exc

        try:
            choice = envelope["choices"][0]
            message = choice["message"]
            if choice.get("finish_reason") != "stop" or message.get("refusal"):
                raise AIOutputInvalid("AI provider did not complete structured extraction")
            content = message["content"]
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise AIOutputInvalid("AI provider response is missing message content") from exc

        if isinstance(content, str):
            try:
                output = json.loads(content, parse_constant=_reject_non_json_number)
            except (ValueError, RecursionError) as exc:
                raise AIOutputInvalid("AI provider message content is not valid JSON") from exc
        else:
            output = content

        if not isinstance(output, dict):
            raise AIOutputInvalid("AI provider structured output must be a JSON object")
        return output


__all__ = ["OpenAICompatibleProvider"]
