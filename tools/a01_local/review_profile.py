"""One explicit technical review of fictional A01, not real-subject approval.

This decision follows reading the actual ASR quotes and the generated statement.
Other candidates remain pending. No creation manuscript or gold is consumed.
"""
import json
import httpx
from ingest import BASE, VAR, STATE, request, save


def main():
    path = VAR / 'runtime/profile-technical-review.json'
    if path.exists():
        print('Explicit technical profile decision already recorded; no duplicate action.')
        return
    state = json.loads(STATE.read_text(encoding='utf8'))
    accounts = json.loads((VAR / 'private/local-accounts.json').read_text(encoding='utf8'))
    clients = {}
    for role, account in accounts.items():
        c = httpx.Client(base_url=BASE, headers={'Origin': BASE}, trust_env=False, timeout=45)
        request(c, 'POST', '/api/v1/accounts/login', json={k: account[k] for k in ('username', 'password')})
        clients[role] = c
    owner, reader = clients['owner'], clients['reader']
    root = '/api/v1/workbench/subjects/' + state['subject_id']
    rows = request(owner, 'GET', root + '/profile-candidates')['items']
    row = next(r for r in rows if r['candidate_id'] == 'pc_fff22a0500178aefe288cf5d35217e4a8bf49afc')
    # Guard this exact reviewed output; this is not an automatic approval rule.
    assert row['statement'] == '讲述者不喜欢浪费，灯不用就关，东西坏了能修就修，看到年轻人一说换新的就心疼钱。'
    assert len(row['counter_evidence_ids']) == 2
    assert row['status'] in {'pending', 'confirmed'}
    request(owner, 'POST', root + '/profile-candidates/' + row['candidate_id'] + '/confirm')
    selected = next(r for r in request(owner, 'GET', root + '/narrative')['records'] if r['title'] == '给豆豆买画笔')
    body = {'narrative_ids': [selected['id']], 'profile_candidate_ids': [row['candidate_id']],
            'recipient_actor_ids': [state['reader_actor_id']]}
    preview = request(owner, 'POST', root + '/companion/snapshots/preview', json=body)
    snapshot = request(owner, 'POST', root + '/companion/snapshots', json={**body,
        'idempotency_key': 'a01-reviewed-frugality-demonstration-v1',
        'source_version': preview['source_version'], 'confirmed': True})
    visible = request(reader, 'GET', root + '/companion/snapshots/' + snapshot['id'])
    assert len(visible['items']) == 2
    current = request(owner, 'GET', root + '/profile-candidates')
    save(path, {'basis': 'fictional technical text review; not real-person endorsement or audio listening',
        'reviewer': 'Codex explicit evidence review', 'decision': 'confirm_one',
        'reason': '本人明确自述日常节俭；同段昂贵画笔保留为例外，可能的原因没有升级为事实。不能外推为所有情境都节俭。',
        'reviewed_candidate': row, 'snapshot_id': snapshot['id'], 'snapshot_reader_items': len(visible['items']),
        'statuses': {s: sum(r['status'] == s for r in current['items']) for s in ('pending', 'confirmed', 'rejected')}})
    save(VAR / 'runtime/profile-reviewed.json', current)
    print('One conditional profile technically reviewed; named reader can read its two-item sealed version.')


if __name__ == '__main__':
    main()
