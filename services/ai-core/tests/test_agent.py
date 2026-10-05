from datetime import datetime, timezone
from copy import deepcopy
import pytest
from remember_contracts.agent import (
    CompareInput,
    Material,
    PersonaInput,
    Snapshot,
    TwinInput,
)
from app.agent.orchestrator import AgentOrchestrator
from app.errors import AIOutputInvalid, EvidenceInvalid
from app.extractor import MemoryExtractor
from app.providers.fixture import FixtureProvider

NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def material(eid="e1", text="工作日下班后我喜欢一个人待着。", **kwargs):
    return Material(
        evidence_id=eid,
        episode_id="episode-" + eid,
        excerpt=text,
        source_type="SUBJECT",
        source_ref="episode:" + eid,
        observed_at=NOW,
        speaker_authority="SELF_ATTESTED",
        memory_type="PREFERENCE",
        **kwargs,
    )


def snapshot(traits=None):
    return Snapshot(
        subject_id="subject-a",
        revision=0,
        traits=traits or [],
        model_version="before",
        prompt_version="before",
    )


def orchestrator(provider=None):
    return AgentOrchestrator(
        MemoryExtractor(
            provider=provider or FixtureProvider(),
            model="fixture-ai-v2",
            model_version="fixture-ai-v2",
        )
    )


class Static:
    def __init__(self, output):
        self.output = output
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return deepcopy(self.output)


def test_separate_contexts_remain_separate_candidate_traits():
    a = orchestrator()
    first = material()
    one = a.persona(
        PersonaInput(
            subject_id="subject-a",
            snapshot=snapshot(),
            materials=[first],
            new_evidence_ids=["e1"],
        )
    )
    second = material("e2", "周末我喜欢和家人一起吃饭。")
    two = a.persona(
        PersonaInput(
            subject_id="subject-a",
            snapshot=snapshot(one.traits),
            materials=[first, second],
            new_evidence_ids=["e2"],
        )
    )
    assert len(two.traits) == 2
    assert {t.context for t in two.traits} == {"工作日下班后", "周末"}
    assert all(t.status == "CANDIDATE" for t in two.traits)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.update(evidence_ids=["foreign-subject-evidence"]),
        lambda c: c.update(action="CHANGE", target_trait_id="foreign-trait"),
        lambda c: c.update(action="ADD", target_trait_id="existing-trait"),
    ],
)
def test_untrusted_persona_references_are_rejected(mutate):
    change = dict(
        action="ADD",
        target_trait_id=None,
        domain="PREFERENCES",
        statement="偏好独处",
        context="",
        evidence_ids=["e1"],
        confidence=0.9,
        reason="test",
    )
    mutate(change)
    with pytest.raises(EvidenceInvalid):
        orchestrator(Static({"changes": [change]})).persona(
            PersonaInput(
                subject_id="subject-a",
                snapshot=snapshot(),
                materials=[material()],
                new_evidence_ids=["e1"],
            )
        )


@pytest.mark.parametrize(
    "authority,source", [("UNVERIFIED", "SUBJECT"), ("SELF_ATTESTED", "THIRD_PARTY")]
)
def test_persona_does_not_accept_unverified_or_third_party_evidence(authority, source):
    m = material().model_copy(
        update={"speaker_authority": authority, "source_type": source}
    )
    proposal = {
        "changes": [
            dict(
                action="ADD",
                target_trait_id=None,
                domain="PREFERENCES",
                statement="偏好独处",
                context="",
                evidence_ids=["e1"],
                confidence=0.9,
                reason="test",
            )
        ]
    }
    with pytest.raises(EvidenceInvalid):
        orchestrator(Static(proposal)).persona(
            PersonaInput(
                subject_id="subject-a",
                snapshot=snapshot(),
                materials=[m],
                new_evidence_ids=["e1"],
            )
        )


def test_unknown_question_returns_insufficient_without_provider_call():
    provider = Static({})
    answer = orchestrator(provider).twin(
        TwinInput(
            subject_id="subject-a",
            question="出生日期是什么？",
            snapshot=snapshot(),
            materials=[material()],
        )
    )
    assert answer.response_type == "INSUFFICIENT"
    assert not answer.evidence_ids
    assert not provider.requests


