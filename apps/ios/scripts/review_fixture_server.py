"""Isolated iOS contract/UI fixture. Fictional text, fake audio/model, loopback only.

Requires the approved Backend revision containing narrative/profile APIs. No
cloud credentials or provider calls. Does not modify the working Backend tree.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-root', type=Path, required=True)
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--contract-output', type=Path)
    parser.add_argument('--pairing-output', type=Path)
    parser.add_argument('--port', type=int, default=8447)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    root = args.backend_root.resolve()
    sys.path[:0] = [str(root), str(root / 'tests')]
    from app.config import Settings
    from app.main import create_app
    from app.models import Episode, Evidence, ProfileCandidate
    from app.access import profile_source_basis
    from app.materials import effective_materials
    from conftest import upgrade_to_head
    from test_agent_workbench import setup_pair
    from test_twin_voice import _record
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    runtime = args.runtime_dir.resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    db = runtime / 'fixture.sqlite'
    db.unlink(missing_ok=True)
    settings = Settings(_env_file=None, environment='test', log_level='WARNING',
                        database_url=f'sqlite:///{db}', object_store_backend='memory')
    upgrade_to_head(settings.database_url)
    app = create_app(settings)
    @app.middleware('http')
    async def record_fixture_requests(request, call_next):
        response = await call_next(request)
        with (runtime / 'requests.jsonl').open('a') as log:
            log.write(json.dumps({'method': request.method, 'path': request.url.path, 'status': response.status_code}) + '\n')
        return response
    client = TestClient(app)
    with app.state.database.session() as session:
        owner, reader, headers, _, episode, cloud = setup_pair(app, client, session)
        session.get(Episode, episode).idempotency_key += '-first'
        session.commit()
        second = _record(client, app, owner.subject_id, owner.consent_id, headers)
        # Change fictional text coherently, retaining real source/provenance mechanics.
        for ep, text in [(episode, '下班后我喜欢散步，先安静一会儿再做决定。'),
                         (second, '赶时间时我会先行动，不会总等到想清楚。')]:
            session.get(Episode, ep).transcript = text
            for evidence in session.scalars(select(Evidence).where(Evidence.episode_id == ep)):
                evidence.excerpt = text; evidence.span_start = 0; evidence.span_end = len(text)
        session.commit()
        materials = effective_materials(session, owner.subject_id, {episode, second})
        session.commit()
        ids = {m['episode_id']: m['evidence'][0]['evidence_id'] for m in materials}
        basis = profile_source_basis(session, owner.subject_id)
        session.add(ProfileCandidate(candidate_id='ios_fixture_candidate', subject_id=owner.subject_id,
            domain='DECISION_PATTERNS', kind='trait', statement='下班后倾向先安静下来再决定。',
            context='限定在下班后的情境；赶时间时存在不同做法。', evidence_ids=[ids[episode]],
            counter_evidence_ids=[ids[second]], independent_episodes=1, source_basis=basis,
            status='pending', model_version='fixture-only', prompt_version='fixture-only'))
        session.commit()
    base = f'/api/v1/workbench/subjects/{owner.subject_id}'
    source = next(e for e in client.get(base + '/narrative', headers=headers).json()['source_evidence'] if e['episode_id'] == episode)
    result = client.post(base + '/narrative/records', headers=headers, json=dict(kind='style',
        title='散步时的原话', text=source['excerpt'], evidence_ids=[source['evidence_id']],
        facets=['EXPRESSION'], time_text='', place_text='', aliases=[], same_event=False, recipient_label=''))
    assert result.status_code == 201, result.text
    captured = {key: client.get(base + suffix, headers=headers).json() for key, suffix in
                [('overview', '/narrative'), ('candidates', '/profile-candidates'),
                 ('updates', '/profile-candidates/updates'), ('jobs', '/narrative/jobs')]}
    if args.contract_output:
        # Normalize random IDs only; keep Backend-produced field names, types and states.
        replacements = {owner.subject_id: 'subject', source['evidence_id']: 'evidence_a',
                        ids[second]: 'evidence_b', episode: 'episode_a', second: 'episode_b',
                        result.json()['id']: 'record_style', basis: 'source-fixture'}
        def normalize(value):
            if isinstance(value, str): return replacements.get(value, value)
            if isinstance(value, list): return [normalize(v) for v in value]
            if isinstance(value, dict): return {k: normalize(v) for k, v in value.items()}
            return value
        args.contract_output.parent.mkdir(parents=True, exist_ok=True)
        args.contract_output.write_text(json.dumps(normalize(captured), ensure_ascii=False, indent=2) + '\n')
    cert, key = runtime / 'certificate.pem', runtime / 'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
                    '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost',
                    '-addext', 'subjectAltName=IP:127.0.0.1,DNS:localhost',
                    '-addext', 'extendedKeyUsage=serverAuth',
                    '-addext', 'keyUsage=critical,digitalSignature,keyEncipherment'], check=True, capture_output=True)
    der = subprocess.check_output(['openssl', 'x509', '-in', str(cert), '-outform', 'DER'])
    pairing = dict(baseURL=f'https://127.0.0.1:{args.port}', fingerprint=hashlib.sha256(der).hexdigest(),
                   token=owner.actor_token, actorID=owner.actor_id, subjectID=owner.subject_id,
                   consentID=owner.consent_id, displayName='虚构验收样例')
    if args.pairing_output:
        args.pairing_output.parent.mkdir(parents=True, exist_ok=True)
        args.pairing_output.write_text(json.dumps(pairing))
    if args.serve:
        import uvicorn
        print('Fictional iOS fixture listening on loopback; no real model or recordings.', flush=True)
        uvicorn.run(app, host='127.0.0.1', port=args.port, ssl_certfile=str(cert), ssl_keyfile=str(key), log_level='warning')


if __name__ == '__main__':
    main()
