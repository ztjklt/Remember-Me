"""A call is usable only while its original identity, consents and policy hold."""
import hashlib
import json
from sqlalchemy import select
from .models import Actor, DeviceCredential, ConsentScope, as_utc, utcnow
from .realtime_models import RealtimeVoiceProfile, VoiceCall
from .repositories.consents import ConsentRepository
from .api.twin import require_subject, TwinNotFound
from .realtime_provider import RealtimeUnavailable


def policy(settings):
    notice = {'version': 'realtime-voice-v1', 'livekit': settings.livekit_url,
              'inference': settings.realtime_inference_url,
              'voice_model': settings.cosyvoice_model, 'asr_model': settings.realtime_asr_model}
    return 'rv1-' + hashlib.sha256(json.dumps(notice, sort_keys=True).encode()).hexdigest()[:24]


def configured(settings, provider):
    from urllib.parse import urlsplit
    transport = urlsplit(settings.livekit_url)
    api = urlsplit(settings.livekit_api_url)
    public = urlsplit(settings.realtime_public_url)
    return bool(settings.realtime_enabled and provider.configured() and
                transport.scheme == 'wss' and transport.hostname and
                (api.scheme == 'https' or api.scheme == 'http' and api.hostname in {'127.0.0.1','localhost'}) and
                public.scheme == 'https' and public.hostname and
                settings.livekit_api_key.get_secret_value() and settings.livekit_api_secret.get_secret_value() and
                len(settings.realtime_worker_secret.get_secret_value()) >= 32)


def profile_for(session, subject_id, actor_id):
    return session.scalar(select(RealtimeVoiceProfile).where(
        RealtimeVoiceProfile.subject_id == subject_id, RealtimeVoiceProfile.actor_id == actor_id,
        RealtimeVoiceProfile.revoked_at.is_(None)).order_by(RealtimeVoiceProfile.created_at.desc()))


def check_call(session, call_id, settings, provider):
    row = session.get(VoiceCall, call_id)
    if row is None or row.ended_at or as_utc(row.expires_at) <= utcnow():
        raise TwinNotFound('语音通话已结束或过期。')
    if not configured(settings, provider) or row.policy != policy(settings):
        raise RealtimeUnavailable('语音服务用途已变化，请结束后重新确认。')
    actor = session.get(Actor, row.actor_id)
    if actor is None: raise TwinNotFound('语音通话不可用。')
    device=session.get(DeviceCredential,row.credential_digest)
    if actor.token_hash != row.credential_digest and not (device and device.actor_id==row.actor_id and
        (device.expires_at is None or as_utc(device.expires_at)>utcnow())):
        raise TwinNotFound('登录已过期或退出，通话已结束。')
    require_subject(session, row.subject_id, actor)
    repository = ConsentRepository(session)
    for scope, identifier in [(ConsentScope.CLOUD_TWIN, row.cloud_consent_id), (ConsentScope.VOICE, row.voice_consent_id)]:
        repository.require_active(identifier, subject_id=row.subject_id, scope=scope, actor_id=row.actor_id)
    profile = session.get(RealtimeVoiceProfile, row.profile_id)
    if profile is None or profile.revoked_at or profile.status != 'ready' or profile.model != settings.cosyvoice_model:
        raise TwinNotFound('个人声音尚未就绪或已撤销。')
    return row, profile, actor
