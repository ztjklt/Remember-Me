"""Operator-only provisioning: python -m app.account_admin create USER --name NAME.
Use reset USER to replace password and revoke sessions. No secrets on argv.
"""
import argparse
import getpass
import secrets
from uuid import uuid4
from sqlalchemy import delete
from .api.accounts import Registration, Credentials, password_digest
from .models import Account, Actor, Subject, DeviceCredential, PairingCode
from .tokens import generate_actor_token, hash_actor_token
from .errors import RequestInvalid


def create_account(session, username, password, display_name):
    body=Registration(username=username,password=password,display_name=display_name)
    if session.get(Account,body.username):raise RequestInvalid('账号已存在。')
    actor=Actor(actor_id='actor_'+uuid4().hex,display_name=body.display_name,token_hash=hash_actor_token(generate_actor_token()))
    session.add(actor);session.flush()
    salt=secrets.token_hex(16)
    session.add(Account(username=body.username,actor_id=actor.actor_id,salt=salt,password_hash=password_digest(body.password,salt)))
    subject=Subject(subject_id='subject_'+uuid4().hex,display_name=body.display_name,owner_actor_id=actor.actor_id)
    session.add(subject);session.flush()
    return {'username':body.username,'actor_id':actor.actor_id,'subject_id':subject.subject_id}


def reset_password(session,username,password):
    body=Credentials(username=username,password=password)
    account=session.get(Account,body.username)
    if account is None:raise RequestInvalid('账号不存在。')
    account.salt=secrets.token_hex(16);account.password_hash=password_digest(body.password,account.salt)
    session.execute(delete(DeviceCredential).where(DeviceCredential.actor_id==account.actor_id))
    session.execute(delete(PairingCode).where(PairingCode.actor_id==account.actor_id))
    session.get(Actor,account.actor_id).token_hash=hash_actor_token(generate_actor_token())
    return {'username':body.username,'sessions_revoked':True}


def main():
    from .config import get_settings
    from .db import Database
    from .access import publication_lock
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['create','reset']);p.add_argument('username');p.add_argument('--name')
    args=p.parse_args()
    if args.action=='create' and not args.name:p.error('create requires --name')
    password=getpass.getpass('Password (8-128 characters): ')
    if password!=getpass.getpass('Repeat password: '):raise SystemExit('Passwords differ; nothing changed')
    db=Database(get_settings().database_url)
    try:
        with db.session() as session:
            publication_lock(session,'')
            result=create_account(session,args.username,password,args.name) if args.action=='create' else reset_password(session,args.username,password)
            session.commit()
        print('Account updated:',result['username'])
    finally:db.dispose()


if __name__=='__main__':main()
