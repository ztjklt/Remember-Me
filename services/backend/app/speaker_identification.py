"""Diarized acoustic speaker IDs + spoken introductions, scoped to one recording.

Names are self-described labels, never account identities or access grants. No
voice vector/profile is persisted or shared between recordings in this slice.
"""
import hashlib
import re
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update, or_
from .models import ConsentScope, utcnow, as_utc
from .speaker_models import SpeakerRecording
from .repositories.consents import ConsentRepository
from .errors import AppError, RequestInvalid, SttFailed, SttTimeout, SttUnavailable
from .chinese_text import simplified_transcript

VERSION = 'natural-voiceprints-v3'
INTRO_WINDOW_MS = 120_000
_NAME = re.compile(r'^(?:(?:大家好|你好|你们好|嗯|哦|对|其实|那个|我呢)[，,。！!、\s]*)*(?:我叫|我的名字(?:是|叫)|我是|叫我|你们(?:可以)?叫我)\s*([\u4e00-\u9fffA-Za-z0-9·]{1,20})(?=[，,。.!！?？;；\s]|就|吧|啊|呀|呢|$)')
_ROLE_WORDS = ('朋友', '老师', '学生', '爸爸', '妈妈', '同意', '觉得', '来自', '这个', '那个', '你的', '他的', '她的', '的')
_CORRECTION = re.compile(r'(?:名字(?:听|写|说|识别)错|不是[^，。！？]{1,12}[，,。]|更正(?:一下)?|纠正(?:一下)?|我(?:是|叫)的?不是)')


def policy(settings):
    from .paraformer_asr import cloud_policy
    return 'speaker-v1:' + hashlib.sha256((cloud_policy(settings) + VERSION).encode()).hexdigest()[:32]


def available(settings):
    from .paraformer_asr import configured
    return settings.stt_backend == 'paraformer' and configured(settings)


def _spoken_name(text):
    # Natural first-person introductions, never a quoted mention of somebody else.
    if re.search(r'(?:他说|她说|别人说|他叫|她叫|他介绍|她介绍|[“\"])', text): return None
    for clause in re.split(r'[，,。！!？?；;]', text.strip()):
        match = _NAME.match(clause.strip())
        if not match: continue
        name = match.group(1)
        name = re.sub(r'(?:就行|就好|好了|吧|啊|呀|呢)$', '', name)
        if name and len(name) <= 8 and not any(word in name for word in _ROLE_WORDS): return name
    return None


def build_report(transcript, *, duration_ms):
    raw = transcript.metadata.get('speaker_sentences')
    if not isinstance(raw, list) or not raw or len(raw) > 3000:
        return _text_only_report(transcript, duration_ms)
    segments = []; voice_ids = {}
    for index, sentence in enumerate(raw):
        if not isinstance(sentence, dict): return _text_only_report(transcript, duration_ms)
        start, end, text = sentence.get('begin_time'), sentence.get('end_time'), sentence.get('text')
        if (type(start) is not int or type(end) is not int or not 0 <= start < end <= duration_ms + 1000
                or not isinstance(text, str) or not text.strip() or len(text) > 30000):
            return _text_only_report(transcript, duration_ms)
        voice = sentence.get('speaker_id')
        speaker = None
        if type(voice) is int and 0 <= voice <= 100:
            speaker = voice_ids.setdefault(voice, 'speaker_' + str(len(voice_ids)))
        segments.append({'segment_id': 'segment_' + str(index), 'start_ms': start, 'end_ms': end,
            'text': simplified_transcript(text), 'speaker_id': speaker, 'speaker_name': None,
            'attribution': 'unidentified', 'overlap': False})
    # Detect overlapping returned intervals. Absence of overlap here is not an
    # acoustic guarantee; the upstream adapter's diarization limitations remain.
    for index, item in enumerate(segments):
        for earlier in segments[:index]:
            if max(item['start_ms'], earlier['start_ms']) < min(item['end_ms'], earlier['end_ms']):
                item['overlap'] = earlier['overlap'] = True
    introductions, corrections = {}, {}
    for item in segments:
        voice = item['speaker_id']
        if voice is None or item['overlap'] : continue
        if name := _spoken_name(item['text']):
            introductions.setdefault(voice, []).append((name, item['segment_id']))
            if _CORRECTION.search(item['text']): corrections[voice] = name
    speakers = []
    for voice in dict.fromkeys(s['speaker_id'] for s in segments if s['speaker_id'] is not None):
        named = introductions.get(voice, [])
        names = {name for name, _ in named}
        if voice in corrections: names = {corrections[voice]}
        identity = ('conflicting_introduction' if len(names) > 1 else
                    'spoken_introduction' if len(names) == 1 else 'unidentified')
        name = next(iter(names)) if identity == 'spoken_introduction' else None
        speakers.append({'speaker_id': voice, 'name': name, 'identity_method': identity,
            'introduction_segment_ids': [segment for _, segment in named], 'consent_segment_ids': []})
        for segment in segments:
            if segment['speaker_id'] == voice:
                segment['speaker_name'] = name if not segment['overlap'] else None
                segment['attribution'] = 'overlap' if segment['overlap'] else identity
    for item in segments:
        if item['overlap']: item['attribution'] = 'overlap'; item['speaker_name'] = None
    return {'identification_scope': 'recording', 'protocol_version': VERSION,
        'model_version': transcript.model_version, 'speakers': speakers, 'segments': segments, 'identification_status':'grouped'}


