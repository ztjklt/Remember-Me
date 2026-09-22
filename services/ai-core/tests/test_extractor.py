import json

import pytest

from app.contracts import AICoreInput, AICoreOutput, load_fixture
from app.errors import AIOutputInvalid
from app.extractor import MemoryExtractor
from app.providers.base import ModelRequest, StructuredModelProvider
from app.providers.fixture import FixtureProvider


class InvalidProvider(StructuredModelProvider):
    def generate(self, request: ModelRequest) -> dict:
        return {
            "memory_items": [
                {
                    "memory_type": "PREFERENCE",
                    "content": "没有对应证据的结论",
                    "source_type": "AI_INFERENCE",
                    "evidence_ids": ["missing-evidence"],
                    "confidence": 0.99,
                    "model_version": "invalid-provider-v1",
                    "prompt_version": "memory-extractor-v1",
                    "schema_version": "integration-contract-v0.1.2",
                }
            ],
            "graph_updates": [],
            "persona_updates": [],
            "evidence": [],
            "model_version": "invalid-provider-v1",
        }


class MalformedProvider(StructuredModelProvider):
    def generate(self, request: ModelRequest) -> dict:
        return {"not": "an ai core output"}


def test_fixture_provider_is_deterministic_and_schema_validated() -> None:
    payload = load_fixture("phase1-happy")
    extractor = MemoryExtractor(
        provider=FixtureProvider(),
        model="fixture-ai-v1",
        model_version="fixture-ai-v1",
    )

    first = extractor.process(payload)
    second = extractor.process(payload)

    assert isinstance(first, AICoreOutput)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.memory_items
    assert first.evidence
    assert first.memory_items[0].evidence_ids == [first.evidence[0].evidence_id]
    assert first.memory_items[0].source_type == "AI_INFERENCE"
    assert first.evidence[0].source_type == "SUBJECT"


def test_empty_or_whitespace_transcript_produces_no_memories() -> None:
    payload = AICoreInput(
        episode_id="episode-empty",
        subject_id="subject-1",
        transcript="   ",
        existing_model_version="model-v0",
    )
    extractor = MemoryExtractor(
        provider=FixtureProvider(),
        model="fixture-ai-v1",
        model_version="fixture-ai-v1",
    )

    output = extractor.process(payload)

    assert output.memory_items == []
    assert output.evidence == []


def test_adversarial_uncertainty_does_not_become_a_confident_memory() -> None:
    payload = load_fixture("phase1-adversarial")
    extractor = MemoryExtractor(
        provider=FixtureProvider(),
        model="fixture-ai-v1",
        model_version="fixture-ai-v1",
    )

    output = extractor.process(payload)

    assert output.memory_items == [] or all(item.confidence <= 0.5 for item in output.memory_items)


@pytest.mark.parametrize("provider", [InvalidProvider(), MalformedProvider()])
def test_invalid_provider_output_raises_schema_error(provider: StructuredModelProvider) -> None:
    payload = load_fixture("phase1-happy")

    with pytest.raises(AIOutputInvalid) as exc_info:
        MemoryExtractor(provider=provider, model="test", model_version="test-v1").process(payload)

    assert exc_info.value.code == "AI_SCHEMA_INVALID"
