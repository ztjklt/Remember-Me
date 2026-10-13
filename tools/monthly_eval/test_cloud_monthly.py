import json
import pytest
import cloud_monthly as monthly


def test_missing_correction_meaning_does_not_confirm_or_share(monkeypatch, tmp_path):
    def save(path, value): path.write_text(json.dumps(value), encoding='utf-8')
    run = tmp_path / 'run'; run.mkdir()
    save(run/'state.json', {'phase':'complete','policy':'policy'})
    pair={'owner':{'subject_id':'s','consent_id':'c'},'reader':{'actor_id':'r'}}
    save(run/'identities.json', {'bus_driver':pair})
    save(run/'revision-targets.json', {'bus_driver':{'correction':'old'}})
    save(run/'product-episodes.json', {'bus_driver-01':{'episode_id':'ep1'}})
    save(tmp_path/'manifest.json', {'people':[{'id':'bus_driver','episodes':[{'id':'bus_driver-01'},{'id':'bus_driver-04'}]}]})
    monkeypatch.setattr(monthly,'CORPUS',tmp_path)
    monkeypatch.setattr(monthly,'load_sample',lambda _:('2026-09-09',tmp_path/'audio.wav',b'audio','hash'))
    monkeypatch.setattr(monthly,'wait_for_review',lambda *a:None)
    calls=[]
    def call(method,path,identity,**kw):
        calls.append((method,path,kw))
        if path.endswith('/capabilities'): return {'cloud_asr_policy':'policy','stt':'relay','stt_model':'codestral-2508'}
        if path.endswith('/grants'): return {'grant_id':'g'}
        if path=='/api/v1/episodes': return {'episode_id':'ep4'}
        if path.endswith('/revisions'): return {'revision_id':'rev4'}
        if path.endswith('/stories'): return {'items':[
            {'episode_id':'ep1','memories':[{'memory_item_id':'old','content':'1986年上岗'}]},
            {'episode_id':'ep4','memories':[{'content':'1987年上岗','evidence':[{'excerpt':'我去上班'}]}]}]}
        pytest.fail('Unexpected request: '+path)
    monkeypatch.setattr(monthly,'call',call)
    with pytest.raises(SystemExit,match='Partial'): monthly.run_month(run)
    assert not any('/confirm' in path for _,path,_ in calls)
    assert len([c for c in calls if c[1].endswith('/grants')])==1  # Only old story01.
    state=json.loads((run/'monthly-state.json').read_text())
    assert not state['episodes']['bus_driver-04'].get('complete')
    assert 'missing from actual ASR' in state['errors'][0]['message']
