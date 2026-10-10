"""Durable post-ASR product checks; successful model mutations are never replayed."""
import hashlib
import json
import time
import httpx
from speech_pipeline import save
from product_loop import call

QUESTIONS = {'bus_driver': '他对女儿说过关于平安回家的什么话？',
             'firefighter': '她第一次独立值班之后给谁打了电话？',
             'life_review': '他开的工作室是大工作室还是小工作室？'}


class Steps:
    def __init__(self, path):
        self.path = path
        self.data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

    def once(self, key, operation):
        row = self.data.get(key)
        if row is not None:
            if 'result' in row: return row['result']
            raise RuntimeError(key + ': previous attempted mutation has no confirmed result; not replayed. Inspect server state first.')
        self.data[key] = {'state': 'started', 'at': time.time()}; save(self.path, self.data)
        try:
            result = operation()
            self.data[key].update(state='complete', result=result)
            save(self.path, self.data)
            return result
        except Exception as error:
            self.data[key].update(state='needs_inspection', error_type=type(error).__name__)
            save(self.path, self.data)
            raise


def wait_profile(read, job_id, seconds=180):
    end = time.monotonic() + seconds
    while True:
        result = read()
        status = next((j['status'] for j in result.get('jobs', []) if j['job_id'] == job_id), None)
        if status == 'failed': raise RuntimeError('Profile job failed; inspect existing job, do not submit a duplicate.')
        if status == 'complete':
            if not result.get('items'): raise RuntimeError('Profile returned no candidates; not accepted as profile completion.')
            return result
        if time.monotonic() >= end: raise RuntimeError('Profile still pending; resume to wait on the same job.')
        time.sleep(2)


def followthrough(run, pairs, mapping):
    steps = Steps(run / 'followthrough-steps.json')
    report_path = run / 'followthrough-results.json'
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {'people': {}}
    for pid, pair in pairs.items():
        owner, reader = pair['owner'], pair['reader']
        subject = owner['subject_id']; eid = mapping[pid + '-01']['episode_id']
        root = '/api/v1/workbench/subjects/' + subject
        twin = '/api/v1/subjects/' + subject + '/twin/answers'
        def post(label, path, identity, body=None, method='POST'):
            return steps.once(pid + '/' + label, lambda: call(method, path, identity, **({'json': body} if body else {})))
        story = next(s for s in call('GET', root + '/stories', owner)['items'] if s['episode_id'] == eid)
        assert story['reviewed'] and story['status'] == 'ready' and story['memories']
        assert all(e['excerpt'] in story['transcript'] for m in story['memories'] for e in m['evidence'])
        audio = httpx.get('http://127.0.0.1:8877' + root + '/stories/' + eid + '/audio',
            headers={'Authorization': 'Bearer ' + owner['actor_token']}, trust_env=False, timeout=30)
        assert audio.status_code == 200 and hashlib.sha256(audio.content).hexdigest() == mapping[pid + '-01']['audio_sha256']
        cloud = post('text-consent', '/api/v1/consents', owner, {'subject_id': subject, 'scope': 'CLOUD_TWIN',
            'evidence_ref': 'authorized-fictional-cloud-asr-evaluation'})['consent_id']
        answer = post('owner-qa', twin, owner, {'question': QUESTIONS[pid], 'cloud_consent_id': cloud})
        assert answer['response_type'] != 'UNKNOWN' and answer['evidence']
        unknown = post('unknown-qa', twin, owner, {'question': '他或她的银行卡密码是多少？', 'cloud_consent_id': cloud})
        assert unknown['response_type'] == 'UNKNOWN'
        grant = post('story-grant', root + '/grants', owner, {'episode_id': eid,
            'reader_actor_id': reader['actor_id'], 'include_audio_confirmed': True, 'cloud_processing_allowed': True})
        reader_answer = post('reader-qa', twin, reader, {'question': QUESTIONS[pid], 'cloud_consent_id': grant['grant_id']})
        assert reader_answer['response_type'] != 'UNKNOWN' and reader_answer['evidence']
        assert all(e['episode_id'] == eid for e in reader_answer['evidence'])
        # Keep revoke in durable steps too; resume after revoke never re-shares.
        post('revoke', root + '/grants/' + grant['grant_id'], owner, method='DELETE')
        for suffix in (root + '/stories/' + eid + '/audio', twin + '/' + reader_answer['answer_id']):
            blocked = httpx.get('http://127.0.0.1:8877' + suffix,
                headers={'Authorization': 'Bearer ' + reader['actor_token']}, trust_env=False, timeout=30)
            assert blocked.status_code == 404
        job = post('profile-job', root + '/profile-candidates/refresh', owner, {'cloud_consent_id': cloud})
        profile = wait_profile(lambda: call('GET', root + '/profile-candidates', owner), job['job_id'])
        report['people'][pid] = {'episode_id': eid, 'memory_count': len(story['memories']),
            'owner_answer': answer, 'reader_answer': reader_answer, 'unknown_answer': unknown,
            'profile': profile, 'audio_hash_pass': True, 'revoke_pass': True,
            'human_listening': False, 'semantic_review': 'pending'}
        save(report_path, report)
        print(pid, 'source/playback/QA/revoke/profile checks saved; quality pending', flush=True)
