"""Explicit account creation never claims legacy subjects. No provider secrets here."""
from datetime import timedelta
import hashlib
import hmac
import secrets
from uuid import uuid4
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..access import publication_lock
from ..db import get_session
from ..errors import AppError, AuthInvalid, RequestInvalid
from ..models import Account, AccountAttempt, Actor, Subject, DeviceCredential, utcnow
from ..tokens import generate_actor_token, hash_actor_token
from ..security import current_actor

router=APIRouter(prefix='/api/v1/accounts',tags=['accounts'])
COOKIE='remember_session'

class Credentials(BaseModel):
    model_config=ConfigDict(extra='forbid')
    username: str=Field(min_length=3,max_length=64,pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str=Field(min_length=10,max_length=128)
    @field_validator('username')
    @classmethod
    def normalize(cls,value): return value.lower()

class Registration(Credentials):
    display_name: str=Field(min_length=1,max_length=80)
    @field_validator('display_name')
    @classmethod
    def nonblank(cls,value):
        if not value.strip(): raise ValueError('请填写称呼')
        return value.strip()

class RateLimited(AppError):
    code='AUTH_RATE_LIMITED'
    http_status=429

def transport(request):
    settings=request.app.state.settings
    # An untrusted Host header does not make a remote connection local.
    peer=request.client.host if request.client else ''
    local=peer in {'127.0.0.1','::1','testclient'} and request.url.hostname in {'127.0.0.1','localhost','[::1]','testserver'}
    if request.url.scheme!='https' and not (settings.environment in {'development','test'} and local):
        raise RequestInvalid('账号登录需要HTTPS；本机开发连接可使用回环地址。')
    origin=request.headers.get('origin')
    if origin and origin!=str(request.base_url).rstrip('/'):
        raise RequestInvalid('请求来源与服务地址不一致。')

def throttle(session,request,username):
    ip=request.client.host if request.client else 'unknown'
    nh,ih=hash_actor_token(username),hash_actor_token(ip)
    publication_lock(session,'')
    recent=AccountAttempt.created_at>=utcnow()-timedelta(minutes=5)
    count=lambda col,value:session.scalar(select(func.count()).select_from(AccountAttempt).where(recent,col==value))
    if count(AccountAttempt.name_hash,nh)>=10 or count(AccountAttempt.ip_hash,ih)>=60:
        session.rollback();raise RateLimited('尝试次数过多，请5分钟后再试。')
    session.execute(delete(AccountAttempt).where(AccountAttempt.created_at<utcnow()-timedelta(hours=1)))
    session.add(AccountAttempt(attempt_id=uuid4().hex,name_hash=nh,ip_hash=ih))
    session.commit()

def password_digest(password,salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600_000).hex()

def issue(session,actor,request,response):
    token=generate_actor_token();expiry=utcnow()+timedelta(days=30)
    session.add(DeviceCredential(token_hash=hash_actor_token(token),actor_id=actor.actor_id,expires_at=expiry))
    session.commit()
    response.headers['Cache-Control']='no-store'
    response.set_cookie(COOKIE,token,max_age=30*86400,httponly=True,secure=request.url.scheme=='https',samesite='strict',path='/')
    return {'actor_token':token,'actor_id':actor.actor_id,'display_name':actor.display_name,'expires_at':expiry.isoformat()}

@router.post('/register',status_code=201)
def register(payload:Registration,request:Request,response:Response,session:Session=Depends(get_session)):
    transport(request)
    settings=request.app.state.settings
    allowed=settings.allow_account_registration
    if not (allowed if allowed is not None else settings.environment in {'development','test'}):
        raise RequestInvalid('此服务尚未开放注册，请联系服务管理员。')
    throttle(session,request,payload.username)
    salt=secrets.token_hex(16);digest=password_digest(payload.password,salt)
    actor=Actor(actor_id='actor_'+uuid4().hex,display_name=payload.display_name,token_hash=hash_actor_token(generate_actor_token()))
    session.add(actor);session.flush()
    session.add(Account(username=payload.username,actor_id=actor.actor_id,salt=salt,password_hash=digest))
    session.add(Subject(subject_id='subject_'+uuid4().hex,display_name=payload.display_name,owner_actor_id=actor.actor_id))
    try: session.flush()
    except IntegrityError:
        session.rollback();raise RequestInvalid('这个账号暂不可用，请换一个账号名。')
    return issue(session,actor,request,response)

@router.post('/login')
def login(payload:Credentials,request:Request,response:Response,session:Session=Depends(get_session)):
    transport(request);throttle(session,request,payload.username)
    account=session.get(Account,payload.username)
    digest=password_digest(payload.password,account.salt if account else '00'*16)
    if not account or not hmac.compare_digest(digest,account.password_hash):
        raise AuthInvalid('账号或密码不正确。')
    return issue(session,session.get(Actor,account.actor_id),request,response)

@router.post('/logout')
def logout(request:Request,response:Response,actor:Actor=Depends(current_actor),session:Session=Depends(get_session)):
    token=request.headers.get('authorization','').removeprefix('Bearer ').strip() or request.cookies.get(COOKIE,'')
    session.execute(delete(DeviceCredential).where(DeviceCredential.token_hash==hash_actor_token(token),DeviceCredential.actor_id==actor.actor_id))
    session.commit();response.delete_cookie(COOKIE,path='/');response.headers['Cache-Control']='no-store'
    return {'signed_out':True}
