"""Explicit, revocable delivery of selected sources to an account-free contact."""
import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, delete
from ..access import Hidden, require_owner, publication_lock
from ..contact_delivery import ContactDelivery, ContactVault, DeliveryUnavailable, mask_contact, normalize_contact, public_origin
from ..contact_entrustment_models import ContactEntrustment, ReceiptChallenge, ReceiptRate, ReceiptSession
from ..db import get_session
from ..errors import AppError, AudioUnavailable, IdempotencyConflict, RequestInvalid
from ..models import Consent, Episode, as_utc, utcnow
from ..persona_models import CompanionAudio
from ..security import current_actor
from ..sharing import SharingChanged, eligible

router = APIRouter(prefix='/api/v1/workbench/subjects/{subject_id}/contact-entrustments', tags=['contact-entrustment'])
receipts = APIRouter(prefix='/api/v1/entrustment-receipts', tags=['contact-receipt'])


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Source(Strict):
    kind: Literal['episode', 'dedicated']
    id: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')


class Selection(Strict):
    sources: list[Source] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def unique(self):
        if len({(s.kind, s.id) for s in self.sources}) != len(self.sources):
            raise ValueError('不能重复选择同一段音频。')
        return self


class Create(Selection):
    recipient_label: str = Field(min_length=1, max_length=80)
    channel: Literal['email', 'sms']
    contact: str = Field(min_length=3, max_length=254)
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(default='', max_length=10000)
    source_version: str = Field(min_length=64, max_length=64)
    days: int = Field(default=30, ge=1, le=90)
    confirmed: Literal[True]
    idempotency_key: str = Field(min_length=1, max_length=200)


class Revision(Strict):
    revision: int = Field(ge=1)


class ChallengeInput(Strict):
    invite_token: str = Field(min_length=40, max_length=100)
    contact: str = Field(min_length=3, max_length=254)


class Verify(Strict):
    invite_token: str = Field(min_length=40, max_length=100)
    challenge_id: str = Field(min_length=1, max_length=64)
    code: str = Field(pattern=r'^[0-9]{6}$')


class Limited(AppError):
    code = 'RECEIPT_RATE_LIMITED'
    http_status = 429


def delivery(request):
    return request.app.state.contact_delivery


def vault(request):
    return ContactVault(request.app.state.settings)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def source_snapshot(session, subject, owner, sources):
    require_owner(session, subject, owner)
    items, basis = [], []
    for source in sorted(sources, key=lambda s: (s['kind'], s['id'])):
        kind, id = source['kind'], source['id']
        if kind == 'episode':
            row = eligible(session, subject, owner, [id])[0]
            consent = session.get(Consent, row.recording_consent_id)
            if (consent is None or consent.status != 'granted' or consent.scope != 'RECORDING'
                    or consent.subject_id != subject or consent.granted_by_actor_id != row.actor_id):
                raise Hidden('这段录音的许可已失效。')
            if not row.audio_object_key or not row.audio_size_bytes:
                raise RequestInvalid('请选择有完整原音的录音。')
            items.append({'kind':kind, 'id':id, 'title':as_utc(row.recorded_at).strftime('%Y-%m-%d %H:%M'),
                          'duration_ms':row.duration_ms, 'text':row.transcript or '',
                          'supplement':(row.capture_metadata or {}).get('review_supplement', ''), 'has_audio':True})
        else:
            row = session.get(CompanionAudio, id)
            if row is None or row.subject_id != subject or row.author_actor_id != owner or row.purpose != 'letter':
                raise Hidden('这段专属录音不可用。')
            if row.status == 'transcribing': raise SharingChanged('声音正在转写，请稍后选择。')
            items.append({'kind':kind, 'id':id, 'title':'专属声音 · ' + as_utc(row.created_at).strftime('%m-%d %H:%M'),
                          'duration_ms':None, 'text':row.reviewed_text if row.status == 'confirmed' else '',
                          'supplement':'', 'has_audio':True})
        basis.append({c.name:getattr(row, c.name) for c in row.__table__.columns})
    return {'source_version':fingerprint(basis), 'items':items,
            'notice':'对方可以听以下每段完整原音和查看这里列出的文字。'}