@pytest.mark.parametrize("question", ["我是谁？", "我的研究方向是什么？", "我做什么工作？"])
def test_identity_intent_retrieves_typed_evidence_without_literal_overlap(question):
    source = material(text="陈安，研发工程师，专攻智能体的长期记忆。")
    proposal = Static({"changes": [dict(action="ADD", target_trait_id=None, domain="IDENTITY",
        statement="研发工程师", context="", evidence_ids=["e1"], confidence=0.8, reason="本人介绍")]})
    traits = orchestrator(proposal).persona(PersonaInput(subject_id="subject-a", snapshot=snapshot(),
        materials=[source], new_evidence_ids=["e1"])).traits
    twin = Static(dict(response_type="ORIGINAL", answer=source.excerpt, evidence_ids=["e1"], limitations=[]))
    answer = orchestrator(twin).twin(TwinInput(subject_id="subject-a", question=question,
        snapshot=snapshot(traits), materials=[source]))
    assert answer.answer == source.excerpt
    assert answer.evidence_ids == ["e1"]
    assert len(twin.requests) == 1


def test_original_cannot_be_a_paraphrase_or_foreign_quote():
    p = Static(
        dict(
            response_type="ORIGINAL",
            answer="我讨厌一个人待着。",
            evidence_ids=["e1"],
            limitations=[],
        )
    )
    with pytest.raises(EvidenceInvalid):
        orchestrator(p).twin(
            TwinInput(
                subject_id="subject-a",
                question="下班后喜欢怎样待着？",
                snapshot=snapshot(),
                materials=[material()],
            )
        )
    p.output["evidence_ids"] = ["not-in-pack"]
    with pytest.raises(EvidenceInvalid):
        orchestrator(p).twin(
            TwinInput(
                subject_id="subject-a",
                question="下班后喜欢怎样待着？",
                snapshot=snapshot(),
                materials=[material()],
            )
        )


def test_changed_view_preserves_history_and_blocks_old_original():
    a = orchestrator()
    m1 = material(text="我喜欢热闹。")
    one = a.persona(
        PersonaInput(
            subject_id="subject-a",
            snapshot=snapshot(),
            materials=[m1],
            new_evidence_ids=["e1"],
        )
    )
    m2 = material("e2", "我现在不喜欢热闹，喜欢安静。")
    result = a.persona(
        PersonaInput(
            subject_id="subject-a",
            snapshot=snapshot(one.traits),
            materials=[m1, m2],
            new_evidence_ids=["e2"],
        )
    )
    assert result.traits[0].status == "SUPERSEDED"
    assert result.traits[0].valid_to == NOW
    assert result.traits[1].counter_evidence_ids == ["e1"]
    answer = a.twin(
        TwinInput(
            subject_id="subject-a",
            question="喜欢热闹吗？",
            snapshot=snapshot(result.traits),
            materials=[m1, m2],
        )
    )
    assert answer.evidence_ids == ["e2"]


def test_compare_requires_all_five_distinct_dimensions():
    a = orchestrator()
    locked = a.twin(
        TwinInput(
            subject_id="subject-a",
            question="下班后喜欢做什么？",
            snapshot=snapshot(),
            materials=[material()],
        )
    )
    comparison = a.compare(
        CompareInput(
            subject_id="subject-a",
            question="下班后喜欢做什么？",
            locked_answer=locked,
            human_answer="更喜欢和家人聊聊天。",
        )
    )
    assert len({d.dimension for d in comparison.dimension_diffs}) == 5
    raw = comparison.model_dump(mode="json")
    raw["dimension_diffs"][1] = raw["dimension_diffs"][0]
    with pytest.raises(AIOutputInvalid):
        orchestrator(Static(raw)).compare(
            CompareInput(
                subject_id="subject-a",
                question="q",
                locked_answer=locked,
                human_answer="answer",
            )
        )


def test_persona_worker_prompt_and_input_are_passed_to_real_provider_interface():
    provider = Static({"changes": []})
    orchestrator(provider).persona(
        PersonaInput(
            subject_id="subject-a",
            snapshot=snapshot(),
            materials=[material()],
            new_evidence_ids=["e1"],
        )
    )
    request = provider.requests[0]
    assert request.task == "persona"
    assert request.worker_input["materials"][0]["excerpt"] == material().excerpt
    assert "human_answer" not in request.worker_input
    assert request.response_schema["additionalProperties"] is False
