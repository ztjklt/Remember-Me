from datetime import timedelta

import pytest
from remember_contracts.agent import PersonaInput, Trait, TwinInput
from app.errors import AIOutputInvalid

from test_agent import NOW, Static, material, orchestrator, snapshot


def identity_state():
    source = material(text="我叫陈安，在海城大学读研究生。")
    correction = material("c1", "我叫晨安", context="我是谁？").model_copy(update={
        "source_type": "CALIBRATION", "source_ref": "calibration:test", "episode_id": None,
        "observed_at": NOW + timedelta(minutes=1),
    })
    trait = Trait(trait_id="identity", domain="IDENTITY", statement="自称陈安，海城大学研究生",
                  context="本人介绍", evidence_ids=[source.evidence_id],
                  counter_evidence_ids=[correction.evidence_id], confidence=0.5,
                  status="CONFLICTED", valid_from=NOW)
    return source, correction, trait


@pytest.mark.parametrize("question", ["我是谁？", " 我是谁? "])
def test_same_question_returns_exact_human_correction_without_model_call(question):
    source, correction, trait = identity_state()
    provider = Static({})
    answer = orchestrator(provider).twin(TwinInput(subject_id="subject-a", question=question,
        snapshot=snapshot([trait]), materials=[source, correction]))
    assert answer.response_type == "ORIGINAL"
    assert answer.answer == correction.excerpt
    assert answer.evidence_ids == [correction.evidence_id]
    assert answer.evidence[0].source_type == "CALIBRATION"
    assert not provider.requests


def test_latest_calibration_wins_without_erasing_previous_evidence():
    source, correction, trait = identity_state()
    previous = correction.model_copy(update={"evidence_id": "c0", "excerpt": "我叫辰安",
                                            "observed_at": NOW})
    payload = TwinInput(subject_id="subject-a", question="我是谁？", snapshot=snapshot([trait]),
                        materials=[source, correction, previous])
    answer = orchestrator(Static({})).twin(payload)
    assert answer.evidence_ids == [correction.evidence_id]
    assert payload.materials[-1].excerpt == previous.excerpt


def test_short_calibrated_question_does_not_require_bigram_overlap():
    _, correction, _ = identity_state()
    correction = correction.model_copy(update={"context": "谁？"})
    answer = orchestrator(Static({})).twin(TwinInput(subject_id="subject-a", question="谁？",
        snapshot=snapshot(), materials=[correction]))
    assert answer.evidence_ids == [correction.evidence_id]


@pytest.mark.parametrize("mode", ["withdrawn", "unverified", "third-party", "superseded", "unrelated"])
def test_ineligible_corrections_cannot_override_conflict(mode):
    source, correction, trait = identity_state()
    materials, traits = [source, correction], [trait]
    if mode == "withdrawn":
        materials = [source]
    elif mode == "unverified":
        materials[1] = correction.model_copy(update={"speaker_authority": "UNVERIFIED"})
    elif mode == "third-party":
        materials[1] = correction.model_copy(update={"source_type": "THIRD_PARTY"})
    elif mode == "superseded":
        traits.append(trait.model_copy(update={"trait_id": "old-correction", "status": "SUPERSEDED",
                                               "evidence_ids": [correction.evidence_id], "counter_evidence_ids": []}))
    else:
        materials[1] = correction.model_copy(update={"context": "周末喜欢做什么？"})
    provider = Static({})
    answer = orchestrator(provider).twin(TwinInput(subject_id="subject-a", question="我是谁？",
        snapshot=snapshot(traits), materials=materials))
    assert answer.response_type == "INSUFFICIENT"
    assert "矛盾" in answer.answer and "未解决的矛盾" in answer.limitations
    assert not answer.evidence_ids and not provider.requests


def test_fact_correction_preserves_history_and_cites_uncorrected_facts():
    source, correction, baseline = identity_state()
    proposal = {"changes": [dict(action="CHANGE", target_trait_id=baseline.trait_id, domain="IDENTITY",
        statement="自称晨安，海城大学研究生", context=baseline.context,
        evidence_ids=[source.evidence_id, correction.evidence_id], confidence=0.7, reason="本人纠正姓名误识别") ]}
    result = orchestrator(Static(proposal)).persona(PersonaInput(subject_id="subject-a",
        snapshot=snapshot([baseline]), materials=[source, correction], new_evidence_ids=[correction.evidence_id]))
    historical, current = result.traits
    assert historical.status == "SUPERSEDED" and historical.statement == baseline.statement
    assert historical.valid_to == correction.observed_at
    assert current.statement == "自称晨安，海城大学研究生"
    assert set(current.evidence_ids) == {source.evidence_id, correction.evidence_id}
    assert not set(current.evidence_ids) & set(current.counter_evidence_ids)
    assert current.status != "CONFLICTED" and source.excerpt.startswith("我叫陈安")


@pytest.mark.parametrize("quote_old_excerpt", [False, True])
def test_corrected_mixed_excerpt_requires_synthesis_for_other_questions(quote_old_excerpt):
    source, correction, baseline = identity_state()
    historical = baseline.model_copy(update={"status": "SUPERSEDED", "valid_to": correction.observed_at})
    current = baseline.model_copy(update={"trait_id": "corrected", "status": "CANDIDATE",
        "statement": "自称晨安，海城大学研究生", "counter_evidence_ids": [],
        "evidence_ids": [source.evidence_id, correction.evidence_id]})
    provider = Static(dict(response_type="ORIGINAL" if quote_old_excerpt else "SIMULATION",
        answer=source.excerpt if quote_old_excerpt else "我在海城大学读研究生。",
        evidence_ids=[source.evidence_id] if quote_old_excerpt else [source.evidence_id, correction.evidence_id],
        limitations=[]))
    agent = orchestrator(provider)
    payload = TwinInput(subject_id="subject-a", question="我在哪所大学读研？",
        snapshot=snapshot([historical, current]), materials=[source, correction])
    if quote_old_excerpt:
        with pytest.raises(AIOutputInvalid):
            agent.twin(payload)
    else:
        answer = agent.twin(payload)
        assert answer.response_type == "SIMULATION" and answer.answer == "我在海城大学读研究生。"
        assert set(answer.evidence_ids) == {source.evidence_id, correction.evidence_id}
    assert "ORIGINAL" not in provider.requests[0].response_schema["properties"]["response_type"]["enum"]