def sources_value(body): return [s.model_dump() for s in body.sources]


def capabilities(request):
    try: vault(request); public_origin(request.app.state.settings)
    except DeliveryUnavailable: return {'email':False, 'sms':False, 'notice_email':False, 'notice_sms':False}
    provider = delivery(request)
    return {**{c:provider.available(c) for c in ('email', 'sms')},
            **{'notice_' + c:provider.available(c, notice=True) for c in ('email', 'sms')}}


def owner_plan(session, subject, actor, id):
    require_owner(session, subject, actor)
    row = session.get(ContactEntrustment, id)
    if row is None or row.subject_id != subject or row.author_actor_id != actor: raise Hidden('托付不存在。')
    return row


def active_snapshot(session, row):
    if row.status != 'active' or as_utc(row.expires_at) <= utcnow(): raise Hidden('这份托付已失效，请联系留下内容的人。')
    try:
        current = source_snapshot(session, row.subject_id, row.author_actor_id, row.sources)
    except AppError:
        raise Hidden('这份托付的来源已变化，请联系留下内容的人。') from None
    if current['source_version'] != row.source_version: raise Hidden('这份托付的来源已变化，请联系留下内容的人。')
    return current


def plan_view(row, session):
    status = row.status
    if status == 'active':
        if as_utc(row.expires_at) <= utcnow(): status = 'expired'
        else:
            try: active_snapshot(session, row)
            except AppError: status = 'source_changed'
    return {'id':row.id, 'title':row.title, 'recipient_label':row.recipient_label,
            'channel':row.channel, 'contact_mask':row.contact_mask, 'status':status, 'revision':row.revision,
            'source_count':len(row.sources), 'notice_status':row.notice_status,
            'claimed_at':as_utc(row.claimed_at).isoformat() if row.claimed_at else None,
            'opened_at':as_utc(row.opened_at).isoformat() if row.opened_at else None,
            'expires_at':as_utc(row.expires_at).isoformat()}


def rate(session, v, key, limit, seconds):
    hashed = v.digest('rate', key)
    row = session.get(ReceiptRate, hashed)
    now = utcnow()
    if row is None:
        row = ReceiptRate(key=hashed, hits=0, reset_at=now + timedelta(seconds=seconds)); session.add(row)
    elif as_utc(row.reset_at) <= now:
        row.hits = 0; row.reset_at = now + timedelta(seconds=seconds)
    if row.hits >= limit:
        session.commit()
        raise Limited('尝试次数较多，请稍后再试。')
    row.hits += 1


def public_lock(request, session, action):
    publication_lock(session, '')
    v = vault(request)
    # Do not trust an arbitrary X-Forwarded-For supplied by a browser.
    address = request.client.host if request.client else 'unknown'
    rate(session, v, action + ':ip:' + address, 30, 600)
    session.execute(delete(ReceiptRate).where(ReceiptRate.reset_at < utcnow() - timedelta(days=1)))
    return v


def invited(session, v, token):
    row = session.scalar(select(ContactEntrustment).where(ContactEntrustment.invite_hash == v.digest('invite', token)))
    if row is None:
        session.commit(); raise Hidden('链接或验证信息无效。')
    try: active_snapshot(session, row)
    except AppError:
        session.commit(); raise Hidden('链接或验证信息无效。') from None
    return row


@router.get('')
def plans(subject_id:str, request:Request, actor=Depends(current_actor), session=Depends(get_session)):
    require_owner(session, subject_id, actor.actor_id)
    rows = session.scalars(select(ContactEntrustment).where(ContactEntrustment.subject_id == subject_id,
        ContactEntrustment.author_actor_id == actor.actor_id).order_by(ContactEntrustment.confirmed_at.desc()).limit(100))
    return {'items':[plan_view(r, session) for r in rows], 'capabilities':capabilities(request)}


