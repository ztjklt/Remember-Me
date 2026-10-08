"""Offline audit of saved actual answers with explicit per-answer annotations.

No model calls, transcript edits, or gold answers sent to the product. Current
source resolution is checked separately from the assistant's semantic review.
"""
import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'services/backend'
sys.path.insert(0, str(BACKEND))


def audit(run, annotations):
    from app.db import Database
    from app.config import Settings
    from app.materials import effective_materials
    from app.access import visible_episodes, altered_story_ids
    batch = json.loads((BACKEND / 'var/monthly-eval' / ('qa-' + run.name + '-cloud-v1.json')).read_text(encoding='utf-8'))
    if not batch.get('finished_at'): raise RuntimeError('Wait for the complete batch.')
    rows = [row for g in batch['qa'].values() for row in g['checks']]
    if len(rows) != 60 or set(annotations) != {r['id'] for r in rows}:
        raise RuntimeError('Explicit review of all 60 answers is required.')
    auth = json.loads((run / 'identities.json').read_text(encoding='utf-8'))
    db = Database(Settings().database_url)
    reviewed = []
    for pid, group in batch['qa'].items():
        for role in ('owner', 'reader'):
            identity = auth[pid][role]; subject = auth[pid]['owner']['subject_id']
            with db.session() as session:
                ids = visible_episodes(session, subject, identity['actor_id'], cloud=True)
                if role == 'reader': ids -= altered_story_ids(session, ids)
                valid = {e['evidence_id']: e for c in effective_materials(session, subject, ids) for e in c['evidence']}
            for row in group['checks']:
                if row['role'] != role: continue
                result = row.get('result'); errors = []
                if result is None: errors.append('request_failed')
                else:
                    for evidence in result['evidence']:
                        original = valid.get(evidence['evidence_id'])
                        if original is None: errors.append('outside_current_scope')
                        elif (original['excerpt'], original['source_type']) != (evidence['excerpt'], evidence['source_type']):
                            errors.append('source_mismatch')
                    if result['response_type'] == 'ORIGINAL' and not any(result['answer'] == e['excerpt'] for e in result['evidence']):
                        errors.append('original_not_exact')
                note = annotations[row['id']]
                assert note['grade'] in {'supported', 'needs_quality_correction', 'failed'}
                reviewed.append({'id': row['id'], 'role': role, 'question': row['question'],
                    'result': result, 'mechanical_errors': errors, **note})
    report = {'recognition_run': run.name, 'reviewer': 'assistant offline text and evidence review',
        'human_listening': False, 'clinical_validation': False,
        'counts': dict(Counter(r['grade'] for r in reviewed)),
        'mechanical_failures': sum(bool(r['mechanical_errors']) for r in reviewed),
        'request_failures': sum(r['result'] is None for r in reviewed),
        'limitations': ['Current visible citations checked, not historical network payload capture.',
                       'Exact quote does not alone prove semantic entailment.',
                       'Fictional synthesized speech, not natural speech accuracy validation.'],
        'items': sorted(reviewed, key=lambda r: r['id'])}
    (run / 'qa-text-review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'items'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not args.run.replace('-', '').isalnum(): raise SystemExit('Invalid run')
    os.chdir(BACKEND)
    run = BACKEND / 'var/monthly-eval/cloud-asr-runs' / args.run
    audit(run, json.loads((run / 'qa-review-annotations.json').read_text(encoding='utf-8')))
