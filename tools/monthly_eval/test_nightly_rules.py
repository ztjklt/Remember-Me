import json
from pathlib import Path
import httpx,pytest
from nightly_rules import publish_repair,choose_audio,record_failure,qa_state,check_correction

def test_publish_switches_manifest_only_after_immutable_audio_ready(tmp_path,monkeypatch):
    audio=tmp_path/'clip.wav';audio.write_bytes(b'old');meta=tmp_path/'clip.json';meta.write_text(json.dumps({'audio_sha256':'old'}))
    import nightly_rules
    def fail(*a):raise OSError('disk failure')
    monkeypatch.setattr(nightly_rules,'save',fail)
    with pytest.raises(OSError):publish_repair(audio,meta,b'new',{})
    assert audio.read_bytes()==b'old'
    assert json.loads(meta.read_text())['audio_sha256']=='old'

def test_publication_selects_new_audio_preserves_original(tmp_path):
    audio=tmp_path/'clip.wav';audio.write_bytes(b'old');meta=tmp_path/'clip.json';meta.write_text('{}')
    publish_repair(audio,meta,b'new',{})
    result=json.loads(meta.read_text())
    assert choose_audio(tmp_path,'clip',result).read_bytes()==b'new'
    assert audio.read_bytes()==b'old'

def test_transient_failures_have_finite_persistent_retry_budget():
    row={}
    for i in range(3):record_failure(row,httpx.ReadTimeout('network'),100+i)
    assert row['transport_attempts']==3 and row['blocked']
    bad={};record_failure(bad,AssertionError('evidence mismatch'),1);assert bad['blocked']

def test_recovered_qa_preserves_prior_error_and_has_checks():
    state={'qa':{'person':{'precondition_error':'previous'}}}
    result=qa_state(state,'person')
    assert result['checks']==[] and result['precondition_error']=='previous'

def test_correction_requires_corrective_evidence_not_just_any_memory():
    with pytest.raises(ValueError):check_correction('bus_driver',{'content':'1986年'}, {'transcript':'我喜欢茶','memories':[{'content':'喜欢茶','evidence':[{'evidence_id':'e','excerpt':'我喜欢茶'}]}]})
    good={'transcript':'我要纠正，是一九八七年，不是一九八六年。','memories':[{'content':'纠正为1987年','evidence':[{'evidence_id':'e','excerpt':'我要纠正，是一九八七年，不是一九八六年。'}]}]}
    assert check_correction('bus_driver',{'content':'1986年'},good)['matching_evidence_ids']==['e']


def test_failure_cannot_be_reported_as_all_technical_requests_passed():
    from nightly_rules import technical_phase
    state={'profiles':{'p':{'status':'failed'}},'qa':{'p':{'checks':[{'id':'q','error':'503'}]}}}
    assert technical_phase(state,1)=='technical_partial_failures'
    state={'profiles':{'p':{'status':'complete'}},'qa':{'p':{'checks':[{'id':'q','result':{'answer':'test'}}]}}}
    assert technical_phase(state,1)=='technical_requests_finished_quality_review_pending'