@router.get('/sources')
def available_sources(subject_id:str, actor=Depends(current_actor), session=Depends(get_session)):
    require_owner(session, subject_id, actor.actor_id)
    candidates = [{'kind':'episode', 'id':id} for id in session.scalars(select(Episode.episode_id).where(
        Episode.subject_id == subject_id, Episode.status == 'ready').order_by(Episode.recorded_at.desc()).limit(100))]
    candidates += [{'kind':'dedicated', 'id':id} for id in session.scalars(select(CompanionAudio.audio_id).where(
        CompanionAudio.subject_id == subject_id, CompanionAudio.author_actor_id == actor.actor_id,
        CompanionAudio.purpose == 'letter').order_by(CompanionAudio.created_at.desc()).limit(100))]
    result = []
    for value in candidates:
        try: result.extend(source_snapshot(session, subject_id, actor.actor_id, [value])['items'])
        except AppError: continue
    return {'items':result}


@router.post('/preview')
def preview(subject_id:str, body:Selection, actor=Depends(current_actor), session=Depends(get_session)):
    return source_snapshot(session, subject_id, actor.actor_id, sources_value(body))


@router.post('', status_code=201)
def create(subject_id:str, body:Create, request:Request, actor=Depends(current_actor), session=Depends(get_session)):
    publication_lock(session, subject_id); require_owner(session, subject_id, actor.actor_id)
    v = vault(request); origin = public_origin(request.app.state.settings)
    contact = normalize_contact(body.channel, body.contact)
    if not delivery(request).available(body.channel): raise DeliveryUnavailable('这个渠道还不能发送验证码，请先配置发送服务。')
    if not body.sources and not body.message.strip(): raise RequestInvalid('请录一段声音、选择录音或填写留言。')
    signature = v.digest('create', json.dumps(body.model_dump() | {'contact':contact}, sort_keys=True, ensure_ascii=False))
    row = session.scalar(select(ContactEntrustment).where(ContactEntrustment.subject_id == subject_id,
        ContactEntrustment.author_actor_id == actor.actor_id, ContactEntrustment.idempotency_key == body.idempotency_key))
    if row:
        if not hmac.compare_digest(row.request_hash, signature): raise IdempotencyConflict('同一请求不能更换接收者或内容。')
        active_snapshot(session, row)
    else:
        current = source_snapshot(session, subject_id, actor.actor_id, sources_value(body))
        if current['source_version'] != body.source_version: raise SharingChanged('内容已变化，请重新预览。')
        rate(session, v, 'create:' + actor.actor_id, 30, 86400)
        token = secrets.token_urlsafe(32)
        row = ContactEntrustment(id='ce_' + uuid4().hex, subject_id=subject_id, author_actor_id=actor.actor_id,
            idempotency_key=body.idempotency_key, request_hash=signature, recipient_label=body.recipient_label,
            channel=body.channel, contact_cipher=v.encrypt(contact), contact_hash=v.digest('contact', contact),
            contact_mask=mask_contact(body.channel, contact), invite_cipher=v.encrypt(token), invite_hash=v.digest('invite', token),
            title=body.title, message=body.message, sources=sources_value(body), source_version=current['source_version'],
            expires_at=utcnow() + timedelta(days=body.days))
        session.add(row); session.flush()
    result = plan_view(row, session) | {'claim_url':origin + '/receive/#' + v.decrypt(row.invite_cipher)}
    session.commit(); return result


@router.post('/{id}/link')
def link(subject_id:str, id:str, request:Request, actor=Depends(current_actor), session=Depends(get_session)):
    row = owner_plan(session, subject_id, actor.actor_id, id); active_snapshot(session, row)
    return {'claim_url':public_origin(request.app.state.settings) + '/receive/#' + vault(request).decrypt(row.invite_cipher)}


