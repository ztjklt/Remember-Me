"""A code binds an account; only the owner can publish the actual grants."""
from datetime import timedelta
from typing import Literal
import secrets
from uuid import uuid4
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from ..access import publication_lock, require_owner, Hidden
from ..db import get_session
from ..errors import RequestInvalid
from ..models import Account, Actor, ShareInvitation, StoryGrant, utcnow, as_utc
from ..security import current_actor
from ..sharing import preview, grant_batch, SharingChanged
from ..tokens import hash_actor_token
from ..retrieval import invalidate_answers

router=APIRouter(prefix='/api/v1/workbench',tags=['sharing'])


class Selection(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    episode_ids:list[str]=Field(default_factory=list,max_length=30)
    story_ids:list[str]=Field(default_factory=list,max_length=30)


class InvitationInput(Selection):
    source_version:str=Field(min_length=64,max_length=64)
    include_audio_confirmed:Literal[True]
    cloud_processing_allowed:bool=False
    recipient_actor_id:str|None=None


class ClaimInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    code:str=Field(min_length=16,max_length=100)


def state(row):
    return 'expired' if row.status in {'created','claimed'} and as_utc(row.expires_at)<=utcnow() else row.status


def contact(session,id):
    actor=session.get(Actor,id) if id else None
    account=session.scalar(select(Account).where(Account.actor_id==id)) if id else None
    return {'actor_id':id,'username':account.username,'display_name':actor.display_name} if account and actor else None


def view(session,row,owner=True):
    data={'id':row.id,'status':state(row),'expires_at':as_utc(row.expires_at).isoformat()}
    if owner:
        data.update(selection=row.selection,source_version=row.source_version,recipient=contact(session,row.recipient_actor_id),
            cloud_processing_allowed=row.cloud_processing_allowed,grant_ids=row.grant_ids,
            scope=row.selection.get('scope_preview',[]))
    else:
        data['sender']=contact(session,row.creator_actor_id)
    return data


@router.post('/subjects/{subject_id}/sharing/preview')
def sharing_preview(subject_id:str,body:Selection,response:Response,actor=Depends(current_actor),session=Depends(get_session)):
    response.headers['Cache-Control']='no-store'
    return preview(session,subject_id,actor.actor_id,body.model_dump())


@router.get('/subjects/{subject_id}/recipients')
def recipients(subject_id:str,actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id)
    ids=set(session.scalars(select(ShareInvitation.recipient_actor_id).where(
        ShareInvitation.subject_id==subject_id,ShareInvitation.approved_at.is_not(None))))
    return {'items':[c for id in sorted(ids) if (c:=contact(session,id))]}


@router.get('/subjects/{subject_id}/invitations')
def invitations(subject_id:str,actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id)
    return {'items':[view(session,r) for r in session.scalars(select(ShareInvitation).where(
        ShareInvitation.subject_id==subject_id).order_by(ShareInvitation.created_at.desc()))]}


@router.post('/subjects/{subject_id}/invitations',status_code=201)
def create(subject_id:str,body:InvitationInput,response:Response,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id)
    selection=body.model_dump(include={'episode_ids','story_ids'})
    data=preview(session,subject_id,actor.actor_id,selection)
    if data['source_version']!=body.source_version:
        raise SharingChanged('分享内容已变化，请重新预览。')
    selection['scope_preview']=[{'episode_id':item['episode_id'],'recorded_at':item['recorded_at'],
        'duration_ms':item['duration_ms'],'title':(next(iter(item['memories']),None) or item['transcript'])[:80]}
        for item in data['items']]
    if contact(session,actor.actor_id) is None:
        raise RequestInvalid('请使用普通账号登录后邀请亲友。')
    if body.recipient_actor_id:
        known=session.scalar(select(ShareInvitation.id).where(ShareInvitation.subject_id==subject_id,
            ShareInvitation.recipient_actor_id==body.recipient_actor_id,ShareInvitation.approved_at.is_not(None)))
        if not known or contact(session,body.recipient_actor_id) is None:
            raise RequestInvalid('首次分享需要亲友领取邀请并由本人核对账号。')
    code=None if body.recipient_actor_id else secrets.token_urlsafe(24)
    row=ShareInvitation(id='invite_'+uuid4().hex,subject_id=subject_id,creator_actor_id=actor.actor_id,
        recipient_actor_id=body.recipient_actor_id,code_hash=hash_actor_token(code) if code else None,
        status='claimed' if body.recipient_actor_id else 'created',selection=selection,
        source_version=body.source_version,cloud_processing_allowed=body.cloud_processing_allowed,
        expires_at=utcnow()+timedelta(hours=24))
    session.add(row);session.commit();response.headers['Cache-Control']='no-store'
    result=view(session,row)
    if code:result['code']=code
    return result


@router.post('/invitations/claim')
def claim(body:ClaimInput,request:Request,response:Response,actor=Depends(current_actor),session=Depends(get_session)):
    from .accounts import throttle
    throttle(session,request,'invite-claim:'+actor.actor_id)
    publication_lock(session,'')
    row=session.scalar(select(ShareInvitation).where(ShareInvitation.code_hash==hash_actor_token(body.code)))
    if row is None or state(row) not in {'created','claimed'}:
        raise RequestInvalid('邀请码不可用、已处理或已过期，请联系邀请人。')
    if row.creator_actor_id==actor.actor_id or contact(session,actor.actor_id) is None:
        raise RequestInvalid('请由亲友使用独立普通账号领取。')
    if row.recipient_actor_id and row.recipient_actor_id!=actor.actor_id:
        raise RequestInvalid('邀请码已被其他账号领取。')
    row.recipient_actor_id=actor.actor_id;row.status='claimed';session.commit()
    response.headers['Cache-Control']='no-store'
    return view(session,row,False)


@router.post('/subjects/{subject_id}/invitations/{invitation_id}/{action}')
def act(subject_id:str,invitation_id:str,action:Literal['approve','reject','cancel','revoke'],request:Request,
        actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    row=session.get(ShareInvitation,invitation_id)
    if row is None or row.subject_id!=subject_id:raise Hidden('邀请不存在。')
    current=state(row)
    if action=='approve':
        if current=='approved':return view(session,row)
        if current!='claimed':raise RequestInvalid('邀请尚未领取、已过期或已结束。')
        if not row.selection.get('scope_preview'):
            raise SharingChanged('旧邀请缺少完整范围记录，请取消后重新预览。')
        data=preview(session,subject_id,actor.actor_id,row.selection)
        if data['source_version']!=row.source_version:raise SharingChanged('材料已变化，请取消并重新预览分享。')
        grants,created=grant_batch(session,subject_id,actor.actor_id,row.recipient_actor_id,data['episode_ids'],row.cloud_processing_allowed)
        row.grant_ids=[g.grant_id for g in grants];row.created_grant_ids=created
        row.status='approved';row.approved_at=utcnow()
    elif action=='revoke':
        if current=='revoked':return view(session,row)
        if current!='approved':raise RequestInvalid('只有已批准的分享可以撤权。')
        for id in row.created_grant_ids:
            grant=session.get(StoryGrant,id)
            if grant:grant.revoked_at=grant.revoked_at or utcnow()
        row.status='revoked'
    else:
        target='rejected' if action=='reject' else 'cancelled'
        if current==target:return view(session,row)
        if current not in {'created','claimed'}:raise RequestInvalid('这个邀请已结束。')
        row.status=target
    invalidate_answers(session,request.app.state.object_store,subject_id)
    session.commit()
    return view(session,row)
