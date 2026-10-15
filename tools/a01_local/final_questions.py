"""One fixed end-to-end pass over all twelve A01 questions; never reads gold.

Answers come from the running backend and persisted actual ASR. A started task
is not replayed on restart, and a failed answer is retained rather than picked
from repeated generations. This file does not perform semantic self-scoring.
"""
import json
import time
from datetime import datetime, timezone
import httpx
from ingest import BASE, VAR, STATE, request, save
from runtime import ROOT


def main():
    path = VAR / 'runtime/final-questions.json'
    state = json.loads(STATE.read_text(encoding='utf8'))
    questions = json.loads((ROOT/'evaluations/a01-20261012/input/questions.json').read_text(encoding='utf8'))
    expected = ['Q01','Q02','Q03','Q04','Q05','Q06','Q07','Q08','U01','U02','A01','N01']
    assert [q['id'] for q in questions] == expected
    result = json.loads(path.read_text(encoding='utf8')) if path.exists() else {
        'schema': 'a01-final-api-qa-v1', 'fictional': True, 'input': 'persisted_actual_ASR',
        'question_ids': expected, 'source': 'input/questions.json; no reference-only file read',
        'endpoint': BASE, 'expected_model': 'Deepseek-v4-flash', 'items': []}
    account = json.loads((VAR/'private/local-accounts.json').read_text(encoding='utf8'))['owner']
    with httpx.Client(base_url=BASE, headers={'Origin': BASE}, trust_env=False, timeout=180) as client:
        request(client, 'POST', '/api/v1/accounts/login', json={k: account[k] for k in ('username','password')})
        for item in questions:
            if any(r['id'] == item['id'] for r in result['items']):
                continue
            record = {**item, 'status': 'started', 'utc': datetime.now(timezone.utc).isoformat(),
                      'semantic_review': 'pending'}
            result['items'].append(record); save(path, result)
            started = time.monotonic()
            try:
                response = client.post('/api/v1/subjects/'+state['subject_id']+'/twin/answers',
                    json={'question': item['question'], 'cloud_consent_id': state['CLOUD_TWIN']})
                record.update(http_status=response.status_code, response=response.json(),
                              status='delivered' if response.is_success else 'failed')
            except (httpx.HTTPError, ValueError) as exc:
                record.update(status='failed', error_type=type(exc).__name__)
            record['elapsed_seconds'] = round(time.monotonic()-started,3)
            save(path,result)
            print(item['id'], record['status'], record['elapsed_seconds'], flush=True)


if __name__ == '__main__':
    main()