@router.post('/{id}/notify')
def notify(subject_id:str, id:str, request:Request, actor=Depends(current_actor), session=Depends(get_session)):
    publication_lock(session, subject_id)
    row = owner_plan(session, subject_id, actor.actor_id, id); active_snapshot(session, row)
    v = vault(request)
    if not delivery(request).available(row.channel, notice=True): raise DeliveryUnavailable('该渠道尚未配置通知，请复制领取链接给对方。')
    rate(session, v, 'notice:' + id, 1, 60)
    rate(session, v, 'notice-daily:' + row.contact_hash, 5, 86400)
    attempt = uuid4().hex; channel = row.channel; contact = v.decrypt(row.contact_cipher)
    claim_url = public_origin(request.app.state.settings) + '/receive/#' + v.decrypt(row.invite_cipher)
    row.notice_status = 'sending'; row.notice_attempt = attempt; row.notice_at = utcnow(); session.commit()
    failed = False
    try: delivery(request).send(channel, contact, link=claim_url)
    except DeliveryUnavailable: failed = True
    publication_lock(session, subject_id); row = owner_plan(session, subject_id, actor.actor_id, id)
    if row.notice_attempt == attempt and row.status == 'active': row.notice_status = 'unconfirmed' if failed else 'accepted'
    result = plan_view(row, session); session.commit()
    if failed: raise DeliveryUnavailable('通知发送结果未确认，可稍后重试或复制领取链接。')
    return result


@router.post('/{id}/revoke')
def revoke(subject_id:str, id:str, body:Revision, actor=Depends(current_actor), session=Depends(get_session)):
    publication_lock(session, subject_id); row = owner_plan(session, subject_id, actor.actor_id, id)
    if row.status != 'revoked':
        if row.revision != body.revision: raise SharingChanged('托付状态已变化，请刷新。')
        row.status = 'revoked'; row.revision += 1
        session.execute(delete(ReceiptSession).where(ReceiptSession.plan_id == id))
        session.execute(delete(ReceiptChallenge).where(ReceiptChallenge.plan_id == id))
    result = plan_view(row, session); session.commit(); return result


@receipts.post('/challenges')
def challenge(body:ChallengeInput, request:Request, session=Depends(get_session)):
    v = public_lock(request, session, 'challenge')
    row = invited(session, v, body.invite_token)
    rate(session, v, 'contact-attempt:' + row.id, 10, 600)
    try: contact = normalize_contact(row.channel, body.contact)
    except RequestInvalid:
        session.commit(); raise Hidden('链接或验证信息无效。') from None
    if not hmac.compare_digest(v.digest('contact', contact), row.contact_hash):
        session.commit(); raise Hidden('链接或验证信息无效。')
    if not delivery(request).available(row.channel): raise DeliveryUnavailable('验证码服务暂不可用。')
    rate(session, v, 'code-minute:' + row.contact_hash, 1, 60)
    rate(session, v, 'code-hour:' + row.contact_hash, 5, 3600)
    rate(session, v, 'code-day:' + row.contact_hash, 10, 86400)
    session.execute(delete(ReceiptChallenge).where(ReceiptChallenge.plan_id == row.id))
    code = f'{secrets.randbelow(1000000):06d}'; id = 'rc_' + uuid4().hex
    item = ReceiptChallenge(id=id, plan_id=row.id, code_hash=v.digest('otp:' + id, code), expires_at=utcnow() + timedelta(minutes=5))
    session.add(item); channel = row.channel; plan_id = row.id; subject = row.subject_id; mask = row.contact_mask
    session.commit()
    failed = False
    try: delivery(request).send(channel, contact, code=code)
    except DeliveryUnavailable: failed = True
    publication_lock(session, subject)
    row = session.get(ContactEntrustment, plan_id); item = session.get(ReceiptChallenge, id)
    if item is None or row is None: raise Hidden('这份托付已变化，请重新领取。')
    active_snapshot(session, row)
    item.status = 'failed' if failed else 'sent'; expiry = as_utc(item.expires_at).isoformat(); session.commit()
    if failed: raise DeliveryUnavailable('验证码发送结果未确认，请稍后重试。')
    return {'challenge_id':id, 'expires_at':expiry, 'contact_mask':mask, 'retry_after_seconds':60}


