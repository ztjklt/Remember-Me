"""Operator desktop ASR + reviewed capture relay; never ship shared keys to an App.

Run with the backend Python environment. ASR and upload are separate commands.
No author script, old ASR or gold answer is consumed. Upload does not confirm text.
"""
import argparse
import hashlib
import json
import mimetypes
import os
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'services/backend'


def save_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write('\n')


def server_url(value):
    parts = urlsplit(value)
    if (not parts.hostname or parts.username or parts.password or parts.query or parts.fragment
            or parts.path not in ('', '/') or parts.scheme not in ('http', 'https')
            or (parts.scheme == 'http' and parts.hostname not in ('localhost', '127.0.0.1', '::1'))):
        raise ValueError('Use a verified HTTPS origin; HTTP is allowed only on loopback')
    return value.rstrip('/')


def transcribe_recording(audio, output, provider, *, audio_export_confirmed):
    audio, output = Path(audio).resolve(), Path(output)
    if audio_export_confirmed is not True:
        raise ValueError('Explicit consent to send this audio to Groq is required')
    raw = audio.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    if output.exists():
        previous = json.loads(output.read_text(encoding='utf-8'))
        if previous['client_transcript']['audio_sha256'] != checksum:
            raise ValueError('Checkpoint belongs to different audio')
        return previous
    attempt = output.with_suffix(output.suffix + '.attempt.json')
    if attempt.exists():
        raise ValueError('An earlier ASR attempt has no saved draft; inspect it before an explicit new attempt')
    save_new(attempt, {'started_at': datetime.now(timezone.utc).isoformat(), 'audio_sha256':checksum,
                      'endpoint':'https://api.groq.com/openai/v1/audio/transcriptions',
                      'request_model':'whisper-large-v3'})
    result = provider.transcribe(raw, mimetypes.guess_type(audio.name)[0] or 'audio/wav')
    value = {'audio_path':str(audio), 'recorded_at':datetime.now(timezone.utc).isoformat(),
        'recorded_at_basis':'desktop import time; not claimed original recording date',
        'human_listening':False, 'reviewed':False,
        'client_transcript':{'text':result.text, 'audio_sha256':checksum, 'provider':'groq',
                             'model':'whisper-large-v3','audio_export_confirmed':True},
        'provider_call':result.metadata}
    save_new(output, value)
    return value


def upload_recording(client, draft, identity, *, subject_id, consent_id, idempotency_key, receipt):
    audio = Path(draft['audio_path'])
    raw = audio.read_bytes()
    if hashlib.sha256(raw).hexdigest() != draft['client_transcript']['audio_sha256']:
        raise ValueError('Audio changed after ASR; refusing to upload')
    binding = {'origin':str(client.base_url).rstrip('/'), 'subject_id':subject_id,
               'consent_id':consent_id, 'idempotency_key':idempotency_key,
               'draft_sha256':hashlib.sha256(json.dumps(draft['client_transcript'],
                    sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()}
    previous = json.loads(Path(receipt).read_text(encoding='utf-8')) if Path(receipt).exists() else None
    if previous is not None and previous.get('binding') != binding:
        raise ValueError('Receipt belongs to a different server, space or draft')
    # Always send the same idempotency key on a deliberate retry. The server
    # compares both original audio and machine transcript before accepting it.
    response = client.post('/api/v1/episodes/client-transcribed',
        headers={'Authorization':'Bearer '+identity['actor_token']},
        data={'subject_id':subject_id, 'recording_consent_id':consent_id,
              'source':'IMPORT', 'recorded_at':draft.get('recorded_at',datetime.now(timezone.utc).isoformat()),
              'audio_ref':audio.name, 'idempotency_key':idempotency_key,
              'client_transcript':json.dumps(draft['client_transcript'],ensure_ascii=False),
              'metadata':json.dumps({'capture_client':'desktop-client-asr-v1',
                                    'recorded_at_basis':draft.get('recorded_at_basis','client supplied')})},
        files={'file':(audio.name,raw,mimetypes.guess_type(audio.name)[0] or 'audio/wav')})
    if response.status_code not in (200,201):
        raise RuntimeError('Capture rejected: HTTP '+str(response.status_code)+'; inspect service status, no ASR retry')
    result=response.json()
    if not result.get('episode_id'):
        raise RuntimeError('Capture response has no Episode ID')
    if previous is not None:
        if previous.get('result') != result:
            raise ValueError('Receipt already belongs to a different capture')
    else:
        save_new(receipt,{'binding':binding,'result':result})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='stage',required=True)
    asr=sub.add_parser('transcribe')
    asr.add_argument('--audio',type=Path,required=True)
    asr.add_argument('--out',type=Path,required=True)
    asr.add_argument('--confirm-audio-export',action='store_true',required=True)
    upload=sub.add_parser('upload')
    upload.add_argument('--draft',type=Path,required=True)
    upload.add_argument('--base-url',required=True)
    upload.add_argument('--ca',type=Path)
    upload.add_argument('--session-file',type=Path,required=True)
    upload.add_argument('--subject-id',required=True)
    upload.add_argument('--consent-id',required=True)
    upload.add_argument('--idempotency-key',required=True)
    upload.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.stage=='transcribe':
            sys.path.insert(0,str(BACKEND))
            from app.config import Settings
            from app.groq_asr import GroqSttProvider
            settings=Settings(_env_file=BACKEND/'.env',groq_asr_model='whisper-large-v3',
                groq_asr_state_dir=str(args.out.parent/'groq-calls'))
            transcribe_recording(args.audio,args.out,GroqSttProvider(settings),
                                 audio_export_confirmed=args.confirm_audio_export)
            print('ASR checkpoint saved; awaiting user review. No product data uploaded.')
        else:
            base=server_url(args.base_url)
            context=ssl.create_default_context(cafile=str(args.ca) if args.ca else None)
            draft=json.loads(args.draft.read_text(encoding='utf-8'))
            identity=json.loads(args.session_file.read_text(encoding='utf-8'))
            with httpx.Client(base_url=base,verify=context,trust_env=False,follow_redirects=False,timeout=90) as client:
                result=upload_recording(client,draft,identity,subject_id=args.subject_id,consent_id=args.consent_id,
                    idempotency_key=args.idempotency_key,receipt=args.receipt)
            print('Saved Episode '+result['episode_id']+'; confirm actual ASR in the workbench before extraction.')
    except Exception as error:
        # Exception strings from networking/dependencies may contain credentials.
        print('Client capture failed ('+type(error).__name__+'); retained local audio/checkpoint.',file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__':
    main()
