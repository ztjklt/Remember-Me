"""Isolated route/database tests. Fake delivery is NOT real SMS/email evidence."""
from datetime import timedelta
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select
import pytest

from app.contact_delivery import ContactVault, DeliveryUnavailable, normalize_contact
from app.contact_entrustment_models import ContactEntrustment, ReceiptChallenge, ReceiptSession
from app.models import Consent, Episode, utcnow
from test_companion import prepare, post
from test_companion_audio import upload

PUBLIC = '/api/v1/entrustment-receipts'


class FakeDelivery:
    def __init__(self): self.messages = []; self.fail = False
    def available(self, channel, *, notice=False): return True
    def send(self, channel, contact, **payload):
        self.messages.append((channel, contact, payload))
        if self.fail: raise DeliveryUnavailable('provider failure')


@pytest.fixture
def configured(app, client, session):
    app.state.settings.contact_entrustment_key = SecretStr(Fernet.generate_key().decode())
    app.state.settings.contact_entrustment_public_url = 'http://testserver'
    app.state.contact_delivery = FakeDelivery()
    o, c, r, oh, ch, rh, ep, companion = prepare(app, client, session)
    return o, oh, rh, ep, companion.removesuffix('/companion') + '/contact-entrustments', companion


def create(client, values, sources=None, **changes):
    o, oh, rh, ep, root, _ = values
    sources = sources if sources is not None else [{'kind':'episode', 'id':ep}]
    preview = post(client, root+'/preview', oh, {'sources':sources})
    body = {'recipient_label':'家人', 'channel':'email', 'contact':'family@example.test', 'title':'留给你',
            'message':'想说的话', 'sources':sources, 'source_version':preview['source_version'],
            'days':30, 'confirmed':True, 'idempotency_key':'plan-1'} | changes
    result = post(client, root, oh, body, 201)
    return result, body


def challenge(client, plan, contact='family@example.test', status=200):
    return post(client, PUBLIC+'/challenges', {}, {'invite_token':plan['claim_url'].split('#')[1], 'contact':contact}, status)


def unlock(app, client, plan):
    otp = challenge(client, plan)
    body = {'invite_token':plan['claim_url'].split('#')[1], 'challenge_id':otp['challenge_id'],
            'code':app.state.contact_delivery.messages[-1][2]['code']}
    response = post(client, PUBLIC+'/verify', {}, body)
    return {'Authorization':'Bearer '+response['session_token']}, body


def test_missing_delivery_is_visible_and_never_claims_created(app,client,session):
    o,_,_,oh,_,_,ep,companion=prepare(app,client,session)
    root=companion.removesuffix('/companion')+'/contact-entrustments'
    result=client.get(root,headers=oh)
    assert result.json()['capabilities']==dict(email=False,sms=False,notice_email=False,notice_sms=False)
    assert client.post(root,headers=oh,json={'recipient_label':'家人','channel':'email','contact':'a@example.test',
        'title':'给你','message':'你好','source_version':'0'*64,'confirmed':True,'idempotency_key':'no-config'}).status_code==503
    assert session.query(ContactEntrustment).count()==0


def test_account_free_multi_audio_scope_encryption_and_revoke(configured,app,client,session):
    o,oh,rh,ep,root,companion=configured
    dedicated=upload(client,companion,oh,purpose='letter')['audio_id']
    excluded=upload(client,companion,oh,purpose='letter',key='excluded')['audio_id']
    plan,body=create(client,configured,[{'kind':'episode','id':ep},{'kind':'dedicated','id':dedicated}])
    assert post(client,root,oh,body,201)['id']==plan['id']
    assert client.post(root,headers=oh,json=body|{'message':'different'}).status_code==409
    stored=session.get(ContactEntrustment,plan['id'])
    assert 'family@example.test' not in stored.contact_cipher
    assert plan['claim_url'].split('#')[1] not in stored.invite_cipher
    assert client.get(PUBLIC+'/content').status_code==404
    assert client.get(root,headers=rh).status_code==404
    headers,verify_body=unlock(app,client,plan)
    assert client.get(root,headers=headers).status_code==401
    result=client.get(PUBLIC+'/content',headers=headers)
    assert result.status_code==200,result.text
    assert {(x['kind'],x['id']) for x in result.json()['items']}=={('episode',ep),('dedicated',dedicated)}
    assert 'memories' not in result.text and 'object_key' not in result.text
    assert result.headers['cache-control']=='no-store'
    assert client.get(PUBLIC+'/audio/dedicated/'+dedicated,headers=headers).content==b'OWN-TEST-AUDIO'
    assert client.get(PUBLIC+'/audio/dedicated/'+excluded,headers=headers).status_code==404
    assert client.post(PUBLIC+'/verify',json=verify_body).status_code==404
    assert post(client,root+'/'+plan['id']+'/revoke',oh,{'revision':1})['status']=='revoked'
    assert client.get(PUBLIC+'/content',headers=headers).status_code==404
    assert client.get(PUBLIC+'/audio/dedicated/'+dedicated,headers=headers).status_code==404
    challenge(client,plan,status=404)


