"""Local Ollama adapter for the isolated iOS branch.

Ollama's native API supports JSON Schema output and `think: false`. This is an
optional adapter; the existing OpenAI-compatible provider stays unchanged.
"""

import json
import re
from typing import Any

import httpx
from opencc import OpenCC

from ..errors import AIOutputInvalid, ProviderTimeout, ProviderUnavailable
from .base import ModelRequest
from .openai_compatible import _reject_non_json_number, _strict_schema


def _source_excerpts(transcript: str) -> list[str]:
    """Offer bounded, exact clauses to the local model for grounded quoting."""
    excerpts = []
    for match in re.finditer(r"[^,，。.!！？?；;\n]+", transcript):
        excerpt = match.group().strip()
        if excerpt and excerpt not in excerpts:
            excerpts.append(excerpt)
    if len(excerpts) > 64 or sum(map(len, excerpts)) > 8192:
        return []
    return excerpts


class OllamaLocalProvider:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        max_response_bytes: int,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._chinese_converter = OpenCC("t2s.json")

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def generate(self, request: ModelRequest) -> dict[str, Any]:
        excerpts = _source_excerpts(request.payload.transcript)
        response_schema = _strict_schema(request.response_schema)
        if excerpts:
            response_schema["$defs"]["Evidence"]["properties"]["excerpt"] = {
                "type": "string", "enum": excerpts,
            }
        versions = json.dumps({
            "model_version": request.model_version,
            "prompt_version": request.prompt_version,
            "schema_version": request.schema_version,
        })
        body = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt + "\nDeployment versions: " + versions + ("\nCopy each evidence excerpt exactly from the allowed source clauses." if excerpts else "")},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"episode_id": request.payload.episode_id, "transcript": request.payload.transcript},
                        ensure_ascii=True,
                    ),
                },
            ],
            "stream": False,
            "think": False,
            "format": response_schema,
            "options": {"temperature": 0},
        }
        try:
            with self._client.stream(
                "POST", f"{self.base_url}/api/chat", json=body,
                timeout=self.timeout_seconds, follow_redirects=False,
            ) as response:
                if response.status_code in (408, 504):
                    raise ProviderTimeout("Local model timed out")
                if response.status_code == 429 or response.status_code >= 500:
                    raise ProviderUnavailable("Local model unavailable")
                if not response.is_success:
                    raise AIOutputInvalid("Local model rejected structured request")
                chunks = bytearray()
                for chunk in response.iter_bytes(chunk_size=65_536):
                    if len(chunks) + len(chunk) > self.max_response_bytes:
                        raise AIOutputInvalid("Local model response too large")
                    chunks.extend(chunk)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("Local model timed out") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailable("Local model connection failed") from exc
        try:
            envelope = json.loads(chunks, parse_constant=_reject_non_json_number)
            if envelope.get("done") is not True:
                raise AIOutputInvalid("Local model did not finish")
            content = envelope["message"]["content"]
            output = json.loads(content, parse_constant=_reject_non_json_number)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise AIOutputInvalid("Local model returned invalid structured output") from exc
        if not isinstance(output, dict):
            raise AIOutputInvalid("Local model output must be an object")
        # Small local models often count CJK spans incorrectly or convert a
        # Traditional STT transcript to Simplified. Re-anchor only when an
        # excerpt has one exact occurrence after one-to-one conversion. Copy
        # the original transcript text into the evidence; ambiguous or changed
        # length conversions still fail strict provenance validation.
        evidences = output.get("evidence")
        transcript = request.payload.transcript
        normalized_transcript: str | None = None
        for evidence in evidences if isinstance(evidences, list) else []:
            if not isinstance(evidence, dict):
                continue
            excerpt = evidence.get("excerpt")
            if not isinstance(excerpt, str) or not excerpt.strip():
                continue
            if transcript.count(excerpt) == 1:
                start = transcript.index(excerpt)
            else:
                if normalized_transcript is None:
                    converted = [self._chinese_converter.convert(char) for char in transcript]
                    normalized_transcript = (
                        "".join(converted) if all(len(char) == 1 for char in converted) else ""
                    )
                normalized_excerpt = "".join(
                    self._chinese_converter.convert(char) for char in excerpt
                )
                if (
                    not normalized_transcript
                    or len(normalized_excerpt) != len(excerpt)
                    or normalized_transcript.count(normalized_excerpt) != 1
                ):
                    continue
                start = normalized_transcript.index(normalized_excerpt)
            end = start + len(excerpt)
            evidence["excerpt"] = transcript[start:end]
            evidence["span_start"] = start
            evidence["span_end"] = end
            evidence["source_ref"] = f"episode:{request.payload.episode_id}#span:{start}-{end}"
        return output
