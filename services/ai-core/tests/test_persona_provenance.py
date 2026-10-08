"""Derived persona provenance obeys the same attribution rules as Memory."""
import pytest

from app.contracts import PersonTrait, GraphFact, load_fixture
from app.errors import AIOutputInvalid, EvidenceInvalid
from app.extractor import MemoryExtractor
from app.providers.fixture import FixtureProvider
from app.validation import validate_output


def example():
    payload = load_fixture('phase1-happy')
    output = MemoryExtractor(provider=FixtureProvider(), model='fixture', model_version='test').process(payload)
    memory = output.memory_items[0]
    output.persona_updates = [PersonTrait(
        trait_id='trait-one', domain='PREFERENCES', statement=memory.content,
        confidence=0.8, source_type='AI_INFERENCE', evidence_ids=memory.evidence_ids,
        counter_evidence_ids=[], status='active', model_version='test')]
    return payload, output


def test_grounded_inference_is_accepted_without_becoming_a_subject_quote():
    payload, output = example()
    assert validate_output(payload, output).persona_updates[0].source_type == 'AI_INFERENCE'
    output.persona_updates[0].source_type = 'SUBJECT'
    output.persona_updates[0].statement = '模型编造的人格结论'
    with pytest.raises(EvidenceInvalid, match='paraphrase'):
        validate_output(payload, output)


def test_third_party_evidence_cannot_become_subject_persona():
    payload, output = example()
    output.evidence[0].source_type = 'THIRD_PARTY'
    trait = output.persona_updates[0]
    trait.statement = output.evidence[0].excerpt
    trait.source_type = 'SUBJECT'
    with pytest.raises(EvidenceInvalid, match='attribution'):
        validate_output(payload, output)


def test_same_quote_cannot_be_both_support_and_counter_evidence():
    payload, output = example()
    output.persona_updates[0].counter_evidence_ids = output.persona_updates[0].evidence_ids
    with pytest.raises(EvidenceInvalid, match='distinct'):
        validate_output(payload, output)


def test_duplicate_trait_and_graph_ids_are_rejected_before_persistence():
    payload, output = example()
    output.persona_updates.append(output.persona_updates[0].model_copy())
    with pytest.raises(AIOutputInvalid, match='unique'):
        validate_output(payload, output)
    output.persona_updates = output.persona_updates[:1]
    fact = GraphFact(fact_id='one', subject_id=payload.subject_id, kind='EVENT',
                     content='事件推断', evidence_ids=output.memory_items[0].evidence_ids, model_version='test')
    output.graph_updates = [fact, fact.model_copy()]
    with pytest.raises(AIOutputInvalid, match='unique'):
        validate_output(payload, output)
