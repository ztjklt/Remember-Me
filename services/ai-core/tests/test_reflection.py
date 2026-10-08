import json
from copy import deepcopy

import pytest

from app.contracts import AICoreInput
from app.extractor import MemoryExtractor
from app.errors import AIOutputInvalid, EvidenceInvalid, ProviderUnavailable
from app.providers.ollama import grounded_result


class ReflectionProvider:
    def __init__(self, reflection):
        self.reflection = reflection
        self.calls = []

    def generate(self, request):
        return grounded_result({"memories": [{"quote": "我现在喝茶更安心", "statement": "现在喜欢喝茶",
                                "domain": "PREFERENCES", "memory_type": "PREFERENCE", "confidence": .8}]}, request)

    def generate_structured(self, request):
        self.calls.append(json.loads(request.payload.transcript))
        if isinstance(self.reflection, Exception):
            raise self.reflection
        return deepcopy(self.reflection)


def run(reflection, target=None, context_subject="own"):
    provider = ReflectionProvider(reflection)
    payload = AICoreInput(episode_id="new", subject_id="own", transcript="我现在喝茶更安心。", existing_model_version="v1",
                          subject_context={"subject_id": context_subject, "current_traits": [target] if target else []})
    output = MemoryExtractor(provider=provider, model="real-adapter-test", model_version="test-v1").process(payload)
    return output, provider


TARGET = {"trait_id": "stable", "domain": "PREFERENCES", "statement": "喜欢咖啡", "context": "日常饮品",
          "status": "active", "memory_item_ids": ["old"], "evidence_ids": ["ev-old"]}


def test_change_uses_verified_new_quote_and_copies_existing_target():
    output, provider = run({"updates": [{"memory_index": 0, "action": "CHANGE", "target_trait_id": "stable", "context": "日常饮品"}],
                            "facets": [{"memory_index": 0, "category": "mood", "label": "喝茶时更安心", "quote": "更安心"}]}, TARGET)
    memory = output.memory_items[0]
    assert memory.metadata["reflection"]["target"] == TARGET
    assert memory.metadata["facets"][0]["evidence_ids"] == memory.evidence_ids
    assert output.evidence[0].excerpt == "我现在喝茶更安心"
    assert provider.calls[0]["current_traits"] == [TARGET]
    assert output.persona_updates[0].evidence_ids == memory.evidence_ids  # No historical quote is forged into this Episode.


@pytest.mark.parametrize("change", [
    {"memory_index": 0, "action": "CHANGE", "target_trait_id": "forged", "context": "日常饮品"},
    {"memory_index": 0, "action": "SUPPORT", "target_trait_id": "stable", "context": "工作中"},
    {"memory_index": 0, "action": "CONFLICT", "target_trait_id": "stable", "context": "日常饮品", "domain": "EXPRESSION"},
])
def test_invalid_target_or_different_context_cannot_mutate_current_understanding(change):
    with pytest.raises(EvidenceInvalid):
        run({"updates": [change], "facets": []}, TARGET)


def test_subject_mismatch_never_sends_old_subject_to_reflection_provider():
    output, provider = run({"updates": [], "facets": []}, TARGET, context_subject="other")
    assert not provider.calls
    assert "reflection" not in output.memory_items[0].metadata


def test_fabricated_emotion_quote_fails_closed():
    with pytest.raises(EvidenceInvalid):
        run({"updates": [], "facets": [{"memory_index": 0, "category": "mood", "label": "悲伤", "quote": "我很难过"}]})


def test_duplicate_update_cannot_replace_two_targets():
    change = {"memory_index": 0, "action": "ADD"}
    with pytest.raises(AIOutputInvalid):
        run({"updates": [change, change], "facets": []})


def test_reflection_outage_preserves_worker_retry_semantics():
    with pytest.raises(ProviderUnavailable):
        run(ProviderUnavailable("reflection temporarily unavailable"))