def _text_only_report(transcript, duration_ms):
    text = simplified_transcript(transcript.text).strip()
    if not text: raise SttFailed('本段没有识别到文字，原音仍保留。')
    return {'identification_scope':'recording', 'protocol_version':VERSION, 'model_version':transcript.model_version,
        'identification_status':'text_only', 'speakers':[], 'segments':[{'segment_id':'segment_0', 'start_ms':0,
        'end_ms':duration_ms, 'text':text, 'speaker_id':None, 'speaker_name':None, 'attribution':'unidentified',
        'overlap':False, 'timing_estimated':True}]}


def require_active(session, row):
    return ConsentRepository(session).require_active(row.consent_id, subject_id=row.subject_id,
        scope=ConsentScope.SPEAKER_IDENTIFICATION, actor_id=row.actor_id)


def discard(session, store, row, status='deleted'):
    # The tombstone and access block are committed before attempting storage
    # cleanup. A remote deletion failure can be retried; access never reopens.
    row.status = 'deleted' if row.status == 'deleted' else status
    row.report = None; row.lease_token = None; row.lease_expires_at = None
    session.commit()
    from .voiceprints import invalidate_source
    invalidate_source(session,'speaker_recording',row.recording_id,store)
    if row.audio_key:
        try: store.delete(row.audio_key)
        except Exception:
            row.error = '原音清理尚未完成，访问已关闭。'; session.commit(); return
        row.audio_key = ''; row.error = None; session.commit()


def run_one(database, store, settings, recording_id=None, provider=None):
    if not available(settings): return False
    now = utcnow(); token = uuid4().hex
    with database.session() as session:
        candidates = select(SpeakerRecording).where(
            or_(SpeakerRecording.status == 'uploaded',
                (SpeakerRecording.status == 'analyzing') & (SpeakerRecording.lease_expires_at < now)))
        if recording_id: candidates = candidates.where(SpeakerRecording.recording_id == recording_id)
        row = session.scalar(candidates.order_by(SpeakerRecording.created_at).limit(1))
        if row is None: return False
        try: require_active(session, row)
        except AppError: discard(session, store, row, 'revoked'); return True
        claimed = session.execute(update(SpeakerRecording).where(
            SpeakerRecording.recording_id == row.recording_id,
            or_(SpeakerRecording.status == 'uploaded',
                (SpeakerRecording.status == 'analyzing') & (SpeakerRecording.lease_expires_at < now)))
            .values(status='analyzing', lease_token=token, lease_expires_at=now + timedelta(seconds=600),
                    attempts=SpeakerRecording.attempts + 1))
        session.commit()
        if not claimed.rowcount: return False
        session.refresh(row)
        rid, key, kind, expected_policy, duration, checksum, count = row.recording_id, row.audio_key, row.content_type, row.policy, row.duration_ms, row.checksum, row.speaker_count
    def authorize():
        with database.session() as session:
            current = session.get(SpeakerRecording, rid)
            if current is None or current.status != 'analyzing' or current.lease_token != token:
                raise RequestInvalid('该段录音已取消、删除或由其他任务接手。')
            require_active(session, current)
            if policy(settings) != expected_policy: raise RequestInvalid('识别用途已变化，请重新确认用途。')
    result, failure, retry = None, None, False
    try:
        authorize(); audio = store.get(key)
        if hashlib.sha256(audio).hexdigest() != checksum: raise SttFailed('原音校验不一致。')
        if provider is None:
            from .paraformer_asr import ParaformerSttProvider
            cfg = settings.model_copy(update={'paraformer_poll_timeout_seconds': min(15, settings.paraformer_poll_timeout_seconds)})
            provider = ParaformerSttProvider(cfg, checkpoint_store=store if cfg.paraformer_checkpoint_backend == 'object_store' else None)
        transcript = provider.transcribe_authorized(audio, kind, authorize, diarization=True, **({'speaker_count':count} if count else {}))
        authorize(); result = build_report(transcript, duration_ms=duration)
    except AppError as exc:
        retry = isinstance(exc, (SttTimeout, SttUnavailable)); failure = exc.message
    except Exception:
        failure = '说话人识别未完成，原音保留，可稍后重试。'; retry = True
    with database.session() as session:
        current = session.get(SpeakerRecording, rid)
        if current is None or current.lease_token != token or current.status != 'analyzing': return True
        try: require_active(session, current)
        except AppError: discard(session, store, current, 'revoked'); return True
        if policy(settings) != expected_policy: result = None; failure = '识别用途已变化，请重新确认用途。'; retry = False
        if result:
            from .voiceprints import available as vp_available, encoder, pcm, annotate
            if vp_available(settings):
                try:
                    result=annotate(session,current.subject_id,pcm(audio,kind),result,encoder(settings.voiceprint_model_path),consent_id=current.consent_id,actor=current.actor_id,source={'kind':'speaker_recording','id':rid},learn_names=True)
                except AppError: result['voiceprint_status']='unavailable'
        current.report = result; current.error = failure
        current.status = 'ready' if result else 'uploaded' if retry and current.attempts < 10 else 'failed'
        current.lease_token = None; current.lease_expires_at = None
        session.commit()
    return True