@pytest.mark.parametrize('change',['transcript','consent','expired','session_expired'])
def test_changed_source_consent_and_expiry_block_existing_recipient(configured,app,client,session,change):
    o,oh,rh,ep,root,_=configured
    plan,_=create(client,configured);headers,_=unlock(app,client,plan)
    session.expire_all()
    if change=='transcript': session.get(Episode,ep).transcript='Changed after confirmation'
    elif change=='consent': session.get(Consent,o.consent_id).status='revoked'
    elif change=='expired': session.get(ContactEntrustment,plan['id']).expires_at=utcnow()-timedelta(seconds=1)
    else: session.scalar(select(ReceiptSession)).expires_at=utcnow()-timedelta(seconds=1)
    session.commit()
    assert client.get(PUBLIC+'/content',headers=headers).status_code==404
    assert client.get(PUBLIC+'/audio/episode/'+ep,headers=headers).status_code==404


def test_contact_match_otp_rate_and_attempt_lockout(configured,app,client,session):
    plan,_=create(client,configured)
    challenge(client,plan,'stranger@example.test',404)
    assert not app.state.contact_delivery.messages
    otp=challenge(client,plan);challenge(client,plan,status=429)
    correct=app.state.contact_delivery.messages[-1][2]['code']
    wrong='000000' if correct!='000000' else '999999'
    body={'invite_token':plan['claim_url'].split('#')[1],'challenge_id':otp['challenge_id'],'code':wrong}
    for _ in range(5): assert client.post(PUBLIC+'/verify',json=body).status_code==404
    assert client.post(PUBLIC+'/verify',json=body|{'code':correct}).status_code==404
    session.expire_all();assert session.get(ReceiptChallenge,otp['challenge_id']).attempts==5


def test_otp_is_bound_to_plan_and_expiry(configured,app,client,session):
    first,_=create(client,configured)
    second,_=create(client,configured,idempotency_key='second')
    otp=challenge(client,first)
    body={'invite_token':second['claim_url'].split('#')[1],'challenge_id':otp['challenge_id'],
          'code':app.state.contact_delivery.messages[-1][2]['code']}
    assert client.post(PUBLIC+'/verify',json=body).status_code==404
    row=session.get(ReceiptChallenge,otp['challenge_id']);row.expires_at=utcnow()-timedelta(seconds=1);session.commit()
    assert client.post(PUBLIC+'/verify',json=body|{'invite_token':first['claim_url'].split('#')[1]}).status_code==404


def test_failed_delivery_cannot_verify_or_fake_read_status(configured,app,client,session):
    _,oh,_,_,root,_=configured;plan,_=create(client,configured)
    app.state.contact_delivery.fail=True
    challenge(client,plan,status=503)
    row=session.scalar(select(ReceiptChallenge))
    body={'invite_token':plan['claim_url'].split('#')[1],'challenge_id':row.id,'code':app.state.contact_delivery.messages[-1][2]['code']}
    assert client.post(PUBLIC+'/verify',json=body).status_code==404
    assert client.post(root+'/'+plan['id']+'/notify',headers=oh).status_code==503
    result=client.get(root,headers=oh).json()['items'][0]
    assert result['notice_status']=='unconfirmed' and result['opened_at'] is None


def test_text_only_notify_and_explicit_session_end(configured,app,client):
    _,oh,_,_,root,_=configured;plan,_=create(client,configured,sources=[])
    result=post(client,root+'/'+plan['id']+'/notify',oh,{})
    assert result['notice_status']=='accepted' and result['claimed_at'] is None
    assert len(app.state.contact_delivery.messages)==1
    headers,_=unlock(app,client,plan)
    assert client.get(PUBLIC+'/content',headers=headers).json()['items']==[]
    assert client.delete(PUBLIC+'/session',headers=headers).json()['ended']
    assert client.get(PUBLIC+'/content',headers=headers).status_code==404


def test_foreign_source_and_unconfirmed_selection_never_publish(configured,app,client,session):
    _,oh,rh,ep,root,companion=configured
    assert client.post(root+'/preview',headers=rh,json={'sources':[{'kind':'episode','id':ep}]}).status_code==404
    assert client.post(root+'/preview',headers=oh,json={'sources':[{'kind':'dedicated','id':'unknown'}]}).status_code==404
    plan,body=create(client,configured)
    assert client.post(root,headers=oh,json=body|{'confirmed':False,'idempotency_key':'new'}).status_code==422
    assert client.post(root,headers=oh,json=body|{'source_version':'0'*64,'idempotency_key':'new'}).status_code==409
    assert client.post(root+'/preview',headers=oh,json={'sources':body['sources']*2}).status_code==422
    assert client.post(root+'/'+plan['id']+'/revoke',headers=rh,json={'revision':1}).status_code==404


