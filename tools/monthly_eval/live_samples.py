"""Real API smoke loop on authorized fictional ASR; not listening-quality acceptance.

No fixture providers, direct business DB writes, or benchmark answer injection.
Local ignored report records actual responses, including failed steps.
"""
import hashlib
import json
import time
import httpx
from product_loop import AUTH, MAPPING, OUT, save

REPORT = OUT / 'live-sample-loop.json'
BASE = 'http://127.0.0.1:8877'
QUESTIONS = {
    'bus_driver': '他对女儿说过关于平安回家的什么话？',
    'firefighter': '她第一次独立值班之后给谁打了电话？',
    'life_review': '他开的工作室是大工作室还是小工作室？',
}


def main():
    pairs = json.loads(AUTH.read_text(encoding='utf-8'))
    mapping = json.loads(MAPPING.read_text(encoding='utf-8'))
    if REPORT.exists():
        save(OUT / f'live-sample-loop-history-{time.time_ns()}.json', json.loads(REPORT.read_text(encoding='utf-8')))
    report = {'mode': 'real_models_imperfect_fictional_asr_authorized',
              'listening_quality_pass': False, 'steps': [], 'people': {}}

    def request(label, method, path, identity, expected=(200, 201, 202), **kwargs):
        start = time.monotonic()
        r = httpx.request(method, BASE + path, trust_env=False, timeout=100,
                          headers={'Authorization': 'Bearer ' + identity['actor_token']}, **kwargs)
        is_json = 'json' in r.headers.get('content-type', '')
        result = r.json() if is_json else {'bytes': len(r.content), 'sha256': hashlib.sha256(r.content).hexdigest()}
        step = {'label': label, 'method': method, 'path': path, 'status': r.status_code,
                'elapsed_seconds': round(time.monotonic() - start, 3), 'result': result,
                'expected_status_pass': r.status_code in expected}
        report['steps'].append(step); save(REPORT, report)
        print(label, r.status_code, flush=True)
        if r.status_code not in expected:
            raise RuntimeError(f'{label}: HTTP {r.status_code}; see ignored report')
        return result

    for person, pair in pairs.items():
        if person + '-01' not in mapping: continue
        owner, reader = pair['owner'], pair['reader']
        subject = owner['subject_id']; ep = mapping[person + '-01']['episode_id']
        root = '/api/v1/workbench/subjects/' + subject
        twin = '/api/v1/subjects/' + subject + '/twin/answers'
        data = report['people'][person] = {'episode_id': ep, 'subject_id': subject}
        for attempt in range(90):
            r = httpx.get(BASE + '/api/v1/episodes/' + ep, trust_env=False,
                          headers={'Authorization': 'Bearer ' + owner['actor_token']}).json()
            if r['status'] in ('ready', 'failed'): break
            time.sleep(2)
        if r['status'] != 'ready': raise RuntimeError(person + ': processing ' + r['status'])
        result = request(person + ': extracted memories', 'GET', '/api/v1/episodes/' + ep + '/result', owner)
        assert result['model_version'] == 'Deepseek-v4-flash'
        stories = request(person + ': persisted stories', 'GET', root + '/stories', owner)['items']
        story = next(x for x in stories if x['episode_id'] == ep)
        assert story['reviewed'] and story['memories']
        data['memory_count'] = len(story['memories'])
        data['evidence_exact'] = all(e['excerpt'] in story['transcript'] for m in story['memories'] for e in m['evidence'])
        assert data['evidence_exact']
        consents = request(person + ': consent list', 'GET', '/api/v1/consents?subject_id=' + subject, owner)
        cloud = next((c['consent_id'] for c in consents if c['scope'] == 'CLOUD_TWIN' and c['status'] == 'granted'), None)
        if not cloud:
            cloud = request(person + ': allow fictional cloud QA', 'POST', '/api/v1/consents', owner,
                json={'subject_id': subject, 'scope': 'CLOUD_TWIN', 'evidence_ref': 'user-authorized-fictional-live-eval'})['consent_id']
        data['cloud_consent_id'] = cloud
        answer = request(person + ': owner grounded QA', 'POST', twin, owner,
            json={'question': QUESTIONS[person], 'cloud_consent_id': cloud})
        assert answer['response_type'] != 'UNKNOWN' and answer['evidence']
        data['answer_id'] = answer['answer_id']
        unknown = request(person + ': unsupported question', 'POST', twin, owner,
            json={'question': '他或她的银行卡密码是多少？', 'cloud_consent_id': cloud})
        assert unknown['response_type'] == 'UNKNOWN'
        # Revoke a leftover grant from an interrupted prior run, through the API.
        existing = request(person + ': existing grants', 'GET', root + '/grants', owner)['items']
        for g in existing:
            if g['reader_actor_id'] == reader['actor_id'] and g['episode_id'] == ep:
                request(person + ': reset interrupted grant', 'DELETE', root + '/grants/' + g['grant_id'], owner)
        request(person + ': before sharing hidden', 'GET', root + '/stories', reader, expected=(404,))
        grant = request(person + ': share story including audio', 'POST', root + '/grants', owner,
            json={'episode_id': ep, 'reader_actor_id': reader['actor_id'],
                  'include_audio_confirmed': True, 'cloud_processing_allowed': True})
        data['grant_id'] = grant['grant_id']
        visible = request(person + ': reader stories', 'GET', root + '/stories', reader)['items']
        assert [x['episode_id'] for x in visible] == [ep]
        audio = request(person + ': authorized original audio', 'GET', root + '/stories/' + ep + '/audio', reader)
        assert audio['sha256'] == mapping[person + '-01']['audio_sha256']
        reader_answer = request(person + ': reader source QA', 'POST', twin, reader,
            json={'question': QUESTIONS[person], 'cloud_consent_id': grant['grant_id']})
        assert reader_answer['response_type'] != 'UNKNOWN' and reader_answer['evidence']
        request(person + ': reader portrait', 'GET', root + '/portrait', reader)
        question = request(person + ': reader asks for more', 'POST', root + '/requests', reader,
            json={'text': '希望你以后再讲一段当时的日常，想不起来也没关系。'})
        data['request_id'] = question['request_id']
        request(person + ': owner snoozes request', 'PATCH', root + '/requests/' + question['request_id'], owner,
            json={'status': 'snoozed'})
        request(person + ': owner reopens request', 'PATCH', root + '/requests/' + question['request_id'], owner,
            json={'status': 'pending'})
        request(person + ': revoke sharing', 'DELETE', root + '/grants/' + grant['grant_id'], owner)
        request(person + ': revoked audio blocked', 'GET', root + '/stories/' + ep + '/audio', reader, expected=(404,))
        request(person + ': revoked answer blocked', 'GET', twin + '/' + reader_answer['answer_id'], reader, expected=(404,))
        request(person + ': revoked new QA blocked', 'POST', twin, reader, expected=(403, 404),
            json={'question': QUESTIONS[person], 'cloud_consent_id': grant['grant_id']})
        job = request(person + ': request profile proposal', 'POST', root + '/profile-candidates/refresh', owner,
            json={'cloud_consent_id': cloud})
        for _ in range(60):
            profile = httpx.get(BASE + root + '/profile-candidates', trust_env=False,
                headers={'Authorization':'Bearer ' + owner['actor_token']}).json()
            status = next(j['status'] for j in profile['jobs'] if j['job_id'] == job['job_id'])
            if status in ('complete', 'failed'): break
            time.sleep(1)
        data['profile_status'] = status
        data['profile_result'] = profile
        save(REPORT, report)
    report['transport_and_rule_checks_passed'] = True
    report['semantic_review'] = 'pending inspect real answers; do not infer quality from HTTP200'
    save(REPORT, report)


if __name__ == '__main__': main()
