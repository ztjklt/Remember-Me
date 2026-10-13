"""DeepSeek Flash chat adapter with locally verified transcript evidence."""

from __future__ import annotations

import json

import httpx

from ..errors import AIOutputInvalid, ProviderTimeout, ProviderUnavailable
from .base import ModelRequest
from .ollama import DOMAINS, PROMPT, TYPES, grounded_result


class DeepSeekProvider:
    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float,
                 max_response_bytes: int = 1_048_576,
                 client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds, trust_env=False)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    @staticmethod
    def response_model_version(output: dict) -> str:
        """Use the API envelope's model, never a model-supplied version string."""
        version = output.get("model_version")
        if not isinstance(version, str) or not version.startswith("deepseek-"):
            raise AIOutputInvalid("DeepSeek response omitted its model identity")
        return version

    def generate(self, request: ModelRequest) -> dict:
        example = {"memories": [{"quote": "我喜欢散步", "statement": "喜欢散步",
                                 "domain": "PREFERENCES", "memory_type": "PREFERENCE",
                                 "confidence": 0.8}]}
        system = (PROMPT + " 只返回 JSON 对象，结构如 "
                  + json.dumps(example, ensure_ascii=False)
                  + "。允许的 domain: " + ", ".join(DOMAINS)
                  + "；允许的 memory_type: " + ", ".join(TYPES)
                  + "。只有输入里确实包含 quote 才能输出该项。")
        body = {
            "model": request.model,
            "thinking": {"type": "disabled"},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": request.payload.transcript}],
            "response_format": {"type": "json_object"},
            "max_tokens": 2048,
            "temperature": 0,
        }
        try:
            with self._client.stream(
                "POST", self.base_url + "/chat/completions", json=body,
                headers={"Authorization": "Bearer " + self.api_key,
                         "Content-Type": "application/json"},
                timeout=self.timeout_seconds, follow_redirects=False,
            ) as response:
                if response.status_code in {408, 504}:
                    raise ProviderTimeout("DeepSeek timed out")
                if response.status_code in {429} or response.status_code >= 500:
                    raise ProviderUnavailable("DeepSeek is temporarily unavailable")
                if not response.is_success:
                    raise ProviderUnavailable("DeepSeek rejected the request")
                chunks = bytearray()
                for chunk in response.iter_bytes(chunk_size=65_536):
                    if len(chunks) + len(chunk) > self.max_response_bytes:
                        raise AIOutputInvalid("DeepSeek response exceeds configured size limit")
                    chunks.extend(chunk)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("DeepSeek timed out") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailable("DeepSeek connection failed") from exc

        try:
            envelope = json.loads(chunks)
            choice = envelope["choices"][0]
            message = choice["message"]
            if choice.get("finish_reason") != "stop" or message.get("refusal"):
                raise AIOutputInvalid("DeepSeek did not complete extraction")
            version = envelope["model"]
            if not isinstance(version, str) or not version.startswith("deepseek-"):
                raise AIOutputInvalid("DeepSeek response omitted its model identity")
            raw = json.loads(message["content"])
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise AIOutputInvalid("DeepSeek returned invalid JSON") from exc
        return grounded_result(raw, request, model_version=version)


__all__ = ["DeepSeekProvider"]
