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


@pytest.mark.parametrize("rewrite_context", [False, True])
def test_repeated_recording_support_preserves_exact_trait_context(rewrite_context):
    first, second = material(), material("e2", "工作日下班后我还是喜欢一个人待着。")
    baseline = orchestrator().persona(PersonaInput(subject_id="subject-a", snapshot=snapshot(),
        materials=[first], new_evidence_ids=[first.evidence_id])).traits[0]
    change = dict(action="SUPPORT", target_trait_id=baseline.trait_id, domain=baseline.domain,
        statement=baseline.statement, context=baseline.context + ("，本次录音" if rewrite_context else ""),
        evidence_ids=[second.evidence_id], confidence=0.8, reason="重复表述同一情境的偏好")
    agent = orchestrator(Static({"changes": [change]}))
    payload = PersonaInput(subject_id="subject-a", snapshot=snapshot([baseline]),
        materials=[first, second], new_evidence_ids=[second.evidence_id])
    if rewrite_context:
        with pytest.raises(EvidenceInvalid, match="Different contexts"):
            agent.persona(payload)
    else:
        result = agent.persona(payload)
        assert len(result.traits) == 1
        assert result.traits[0].context == baseline.context
        assert result.traits[0].evidence_ids == [first.evidence_id, second.evidence_id]
        assert result.traits[0].status == "SUPPORTED"


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


def test_unknown_question_is_assessed_by_model_with_original_context():
    provider = Static(dict(answerable=False, answer="没有出生日期材料", evidence_ids=[], limitations=[]))
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
    assert provider.requests[0].worker_input["materials"][0]["excerpt"] == material().excerpt


@pytest.mark.parametrize("question", ["我是谁？", "我的研究方向是什么？", "我做什么工作？"])
def test_paraphrased_questions_receive_original_context_without_keyword_filter(question):
    source = material(text="陈安，研发工程师，专攻智能体的长期记忆。")
    proposal = Static({"changes": [dict(action="ADD", target_trait_id=None, domain="IDENTITY",
        statement="研发工程师", context="", evidence_ids=["e1"], confidence=0.8, reason="本人介绍")]})
    traits = orchestrator(proposal).persona(PersonaInput(subject_id="subject-a", snapshot=snapshot(),
        materials=[source], new_evidence_ids=["e1"])).traits
    twin = Static(dict(answerable=True, answer=source.excerpt, evidence_ids=["e1"], limitations=[]))
    answer = orchestrator(twin).twin(TwinInput(subject_id="subject-a", question=question,
        snapshot=snapshot(traits), materials=[source]))
    assert answer.answer == source.excerpt
    assert answer.evidence_ids == ["e1"]
    assert len(twin.requests) == 1


def test_generated_answer_is_not_misclassified_as_original_and_foreign_refs_fail():
    p = Static(dict(answerable=True, answer="下班后我喜欢独处。", evidence_ids=["e1"], limitations=[]))
    payload = TwinInput(subject_id="subject-a", question="下班后怎么度过？",
                        snapshot=snapshot(), materials=[material()])
    assert orchestrator(p).twin(payload).response_type == "SIMULATION"
    p.output["evidence_ids"] = ["not-in-pack"]
    with pytest.raises(EvidenceInvalid):
        orchestrator(p).twin(payload)


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


def test_full_context_keeps_team_facts_missing_from_understanding():
    source = material('team', '我们一共六人，三人学物理，两人学设计，一人学计算机。')
    others = [material(f'noise{i}', f'第{i}次谈到周末散步。') for i in range(15)]
    provider = Static(dict(answerable=True, answer='团队共六人，专业是物理、设计和计算机。',
                           evidence_ids=['team'], limitations=[]))
    answer = orchestrator(provider).twin(TwinInput(subject_id='subject-a',
        question='同行的人数及学科构成？', snapshot=snapshot(), materials=[source, *others]))
    assert answer.response_type == 'SIMULATION'
    assert answer.evidence_ids == ['team']
    assert len(provider.requests[0].worker_input['materials']) == 16
    assert len(answer.answer) < len(source.excerpt) + 10


@pytest.mark.parametrize('refs', [['e1', 'e1'], ['foreign']])
def test_bad_answer_references_are_rejected(refs):
    provider = Static(dict(answerable=True, answer='独处', evidence_ids=refs, limitations=[]))
    with pytest.raises(EvidenceInvalid):
        orchestrator(provider).twin(TwinInput(subject_id='subject-a', question='休息方式？',
            snapshot=snapshot(), materials=[material()]))


def test_no_authorized_original_never_calls_provider():
    provider = Static({})
    answer = orchestrator(provider).twin(TwinInput(subject_id='subject-a', question='休息方式？',
        snapshot=snapshot(), materials=[material().model_copy(update={'speaker_authority':'UNVERIFIED'})]))
    assert answer.response_type == 'INSUFFICIENT' and not provider.requests


def test_unknown_fact_is_insufficient_even_when_model_cites_background():
    provider = Static(dict(answerable=False, answer="这段录音没有给出队友姓名。",
                           evidence_ids=["e1"], limitations=[]))
    answer = orchestrator(provider).twin(TwinInput(subject_id="subject-a", question="队友姓名？",
        snapshot=snapshot(), materials=[material()]))
    assert answer.response_type == "INSUFFICIENT" and not answer.evidence
