"""Profile and 60-question checks on completed cloud Episodes, never old ASR data.

Question expectations are evaluated separately. A 200 or a finished file is
not a semantic pass. Pending profile candidates are never auto-confirmed.
"""
import argparse
import json
import sys
from cloud_followthrough import Steps, wait_profile
from product_loop import call
from speech_pipeline import OUT, save
import qa_round


def verify(run):
    monthly = json.loads((run / 'monthly-state.json').read_text(encoding='utf-8'))
    if monthly['phase'] != 'complete':
        raise RuntimeError('Month is incomplete; do not substitute old Whisper results.')
    pairs = json.loads((run / 'identities.json').read_text(encoding='utf-8'))
    mapping = json.loads((run / 'product-episodes.json').read_text(encoding='utf-8'))
    steps = Steps(run / 'monthly-verification-steps.json')
    report_path = run / 'monthly-verification.json'
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {
        'recognition_run': run.name, 'recognition_providers': ['relay/codestral-2508', 'groq/whisper-large-v3'],
        'human_listening': False, 'semantic_acceptance': 'pending', 'people': {}}
    for pid, pair in pairs.items():
        owner = pair['owner']; root = '/api/v1/workbench/subjects/' + owner['subject_id']
        stories = call('GET', root + '/stories', owner)['items']
        selected = [s for s in stories if s['episode_id'] in {
            v['episode_id'] for k,v in mapping.items() if k.startswith(pid + '-')}]
        if len(selected) != 10 or any(s['status'] != 'ready' or not s['reviewed']
                or s['stt_model_version'] != next(v.get('asr_model', 'relay/codestral-2508') for v in mapping.values()
                    if v['episode_id'] == s['episode_id']) for s in selected):
            raise RuntimeError(pid + ': expected ten actual reviewed cloud-ASR stories.')
        save(run / (pid + '.final-owner-stories.json'), selected)
        save(run / (pid + '.final-reader-stories.json'), call('GET', root + '/stories', pair['reader']))
        row = report['people'].setdefault(pid, {})
        row.update(stories=len(selected), saved_memories=sum(len(s['memories']) for s in selected))
        from collections import Counter
        row['asr_provenance'] = dict(Counter(s['stt_model_version'] for s in selected))
        try:
            consents = call('GET', '/api/v1/consents?subject_id=' + owner['subject_id'], owner)
            cloud = next(c['consent_id'] for c in consents if c['scope'] == 'CLOUD_TWIN' and c['status'] == 'granted')
            job = steps.once(pid + '/monthly-profile', lambda: call('POST', root + '/profile-candidates/refresh',
                owner, json={'cloud_consent_id': cloud}))
            profile = wait_profile(lambda: call('GET', root + '/profile-candidates', owner), job['job_id'])
            current = [i for i in profile['items'] if i['source_version'] == profile['source_version']]
            row['profile_candidates'] = current
            row['profile_job'] = job['job_id']
            row['profile_state'] = 'complete' if current else 'empty_quality_issue'
        except Exception as error:
            row['profile_state'] = 'failed'
            row.setdefault('profile_errors', []).append(str(error))
        save(report_path, report)
        print(pid, 'actual monthly profile:', row['profile_state'], flush=True)
    # Existing question runner only sends each question. Gold answers are never
    # included in API requests. Pin both identities and Episode IDs to this run.
    qa_round.AUTH = run / 'identities.json'
    qa_round.MAPPING = run / 'product-episodes.json'
    original = sys.argv
    try:
        sys.argv = ['qa_round.py', '--round', run.name + '-cloud-v1']
        qa_round.main()
    finally:
        sys.argv = original
    report['qa_file'] = str(OUT / ('qa-' + run.name + '-cloud-v1.json'))
    report['semantic_acceptance'] = 'awaiting separate source/fact/privacy audit'
    save(report_path, report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not args.run.replace('-', '').isalnum(): raise SystemExit('Invalid run')
    verify(OUT / 'cloud-asr-runs' / args.run)
