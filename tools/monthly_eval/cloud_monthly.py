"""Chronological expansion of a verified cloud smoke run through product APIs.

Actual immutable audio only. Explicit owner-selected revision targets are held
in the ignored run directory; no old-run memory IDs or author answers are used.
Technical ASR confirmation is authorized for this fictional corpus, not listening.
"""
import argparse
import json
import time

from cloud_asr_samples import load_sample, wait_for_review
from cloud_followthrough import Steps
from nightly_rules import check_correction
from product_loop import call
from speech_pipeline import CORPUS, OUT, save

REQUESTS = {'bus_driver': '为什么总说平安回家比多跑一趟重要？',
            'firefighter': '为什么休息时把手机调成静音？',
            'life_review': '为什么一直留着那本边角磨坏的工作本？'}


def run_month(run):
    smoke = json.loads((run / 'state.json').read_text(encoding='utf-8'))
    if smoke.get('phase') != 'complete':
        raise RuntimeError('Complete the three actual smoke loops before expanding.')
    pairs = json.loads((run / 'identities.json').read_text(encoding='utf-8'))
    targets = json.loads((run / 'revision-targets.json').read_text(encoding='utf-8'))
    manifest = json.loads((CORPUS / 'manifest.json').read_text(encoding='utf-8'))
    mapping_path = run / 'product-episodes.json'
    mapping = json.loads(mapping_path.read_text(encoding='utf-8'))
    path = run / 'monthly-state.json'
    state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'phase': 'running', 'policy': smoke['policy'], 'episodes': {}, 'errors': [], 'human_listening': False}
    steps = Steps(run / 'monthly-steps.json')
    def persist():
        save(mapping_path, mapping)
        save(path, state)
    for person in manifest['people']:
        pid = person['id']; pair = pairs[pid]; owner = pair['owner']
        root = '/api/v1/workbench/subjects/' + owner['subject_id']
        if call('GET', '/api/v1/workbench/capabilities', owner).get('cloud_asr_policy') != state['policy']:
            raise RuntimeError('Relay policy changed; no grants or uploads made for this person.')
        def mutate(label, method, endpoint, identity=owner, **kwargs):
            return steps.once(pid + '/' + label, lambda: call(method, endpoint, identity, **kwargs))
        # Smoke checks revoked story01. Re-share explicitly to exercise how a
        # private correction withdraws the now-obsolete shared story later.
        mutate('share01-for-correction', 'POST', root + '/grants', json={
            'episode_id': mapping[pid + '-01']['episode_id'], 'reader_actor_id': pair['reader']['actor_id'],
            'include_audio_confirmed': True, 'cloud_processing_allowed': True})
        for spec in person['episodes'][1:]:
            name = spec['id']; number = int(name[-2:])
            row = state['episodes'].setdefault(name, {})
            if row.get('complete'): continue
            try:
                caps = call('GET', '/api/v1/workbench/capabilities', owner)
                if caps.get('cloud_asr_policy') != state['policy']:
                    raise RuntimeError('Relay policy changed; no new upload.')
                date, audio, raw, checksum = load_sample({**person, 'episodes': [spec]})
                if name not in mapping:
                    generation = state.get('upload_generation', '')
                    uploaded = mutate('upload/' + name + generation, 'POST', '/api/v1/episodes', data={
                        'subject_id': owner['subject_id'], 'recording_consent_id': owner['consent_id'],
                        'source': 'IMPORT', 'audio_ref': audio.name, 'recorded_at': date,
                        'idempotency_key': run.name + '-' + name + generation,
                        'metadata': json.dumps({'evaluation_id': name, 'fictional': True,
                            'cloud_asr_policy': state['policy'], 'technical_quality_pending': True})},
                        files={'file': (audio.name, raw, 'audio/wav')})
                    mapping[name] = {'episode_id': uploaded['episode_id'], 'person': pid, 'audio_sha256': checksum,
                                     'asr_model': caps['stt'] + '/' + caps['stt_model']}
                    persist()
                eid = mapping[name]['episode_id']; row['episode_id'] = eid
                kind = 'correction' if number == 4 else 'supplement' if number == 6 else None
                if kind:
                    revision = mutate('associate/' + name, 'POST', root + '/revisions', json={
                        'episode_id': eid, 'target_memory_id': targets[pid][kind], 'kind': kind})
                    row['revision_id'] = revision['revision_id']; persist()
                if number == 9:
                    request = mutate('question/' + name, 'POST', root + '/requests', pair['reader'],
                                     json={'text': REQUESTS[pid]})
                    row['request_id'] = request['request_id']; persist()
                wait_for_review(owner, eid, run / (name + '.product-asr.json'), row, persist)
                stories = call('GET', root + '/stories', owner)['items']
                story = next(s for s in stories if s['episode_id'] == eid)
                if not story['memories']:
                    row['quality_issue'] = 'Model returned a valid empty extraction; confirmed original remains available. Not proof of successful deduplication.'
                    if kind: raise RuntimeError('Revision has no saved memories; cannot confirm.')
                if kind and not row.get('revision_confirmed'):
                    if kind == 'correction':
                        old = next(m for s in stories for m in s['memories'] if m['memory_item_id'] == targets[pid][kind])
                        row['correction_gate'] = check_correction(pid, old, story)
                        persist()
                    mutate('confirm/' + name, 'POST', root + '/revisions/' + row['revision_id'] + '/confirm')
                    row['revision_confirmed'] = True
                row['evidence_exact'] = all(e['excerpt'] in story['transcript'] for m in story['memories'] for e in m['evidence'])
                if not row['evidence_exact']: raise RuntimeError('Saved evidence absent from confirmed ASR text.')
                if number in (2,3,5,6,8,9):
                    grant = mutate('share/' + name, 'POST', root + '/grants', json={
                        'episode_id': eid, 'reader_actor_id': pair['reader']['actor_id'],
                        'include_audio_confirmed': True, 'cloud_processing_allowed': True})
                    row['grant_id'] = grant['grant_id']
                if number == 5:
                    row['temporal_update'] = 'Past and present locations remain in narrative; no invented prior target.'
                if number == 10:
                    request_id = state['episodes'][pid + '-09']['request_id']
                    mutate('answer/' + name, 'PATCH', root + '/requests/' + request_id,
                           json={'status': 'answered', 'answer_episode_id': eid})
                    visible = call('GET', root + '/requests', pair['reader'])['items']
                    if next(r for r in visible if r['request_id'] == request_id)['answer_episode_id'] is not None:
                        raise RuntimeError('Private response leaked to reader.')
                row.update(complete=True, memory_count=len(story['memories']))
                row.pop('blocked', None); persist()
                print(name, 'saved with actual cloud ASR and text model', flush=True)
            except Exception as error:
                row['blocked'] = type(error).__name__
                state['errors'].append({'episode': name, 'at': time.time(), 'type': type(error).__name__,
                    'message': str(error) if isinstance(error, (RuntimeError, ValueError)) else 'Inspect stage logs.'})
                persist(); print(name, 'blocked; preserved; continuing independent person', flush=True)
                break
    state['phase'] = ('complete' if all(state['episodes'].get(e['id'], {}).get('complete')
        for p in manifest['people'] for e in p['episodes'][1:]) else 'partial')
    persist()
    if state['phase'] != 'complete': raise SystemExit('Partial monthly run; inspect retained failures, no automatic extra retries.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not args.run.replace('-', '').isalnum(): raise SystemExit('Invalid run name')
    run_month(OUT / 'cloud-asr-runs' / args.run)
