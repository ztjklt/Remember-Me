"""One transport to schema workers; retries belong to Job or explicit user retry."""

import httpx
from pydantic import ValidationError
from remember_contracts.agent import Comparison, PersonaResult, TwinAnswer
from .errors import AiFailed, AiSchemaInvalid, AiTimeout, AiUnavailable


class AgentClient:
    def __init__(self, base_url, timeout_seconds=45):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def call(self, task, payload, result_type):
        try:
            response = httpx.post(
                self.base_url + "/experimental/agent/v1/" + task,
                json=payload.model_dump(mode="json"),
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise AiTimeout("Agent Worker timed out") from exc
        except httpx.TransportError as exc:
            raise AiUnavailable("Agent Worker is unreachable") from exc
        if response.status_code in {408, 504}:
            raise AiTimeout("Agent Worker timed out")
        if response.status_code == 502:
            try:
                code = response.json().get("error_code")
            except (ValueError, AttributeError):
                code = None
            if code in {"AI_SCHEMA_INVALID", "EVIDENCE_INVALID"}:
                raise AiSchemaInvalid("Agent Worker returned invalid output or evidence")
        if response.status_code == 429 or response.status_code >= 500:
            raise AiUnavailable("Agent Worker is temporarily unavailable")
        if not response.is_success:
            raise AiFailed(
                f"Agent Worker rejected request (HTTP {response.status_code})"
            )
        try:
            return result_type.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise AiSchemaInvalid("Agent Worker response is invalid") from exc

    def persona(self, payload):
        return self.call("persona", payload, PersonaResult)

    def twin(self, payload):
        return self.call("twin", payload, TwinAnswer)

    def compare(self, payload):
        return self.call("compare", payload, Comparison)
