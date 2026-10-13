from datetime import timedelta
from sqlalchemy import select
from app.models import Account, DeviceCredential, Subject, utcnow
from app.tokens import hash_actor_token

BODY={'username':'tester_one','password':'a-long-test-password','display_name':'测试记录者'}

def test_eight_character_password_register_login_and_admin_reset(client,session):
    from app.account_admin import reset_password
    body={**BODY,'password':'story008'}
    registered=client.post('/api/v1/accounts/register',json=body)
    assert registered.status_code==201
    credentials={k:body[k] for k in ('username','password')}
    login=client.post('/api/v1/accounts/login',json=credentials)
    assert login.status_code==200
    old={'Authorization':'Bearer '+login.json()['actor_token']}
    reset_password(session,body['username'],'flower08');session.commit()
    assert client.get('/api/v1/session',headers=old).status_code==401
    assert client.post('/api/v1/accounts/login',json=credentials).status_code==401
    assert client.post('/api/v1/accounts/login',json={**credentials,'password':'flower08'}).status_code==200

def test_seven_character_password_is_rejected(client):
    assert client.post('/api/v1/accounts/register',json={**BODY,'password':'short07'}).status_code==422

def test_register_login_logout_and_space_isolation(client,session):
    created=client.post('/api/v1/accounts/register',json=BODY)
    assert created.status_code==201,created.text
    data=created.json();headers={'Authorization':'Bearer '+data['actor_token']}
    account=session.get(Account,BODY['username'])
    assert account.password_hash!=BODY['password']
    assert 'HttpOnly' in created.headers['set-cookie']
    assert 'SameSite=strict' in created.headers['set-cookie']
    spaces=client.get('/api/v1/workbench/spaces',headers=headers).json()['items']
    assert len(spaces)==1 and spaces[0]['role']=='owner'
    assert client.get('/api/v1/workbench/subjects/'+spaces[0]['subject_id']+'/stories',headers=headers).json()['items']==[]
    assert client.post('/api/v1/accounts/login',json={**{k:BODY[k] for k in ('username','password')},'password':'wrong-password'}).status_code==401
    # Cookie writes require same-origin; Android bearer requests do not.
    assert client.post('/api/v1/accounts/logout').status_code==401
    assert client.post('/api/v1/accounts/logout',headers={'Origin':'http://testserver'}).status_code==200
    assert client.get('/api/v1/session',headers=headers).status_code==401
    login=client.post('/api/v1/accounts/login',json={k:BODY[k] for k in ('username','password')})
    assert login.status_code==200
    newtoken=login.json()['actor_token'];assert newtoken!=data['actor_token']
    device=session.get(DeviceCredential,hash_actor_token(newtoken));device.expires_at=utcnow()-timedelta(seconds=1);session.commit()
    assert client.get('/api/v1/session',headers={'Authorization':'Bearer '+newtoken}).status_code==401

def test_registration_does_not_claim_old_space(client,session):
    session.add(Subject(subject_id='unmapped',display_name='旧资料'));session.commit()
    result=client.post('/api/v1/accounts/register',json=BODY)
    assert result.status_code==201
    session.expire_all();assert session.get(Subject,'unmapped').owner_actor_id is None
    assert client.post('/api/v1/accounts/register',json=BODY).status_code==422

def test_auth_rate_limit_and_remote_transport(client):
    for _ in range(10):
        assert client.post('/api/v1/accounts/login',json={k:BODY[k] for k in ('username','password')}).status_code==401
    assert client.post('/api/v1/accounts/login',json={k:BODY[k] for k in ('username','password')}).status_code==429
    assert client.post('/api/v1/accounts/register',json=BODY,headers={'Origin':'https://attacker.invalid'}).status_code==422
    assert client.post('http://remote.invalid/api/v1/accounts/register',json=BODY).status_code==422


def test_admin_account_works_with_closed_registration_and_reset_revokes_sessions(app,client,session):
    from app.account_admin import create_account, reset_password
    app.state.settings.allow_account_registration=False
    assert client.post('/api/v1/accounts/register',json=BODY).status_code==422
    created=create_account(session,**BODY)
    session.commit()
    credentials={k:BODY[k] for k in ('username','password')}
    login=client.post('/api/v1/accounts/login',json=credentials)
    assert login.status_code==200
    old={'Authorization':'Bearer '+login.json()['actor_token']}
    assert client.get('/api/v1/workbench/spaces',headers=old).json()['items'][0]['role']=='owner'
    reset_password(session,BODY['username'],'a-different-test-password');session.commit()
    assert client.get('/api/v1/session',headers=old).status_code==401
    assert client.post('/api/v1/accounts/login',json=credentials).status_code==401
    assert client.post('/api/v1/accounts/login',json={**credentials,'password':'a-different-test-password'}).status_code==200
    assert 'password' not in created


def test_password_reset_during_login_cannot_issue_session_for_old_password(app,client,session,monkeypatch):
    from app.api import accounts
    from app import account_admin
    client.post('/api/v1/accounts/register',json=BODY)
    digest=accounts.password_digest
    def interrupted(password,salt):
        result=digest(password,salt)
        with app.state.database.session() as other:
            from app.access import publication_lock
            publication_lock(other,'')
            account_admin.reset_password(other,BODY['username'],'new-password-after-reset')
            other.commit()
        return result
    monkeypatch.setattr(accounts,'password_digest',interrupted)
    response=client.post('/api/v1/accounts/login',json={k:BODY[k] for k in ('username','password')})
    assert response.status_code==401
