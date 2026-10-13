import pytest
from speech_pipeline import authorize_remaining

def test_default_requires_quality_gate():
    with pytest.raises(ValueError): authorize_remaining({}, ['a'], False)

def test_explicit_technical_run_never_claims_listening():
    result=authorize_remaining({}, ['a'], True)
    assert result['mode']=='technical_only'
    assert result['manual_listening_passed'] is False

def test_quality_gate_needs_every_person_and_field():
    good={k:True for k in ('real_weixin','reviewed_asr','persisted_memory','qa_sources','manual_listening','duration_pass')}
    with pytest.raises(ValueError):authorize_remaining({'a':good},['a','b'],False)
    assert authorize_remaining({'a':good},['a'],False)['mode']=='quality_gated'
