import pytest
from app.errors import AIOutputInvalid


def sample(action='SUPPORT'):
    from app.profile_relations import RelationInput
    return RelationInput.model_validate({'materials':[
        {'evidence_id':'a','episode_id':'ep1','excerpt':'平时喝茶不放糖。'},
        {'evidence_id':'b','episode_id':'ep2','excerpt':'后来改了口味，现在喜欢加糖。' if action=='CHANGE' else '昨天喝茶仍然不加糖。'}],
        'candidates':[{'candidate_id':'new','domain':'PREFERENCES','kind':'habit','statement':'现在的口味',
            'context':'喝茶','evidence_ids':['b'],'counter_evidence_ids':[]}],
        'targets':[{'candidate_id':'old','domain':'PREFERENCES','kind':'habit','statement':'以前的口味',
            'context':'喝茶','evidence_ids':['a'],'counter_evidence_ids':[]}]})


def relation(action='SUPPORT'):
    return {'candidate_id':'n1','target_candidate_id':'t1','action':action,'reason':'两次本人讲述',
        'evidence_ids':['s1','s2'],'time_text':'后来' if action=='CHANGE' else '',
        'time_evidence_id':'s2' if action=='CHANGE' else None}


def provider(item):
    from app.profile_relations import RelationProvider
    class Chat:
        def complete(self,system,payload):
            return {'relations':[item]},'test-model'
    return RelationProvider(Chat())


@pytest.mark.parametrize('action',['SUPPORT','CONFLICT','CHANGE'])
def test_proposed_relation_maps_to_real_ids_and_retains_source(action):
    output=provider(relation(action)).propose(sample(action))
    item=output.relations[0]
    assert item.candidate_id=='new' and item.target_candidate_id=='old'
    assert item.evidence_ids==['a','b'] and item.action==action
    assert output.model_version=='test-model'


@pytest.mark.parametrize('bad',['target','evidence','time','duplicate','unsupported_pair'])
def test_relation_with_unverifiable_basis_fails_closed(bad):
    data=sample('CHANGE'); item=relation('CHANGE')
    if bad=='target': item['target_candidate_id']='unknown'
    if bad=='evidence': item['evidence_ids']=['s1']
    if bad=='time': item['time_text']='2025年8月'
    if bad=='duplicate':
        item=relation(); data.materials[1].excerpt=data.materials[0].excerpt
    if bad=='unsupported_pair': data.targets[0].domain='RELATIONSHIPS'
    with pytest.raises(AIOutputInvalid): provider(item).propose(data)


def test_http_relation_endpoint_accepts_json_body():
    from fastapi.testclient import TestClient
    from app.api import create_app
    from app.config import Settings
    class Profiles:
        def propose_relations(self, payload):
            return provider(relation()).propose(payload)
    with TestClient(create_app(Settings(provider='fixture', environment='test'),
                              profile_provider=Profiles())) as client:
        response = client.post('/profile-relations', json=sample().model_dump())
    assert response.status_code == 200, response.text
    assert response.json()['relations'][0]['candidate_id'] == 'new'
