"""QA dispatch cannot alter a signed room's identity or microphone-only grants."""
import base64
import copy
import hashlib
import hmac
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools/verification'))
from rtc_test_dispatch import dispatch_ticket


def encode(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b'=').decode()


def fixture(tmp_path, *, sources=None):
    secret='fixture-only-secret'
    (tmp_path/'realtime.env').write_text('REMEMBER_LIVEKIT_API_KEY=fixture-key\nREMEMBER_LIVEKIT_API_SECRET='+secret+'\n')
    claims={'iss':'fixture-key','sub':'qa-user','exp':2000000000,
            'video':{'room':'qa-room','canPublishSources':sources or ['microphone']},
            'roomConfig':{'agents':[{'agentName':'remember-twin','metadata':json.dumps({'call_id':'qa-room'})}]},
            'metadata':'fixture-call-binding'}
    body=encode({'alg':'HS256'})+'.'+encode(claims)
    signature=base64.urlsafe_b64encode(hmac.new(secret.encode(),body.encode(),hashlib.sha256).digest()).rstrip(b'=').decode()
    return {'token':body+'.'+signature,'room':'qa-room','call_id':'qa-room','participant_identity':'qa-user'},claims


def test_staging_changes_only_agent_and_production_ticket_is_unchanged(tmp_path):
    ticket,original=fixture(tmp_path)
    assert dispatch_ticket(ticket,None,tmp_path) is ticket
    changed=dispatch_ticket(ticket,'remember-twin-qa',tmp_path)
    part=changed['token'].split('.')[1]
    claims=json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))
    assert claims['roomConfig']['agents'][0]['agentName']=='remember-twin-qa'
    assert json.loads(claims['roomConfig']['agents'][0]['metadata'])=={'call_id':'qa-room'}
    restored=copy.deepcopy(claims);restored['roomConfig']['agents'][0]['agentName']=original['roomConfig']['agents'][0]['agentName']
    assert restored==original and ticket['token']!=changed['token']


@pytest.mark.parametrize('tamper',['signature','room','sources','agent','participant','call'])
def test_tampered_or_broadened_qa_ticket_is_rejected(tmp_path,tamper):
    ticket,_=fixture(tmp_path,sources=['microphone','camera'] if tamper=='sources' else None)
    agent='remember-twin-qa'
    if tamper=='signature':ticket['token']=ticket['token'][:-2]+'AA'
    if tamper=='room':ticket['room']='another-room'
    if tamper=='agent':agent='agent with spaces'
    if tamper=='participant':ticket['participant_identity']='another-user'
    if tamper=='call':ticket['call_id']='another-call'
    with pytest.raises(ValueError):dispatch_ticket(ticket,agent,tmp_path)
