from datetime import timedelta

import pytest
from remember_contracts.agent import PersonaInput, Trait, TwinInput
from app.errors import EvidenceInvalid

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
def test_correction_remains_in_full_context_and_exact_quote_is_original(question):
    source, correction, trait = identity_state()
    provider = Static(dict(answerable=True, answer=correction.excerpt, evidence_ids=[correction.evidence_id], limitations=[]))
    answer = orchestrator(provider).twin(TwinInput(subject_id="subject-a", question=question,
        snapshot=snapshot([trait]), materials=[source, correction]))
    assert answer.response_type == "ORIGINAL"
    assert answer.answer == correction.excerpt
    assert answer.evidence_ids == [correction.evidence_id]
    assert answer.evidence[0].source_type == "CALIBRATION"
    assert provider.requests[0].worker_input["corrections"][0]["excerpt"] == correction.excerpt


def test_latest_calibration_wins_without_erasing_previous_evidence():
    source, correction, trait = identity_state()
    previous = correction.model_copy(update={"evidence_id": "c0", "excerpt": "我叫辰安",
                                            "observed_at": NOW})
    payload = TwinInput(subject_id="subject-a", question="我是谁？", snapshot=snapshot([trait]),
                        materials=[source, correction, previous])
    provider = Static(dict(answerable=True, answer=correction.excerpt, evidence_ids=[correction.evidence_id], limitations=[]))
    answer = orchestrator(provider).twin(payload)
    assert answer.evidence_ids == [correction.evidence_id]
    assert payload.materials[-1].excerpt == previous.excerpt


def test_short_calibrated_question_does_not_require_bigram_overlap():
    _, correction, _ = identity_state()
    correction = correction.model_copy(update={"context": "谁？"})
    answer = orchestrator(Static(dict(answerable=True, answer=correction.excerpt, evidence_ids=[correction.evidence_id], limitations=[]))).twin(TwinInput(subject_id="subject-a", question="谁？",
        snapshot=snapshot(), materials=[correction]))
    assert answer.evidence_ids == [correction.evidence_id]


@pytest.mark.parametrize("mode", ["withdrawn", "unverified", "third-party"])
def test_ineligible_correction_cannot_be_cited(mode):
    source, correction, trait = identity_state()
    materials = [source, correction]
    if mode == "withdrawn":
        materials = [source]
    elif mode == "unverified":
        materials[1] = correction.model_copy(update={"speaker_authority": "UNVERIFIED"})
    else:
        materials[1] = correction.model_copy(update={"source_type": "THIRD_PARTY"})
    provider = Static(dict(answerable=True, answer=correction.excerpt, evidence_ids=[correction.evidence_id], limitations=[]))
    with pytest.raises(EvidenceInvalid):
        orchestrator(provider).twin(TwinInput(subject_id="subject-a", question="我是谁？",
            snapshot=snapshot([trait]), materials=materials))


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


def test_correction_does_not_block_other_facts_in_the_same_recording():
    source, correction, baseline = identity_state()
    historical = baseline.model_copy(update={"status": "SUPERSEDED", "valid_to": correction.observed_at})
    provider = Static(dict(answerable=True, answer="在海城大学读研。", evidence_ids=[source.evidence_id], limitations=[]))
    answer = orchestrator(provider).twin(TwinInput(subject_id="subject-a", question="就读哪里？",
        snapshot=snapshot([historical, baseline]), materials=[source, correction]))
    assert answer.response_type == "SIMULATION"
    request = provider.requests[0]
    assert {m["evidence_id"] for m in request.worker_input["materials"] + request.worker_input["corrections"]} == {"e1", "c1"}
    assert all(t["status"] != "SUPERSEDED" for t in request.worker_input["current_understanding"]["traits"])
    assert "response_type" not in request.response_schema["properties"]
