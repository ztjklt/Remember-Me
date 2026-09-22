"""HTTP adapter for providers exposing an OpenAI-compatible chat endpoint."""

from __future__ import annotations

import json
from typing import Any

import httpx

from ..errors import AIOutputInvalid, ProviderTimeout, ProviderUnavailable
from .base import ModelRequest


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
        )

    def generate(self, request: ModelRequest) -> dict[str, Any]:
        body = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        request.payload.model_dump(exclude_none=True),
                        ensure_ascii=False,
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "remember_me_ai_core_output",
                    "strict": True,
                    "schema": request.response_schema,
                },
            },
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = self._client.post("chat/completions", json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("AI provider request timed out") from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailable("AI provider connection failed") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailable("AI provider transport failed") from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if response.status_code >= 500:
                raise ProviderUnavailable(
                    f"AI provider returned HTTP {response.status_code}"
                ) from exc
            raise AIOutputInvalid(
                f"AI provider rejected the structured request with HTTP {response.status_code}"
            ) from exc

        try:
            envelope = response.json()
        except ValueError as exc:
            raise AIOutputInvalid("AI provider returned invalid JSON") from exc

        try:
            content = envelope["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIOutputInvalid("AI provider response is missing message content") from exc

        if isinstance(content, str):
            try:
                output = json.loads(content)
            except json.JSONDecodeError as exc:
                raise AIOutputInvalid("AI provider message content is not valid JSON") from exc
        else:
            output = content

        if not isinstance(output, dict):
            raise AIOutputInvalid("AI provider structured output must be a JSON object")
        return output


__all__ = ["OpenAICompatibleProvider"]