@receipts.post('/verify')
def verify(body:Verify, request:Request, session=Depends(get_session)):
    v = public_lock(request, session, 'verify'); row = invited(session, v, body.invite_token)
    rate(session, v, 'verify-plan:' + row.id, 20, 900)
    item = session.get(ReceiptChallenge, body.challenge_id)
    if item is None or item.plan_id != row.id or item.status != 'sent' or item.attempts >= 5 or as_utc(item.expires_at) <= utcnow():
        session.commit(); raise Hidden('验证码无效或已过期。')
    item.attempts += 1
    if not hmac.compare_digest(item.code_hash, v.digest('otp:' + item.id, body.code)):
        session.commit(); raise Hidden('验证码无效或已过期。')
    item.status = 'used'
    token = secrets.token_urlsafe(32); expiry = min(utcnow() + timedelta(minutes=30), as_utc(row.expires_at))
    session.add(ReceiptSession(token_hash=v.digest('session', token), plan_id=row.id, revision=row.revision, expires_at=expiry))
    if row.claimed_at is None: row.claimed_at = utcnow()
    session.commit(); return {'session_token':token, 'expires_at':expiry.isoformat()}


def receipt(request, session):
    v = vault(request)
    token = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if not token or len(token) > 100: raise Hidden('领取会话已失效，请重新验证。')
    # Same boundary as revocation/source updates; every publication revalidates access.
    publication_lock(session, '')
    access = session.get(ReceiptSession, v.digest('session', token))
    if access is None or as_utc(access.expires_at) <= utcnow(): raise Hidden('领取会话已失效，请重新验证。')
    row = session.get(ContactEntrustment, access.plan_id)
    if row is None or row.revision != access.revision: raise Hidden('这份托付已失效。')
    snapshot = active_snapshot(session, row)
    return row, snapshot, access


@receipts.get('/content')
def content(request:Request, session=Depends(get_session)):
    row, snapshot, access = receipt(request, session)
    if row.opened_at is None: row.opened_at = utcnow()
    result = {'title':row.title, 'recipient_label':row.recipient_label, 'message':row.message,
              'items':snapshot['items'], 'expires_at':as_utc(access.expires_at).isoformat()}
    session.commit(); return result


@receipts.get('/audio/{kind}/{id}')
def audio(kind:Literal['episode','dedicated'], id:str, request:Request, session=Depends(get_session)):
    row, _, _ = receipt(request, session)
    if {'kind':kind, 'id':id} not in row.sources: raise Hidden('音频不在这份托付内。')
    if kind == 'episode':
        source = session.get(Episode, id); key = source.audio_object_key; mime = source.audio_content_type
    else:
        source = session.get(CompanionAudio, id); key = source.object_key; mime = source.content_type
    session.commit()
    # Remote storage must not hold the publication lock and block owner/Agent work.
    try: data = request.app.state.object_store.get(key)
    except Exception: raise AudioUnavailable('这段原音暂时无法取回，请稍后重试。') from None
    receipt(request, session)  # A revoke/expiry/source change during download wins.
    session.commit()
    return Response(data, media_type=mime, headers={'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'})


@receipts.delete('/session')
def end(request:Request, session=Depends(get_session)):
    v = vault(request); token = request.headers.get('Authorization', '').removeprefix('Bearer ')
    session.execute(delete(ReceiptSession).where(ReceiptSession.token_hash == v.digest('session', token)))
    session.commit(); return {'ended':True}