@pytest.mark.parametrize('channel,value,expected',[
    ('sms','138 0013 8000','+8613800138000'),('sms','008613800138000','+8613800138000'),
    ('email',' Family@Example.test ','family@example.test'),
])
def test_normalization(channel,value,expected): assert normalize_contact(channel,value)==expected


@pytest.mark.parametrize('channel,value',[('email','a\r\nBcc:x@y.test'),('email','a..b@example.test'),('sms','+15555555555')])
def test_invalid_contacts(channel,value):
    from app.errors import RequestInvalid
    with pytest.raises(RequestInvalid): normalize_contact(channel,value)


def test_receipt_page_has_no_third_party_assets_or_inline_scripts(client):
    response=client.get('/receive/')
    assert response.status_code==200
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert response.headers['referrer-policy']=='no-referrer'
    assert '<script defer src="/receive/receipt.js"></script>' in response.text
    assert '有些话' in response.text
    assert client.get('/receive/receipt.js').status_code==200


def test_revocation_during_provider_send_cannot_publish_late_code(configured,app,client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from fastapi.testclient import TestClient
    _,oh,_,_,root,_=configured;plan,_=create(client,configured)
    entered,release=Event(),Event()
    class Delayed(FakeDelivery):
        def send(self,*args,**kwargs):
            entered.set();assert release.wait(15)
            super().send(*args,**kwargs)
    app.state.contact_delivery=Delayed()
    def send():
        with TestClient(app) as other:
            return other.post(PUBLIC+'/challenges',json={'invite_token':plan['claim_url'].split('#')[1],'contact':'family@example.test'})
    with ThreadPoolExecutor() as pool:
        future=pool.submit(send)
        assert entered.wait(15)
        try: post(client,root+'/'+plan['id']+'/revoke',oh,{'revision':1})
        finally: release.set()
        assert future.result().status_code==404
    challenge(client,plan,status=404)


def test_additive_migration_preserves_existing_account_letters(configured,app,client,settings):
    from alembic import command
    from conftest import alembic_config
    _,oh,rh,ep,root,companion=configured
    # Existing account letters remain an independent API; recipient comes from seeded actor token.
    from app.models import Actor
    with app.state.database.session() as session:
        actor=session.scalar(select(Actor).where(Actor.actor_id!=configured[0].actor_id))
        recipient=actor.actor_id
    letter=post(client,companion+'/letters',oh,{'recipient_actor_id':recipient,'title':'旧信','text':'保留原内容','idempotency_key':'old-letter'},201)
    command.downgrade(alembic_config(settings.database_url),'0021_twin_review_summary')
    command.upgrade(alembic_config(settings.database_url),'head')
    result=client.get(companion+'/letters',headers=oh)
    assert result.status_code==200,result.text
    assert any(x['id']==letter['id'] and x['text']=='保留原内容' for x in result.json()['items'])


def test_sources_and_contract_match_native_inputs(configured,client):
    import json
    from pathlib import Path
    from jsonschema import Draft202012Validator
    _,oh,_,ep,root,_=configured
    sources=client.get(root+'/sources',headers=oh)
    assert sources.status_code==200 and any(x['id']==ep for x in sources.json()['items'])
    _,body=create(client,configured)
    schema=json.loads((Path(__file__).resolve().parents[3]/'packages/contracts/schemas/contact-entrustment-v1.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator(schema).validate(body)


def test_revoke_during_storage_read_rejects_late_audio_without_blocking_owner(configured,app,client,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from fastapi.testclient import TestClient
    _,oh,_,ep,root,_=configured;plan,_=create(client,configured);headers,_=unlock(app,client,plan)
    entered,release=Event(),Event();original=app.state.object_store.get
    def delayed(key): entered.set();assert release.wait(15);return original(key)
    monkeypatch.setattr(app.state.object_store,'get',delayed)
    def load():
        with TestClient(app) as other:return other.get(PUBLIC+'/audio/episode/'+ep,headers=headers)
    with ThreadPoolExecutor() as pool:
        future=pool.submit(load);assert entered.wait(15)
        try: post(client,root+'/'+plan['id']+'/revoke',oh,{'revision':1})
        finally: release.set()
        result=future.result();assert result.status_code==404,result.text


def test_missing_audio_returns_safe_failure(configured,app,client,monkeypatch):
    _,_,_,ep,_,_=configured;plan,_=create(client,configured);headers,_=unlock(app,client,plan)
    def missing(key):raise FileNotFoundError('private/object/key')
    monkeypatch.setattr(app.state.object_store,'get',missing)
    result=client.get(PUBLIC+'/audio/episode/'+ep,headers=headers)
    assert result.status_code==503 and 'private/object/key' not in result.text
