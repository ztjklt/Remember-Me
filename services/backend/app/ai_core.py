"""AI Core boundary.

Backend hands AI Core an `aiCoreInput` and receives an `aiCoreOutput`, both
validated against app/contracts.py on the way out and on the way back. The
output is parsed before it is stored, not after: a response that is missing a
required field or uses an unregistered enum value is refused here, at the
boundary, so a half-shaped memory never reaches the memory table.

AI Core never generates or mutates `episode_id` (the contract says so, and
packages/contracts asserts it). The response is not trusted for it either — the
episode id written to the record is the one the worker is holding.

As with the speech-to-text boundary, `build_ai_client` refuses the fake outside
development and test. The rule itself is in app/providers.py, written once for
both boundaries.
"""

from typing import Protocol

import httpx
from pydantic import ValidationError

from .contracts import SCHEMA_VERSION, AICoreInput, AICoreOutput, Evidence, MemoryItem
from .config import Settings
from .errors import AiFailed, AiSchemaInvalid, AiTimeout, AiUnavailable
from .models import MemoryType, SourceType
from .providers import refuse_fake_unless_permitted

FAKE_BACKEND = "fake"
FAKE_MODEL_VERSION = "fake-ai-v1"
FAKE_PROMPT_VERSION = "fake-prompt-v1"

# Long enough to identify the cause, short enough that a provider returning an
# HTML error page cannot push a novel into the Episode's error_message column.
_ERROR_EXCERPT = 300


class AiCoreClient(Protocol):
    """Boundary every AI Core transport sits behind."""

    def process(self, payload: AICoreInput) -> AICoreOutput: ...


class FakeAiCoreClient:
    """Deterministic stand-in: one memory item per line of the transcript.

    It does not reason about anything, and it says so in every value it writes —
    `model_version` and `prompt_version` are both prefixed `fake-`, and the
    memory content repeats the `[fake-stt]` marker it was derived from. A row
    that a fake wrote is therefore identifiable from the row itself:

        SELECT * FROM memory_items WHERE model_version LIKE 'fake-%';

    `graph_updates` and `persona_updates` are empty: the graph and persona shapes
    are Phase 2, and this adapter has no honest way to fill them.
    """

    backend = FAKE_BACKEND
    model_version = FAKE_MODEL_VERSION

    def process(self, payload: AICoreInput) -> AICoreOutput:
        lines = [line.strip() for line in payload.transcript.splitlines() if line.strip()]

        evidence: list[Evidence] = []
        memory_items: list[MemoryItem] = []
        for index, line in enumerate(lines):
            evidence_id = f"ev_{payload.episode_id}_{index}"
            evidence.append(
                Evidence(
                    evidence_id=evidence_id,
                    # The line a memory rests on is a transcript of the subject's
                    # audio; what the model concluded from it is not.
                    source_type=SourceType.SUBJECT,
                    source_ref=f"episode:{payload.episode_id}#line{index}",
                    excerpt=line,
                    confidence=0.5,
                )
            )
            memory_items.append(
                MemoryItem(
                    memory_type=MemoryType.EVENT,
                    content=f"[fake-ai] {line}",
                    source_type=SourceType.AI_INFERENCE,
                    evidence_ids=[evidence_id],
                    confidence=0.5,
                    model_version=self.model_version,
                    prompt_version=FAKE_PROMPT_VERSION,
                    schema_version=SCHEMA_VERSION,
                )
            )

        return AICoreOutput(
            memory_items=memory_items,
            graph_updates=[],
            persona_updates=[],
            evidence=evidence,
            model_version=self.model_version,
        )


class HttpAiCoreClient:
    """AI Core over HTTP, the deployment transport.

    One attempt per call, like the object store: a retry is the job's decision,
    made with the attempt count and the backoff in view.
    """

    backend = "http"

    def __init__(self, base_url: str, path: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.path = path
        self.timeout_seconds = timeout_seconds

    def process(self, payload: AICoreInput) -> AICoreOutput:
        url = f"{self.base_url}/{self.path.lstrip('/')}"
        try:
            response = httpx.post(
                url,
                json=payload.model_dump(mode="json"),
                timeout=httpx.Timeout(self.timeout_seconds),
            )
        except httpx.TimeoutException as error:
            raise AiTimeout(f"AI Core did not answer within {self.timeout_seconds}s") from error
        except httpx.TransportError as error:
            raise AiUnavailable(f"AI Core is unreachable at {url}: {error}") from error

        if response.status_code >= 400:
            message = (
                f"AI Core answered {response.status_code}: "
                f"{response.text[:_ERROR_EXCERPT]}"
            )
            if response.status_code == 503:
                raise AiUnavailable(message)
            if response.status_code == 504:
                raise AiTimeout(message)
            raise AiFailed(message)

        try:
            body = response.json()
        except ValueError as error:
            raise AiSchemaInvalid(
                f"AI Core answered with something that is not JSON: "
                f"{response.text[:_ERROR_EXCERPT]}"
            ) from error

        try:
            # Strict on purpose, including unknown fields: the contract sets
            # additionalProperties false, so a response carrying a field v0.1 does
            # not define is drift, and it is cheaper to see it here than in a
            # client that has already been shipped.
            return AICoreOutput.model_validate(body)
        except ValidationError as error:
            raise AiSchemaInvalid(
                f"AI Core answered with something that is not a valid aiCoreOutput: "
                f"{error.error_count()} validation error(s): "
                f"{_first_problem(error)}"
            ) from error


def _first_problem(error: ValidationError) -> str:
    problem = error.errors()[0]
    location = ".".join(str(part) for part in problem["loc"]) or "<body>"
    return f"{location}: {problem['msg']}"


def build_ai_client(settings: Settings) -> AiCoreClient:
    if settings.ai_backend == FAKE_BACKEND:
        refuse_fake_unless_permitted(settings, "AI Core")
        return FakeAiCoreClient()
    if settings.ai_backend == "http":
        return HttpAiCoreClient(
            settings.ai_core_url,
            settings.ai_core_path,
            settings.ai_timeout_seconds,
        )
    raise ValueError(f"Unsupported AI backend: {settings.ai_backend!r}")
