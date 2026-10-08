"""Three real cloud-ASR stories through existing authenticated product APIs.

Reads existing immutable synthetic audio only, never scripts/gold. New subjects,
Episodes and a separate checkpoint preserve the old Whisper comparison corpus.
Technical confirmation was explicitly authorized for this fictional evaluation;
it is NOT human listening or content-quality acceptance. No automatic retries.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import product_loop as product
from nightly_rules import choose_audio
from speech_pipeline import OUT, CORPUS, REPO, save


def load_sample(person):
    spec = person['episodes'][0]
    name = spec['id']
    folder = OUT / person['id']
    metadata = json.loads((folder / (name + '.json')).read_text(encoding='utf-8'))
    audio = choose_audio(folder, name, metadata)
    raw = audio.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    if checksum != metadata['audio_sha256']:
        raise RuntimeError('immutable audio hash mismatch')
    return spec['simulated_recorded_at'], audio, raw, checksum


def wait_for_review(owner, episode, output, row, persist, *, seconds=900):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        status = product.call('GET', f'/api/v1/episodes/{episode}', owner)
        if status['status'] == 'failed':
            raise RuntimeError('product stage failed: ' + status.get('error_code', 'unknown'))
        if status['status'] == 'ready':
            return
        review = product.call('GET', f'/api/v1/episodes/{episode}/transcript-review', owner)
        if review['state'] == 'reviewing':
            save(output, review)
            # Store exactly the API's ASR-derived review draft. No author repair.
            row['confirmation'] = 'user-authorized imperfect synthetic ASR technical confirmation'
            row['human_listening'] = False
            persist()
            product.call('PATCH', f'/api/v1/episodes/{episode}/transcript-review', owner,
                         json={'transcript': review['transcript']})
        time.sleep(2)
    raise RuntimeError('bounded product-stage wait expired; resume existing Episode')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True, help='new evaluation name or existing checkpoint')
    parser.add_argument('--execute', action='store_true', help='run user-authorized real fictional audio')
    args = parser.parse_args()
    if not args.run.replace('-', '').isalnum():
        raise SystemExit('Use an alphanumeric run name')
    sys.path.insert(0, str(REPO / 'services/backend'))
    from app.config import Settings
    from app.relay_asr import configured, cloud_policy
    backend = REPO / 'services/backend'
    settings = Settings(_env_file=backend / '.env')
    if settings.stt_backend != 'relay' or not configured(settings):
        raise SystemExit('Cloud ASR not configured; no audio sent, no local fallback, no identities created.')
    if not args.execute:
        print('Configuration present; live availability unverified. Use --execute for real fictional audio.')
        return
    run = OUT / 'cloud-asr-runs' / args.run
    run.mkdir(parents=True, exist_ok=True)
    state_path = run / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {
        'policy': cloud_policy(settings), 'phase': 'running', 'episodes': {}, 'errors': [], 'human_listening': False}
    if state['policy'] != cloud_policy(settings):
        raise SystemExit('Relay route changed; use a new run instead of replacing old ASR provenance.')
    if state['phase'] == 'complete':
        print('This checkpoint is complete; no model requests repeated.')
        return
    product.AUTH = run / 'identities.json'
    # Seed's local config resolution requires the backend cwd. No business-state
    # direct writes: capture/review/extract/QA/profile are all actual HTTP APIs.
    os.chdir(backend)
    manifest = json.loads((CORPUS / 'manifest.json').read_text(encoding='utf-8'))
    pairs = product.identities(manifest)
    def persist(): save(state_path, state)
    for person in manifest['people']:
        pid = person['id']; name = pid + '-01'; owner = pairs[pid]['owner']
        row = state['episodes'].setdefault(name, {'person': pid})
        if row.get('complete'): continue
        try:
            caps = product.call('GET', '/api/v1/workbench/capabilities', owner)
            if caps.get('cloud_asr_policy') != state['policy'] or not caps.get('stt_configured'):
                raise RuntimeError('Running service is not using this cloud ASR policy; restart it before upload.')
            recorded_at, audio, raw, checksum = load_sample(person)
            row.update(audio_sha256=checksum, audio_path=str(audio))
            if not row.get('episode_id'):
                created = product.call('POST', '/api/v1/episodes', owner, data={
                    'subject_id': owner['subject_id'], 'recording_consent_id': owner['consent_id'],
                    'source': 'IMPORT', 'recorded_at': recorded_at,
                    'idempotency_key': args.run + '-' + name, 'audio_ref': audio.name,
                    'metadata': json.dumps({'capture_client': 'cloud-asr-synthetic-evaluation',
                        'cloud_asr_policy': state['policy'], 'fictional': True})},
                    files={'file': (audio.name, raw, 'audio/wav')})
                row['episode_id'] = created['episode_id']; persist()
            wait_for_review(owner, row['episode_id'], run / (name + '.product-asr.json'), row, persist)
            row['complete'] = True; persist()
            print(name, 'real ASR + reviewed extraction saved; quality review pending', flush=True)
        except Exception as error:
            state['errors'].append({'episode': name, 'at': time.time(), 'error_type': type(error).__name__,
                'message': str(error) if isinstance(error, RuntimeError) else 'Check product/call logs; no retry issued'})
            persist()
            print(name, 'blocked; original and checkpoint retained', flush=True)
    if not all(state['episodes'].get(p['id'] + '-01', {}).get('complete') for p in manifest['people']):
        raise SystemExit('Incomplete real cloud-ASR samples; see checkpoint errors. No QA success claimed.')
    product.MAPPING = run / 'product-episodes.json'
    save(product.MAPPING, state['episodes'])
    from cloud_followthrough import followthrough
    followthrough(run, pairs, state['episodes'])
    state['phase'] = 'complete'; state['quality_review'] = 'pending'; persist()


if __name__ == '__main__':
    main()
