"""Original routing and generated answers remain bound to actual evidence."""

import pytest

from app.errors import AIOutputInvalid
from app.twin_agent import TwinAgent, TwinAgentInput


class Stub:
    def __init__(self, output):
        self.output = output

    def complete(self, payload, schema, prompt, name):
        assert name == "remember_me_twin_agent"
        assert payload["traits"][0]["domain"] == "Preferences"
        return self.output


def payload():
    return TwinAgentInput.model_validate({
        "question": "这个人喜欢喝什么？",
        "evidence": [
            {"evidence_id": "ev_1", "memory_item_id": "m1", "excerpt": "我喜欢喝咖啡。",
             "memory_content": "喜欢咖啡", "source_type": "SUBJECT", "recorded_at": None,
             "confidence": 0.92},
            {"evidence_id": "ev_2", "memory_item_id": "m2", "excerpt": "朋友说他喜欢茶。",
             "memory_content": "喜欢茶", "source_type": "THIRD_PARTY", "recorded_at": None,
             "confidence": 0.65},
        ],
        "traits": [{"trait_id": "trait_1", "domain": "Preferences",
                    "statement": "喜欢咖啡", "evidence_ids": ["ev_1"],
                    "context": None, "confidence": 0.82}],
    })


def test_original_is_exact_subject_excerpt_not_generated_paraphrase():
    agent = TwinAgent(provider=Stub({
        "route": "ORIGINAL", "answer": "他最喜欢茶。", "evidence_ids": ["ev_1"],
        "confidence": 0.99, "model_version": "untrusted",
    }), model_version="deepseek-real")
    answer = agent.answer(payload())
    assert answer.answer == "我喜欢喝咖啡。"
    assert answer.confidence == 0.92
    assert answer.model_version == "deepseek-real"


def test_third_party_cannot_be_original_and_simulation_requires_citations():
    original = TwinAgent(provider=Stub({
        "route": "ORIGINAL", "answer": "朋友说他喜欢茶。", "evidence_ids": ["ev_2"],
        "confidence": 0.7, "model_version": "x",
    }), model_version="real")
    with pytest.raises(AIOutputInvalid):
        original.answer(payload())
    hallucination = TwinAgent(provider=Stub({
        "route": "SIMULATION", "answer": "他喜欢茶", "evidence_ids": ["other"],
        "confidence": 0.8, "model_version": "x",
    }), model_version="real")
    with pytest.raises(AIOutputInvalid):
        hallucination.answer(payload())


def test_refusal_has_no_citation_or_confidence():
    agent = TwinAgent(provider=Stub({
        "route": "REFUSE", "answer": "编造回答", "evidence_ids": ["ev_1"],
        "confidence": 1, "model_version": "x",
    }), model_version="real")
    result = agent.answer(payload())
    assert result.answer is None and result.evidence_ids == [] and result.confidence == 0
