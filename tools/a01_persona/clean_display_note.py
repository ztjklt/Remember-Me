"""Prepare a clean user-facing opinion; wait for explicit root --go to write."""
import argparse
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('a01_voice_shared', Path(__file__).with_name('voice_companion_live.py'))
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
OUT = shared.VAR / 'companion-display-cleanup-20261012-v2'
CLEAN = ('我觉得，留下旧物有时也能留下和一个人有关的回忆，不一定只是为了省钱。'
         '陈国梁自己怎么想，我还想听听他的说法。')


def prepare(path):
    voice_plan = shared.read(shared.OUT / 'plan.json')
    old = shared.read(shared.OUT / 'display-opinion.json')
    if old['classification'] != 'opinion' or old['text'] != shared.DISPLAY_NOTE:
        raise ValueError('Original opinion differs from reviewed clean replacement')
    plan = {key: voice_plan[key] for key in ('base_url', 'subject_id', 'owner_actor_id', 'reader_actor_id', 'state_path')}
    plan.update(schema='a01-clean-opinion-plan-v1', original_note_id=old['id'], original_text=old['text'],
                replacement_text=CLEAN, classification='opinion', model_use=False,
                provenance='Additional fictional display opinion; remove engineering header only, keep original as withdrawn history')
    if path.exists() and shared.read(path) != plan:
        raise ValueError('Different cleanup plan already exists')
    shared.save(path, plan)
    return plan


def create_body(plan):
    if plan['replacement_text'] != CLEAN:
        raise ValueError('Clean replacement changed')
    return {'idempotency_key': 'a01-clean-display-' + shared.digest(plan)[:20],
            'classification': 'opinion', 'text': CLEAN, 'narrative_ids': []}


def execute(plan, record):
    with shared.live_clients(plan) as clients:
        run = shared.Run(plan, record, clients)
        old_path = run.companion + '/contributions/' + plan['original_note_id']
        old = run.body('cleanup.original', 'reader', 'GET', old_path)
        if (old['status'] != 'accepted' or old.get('text') != plan['original_text']
                or old['author_actor_id'] != plan['reader_actor_id']):
            raise ValueError('Original display note changed; do not withdraw a different resource')
        withdrawn = run.body('cleanup.withdraw', 'reader', 'POST', old_path + '/withdraw', {'revision': old['revision']})
        if withdrawn['status'] != 'withdrawn' or 'text' in withdrawn:
            raise ValueError('Old display note was not hidden')
        note = run.body('cleanup.create', 'reader', 'POST', run.companion + '/contributions', create_body(plan))
        accepted = run.body('cleanup.accept', 'owner', 'POST', run.companion + '/contributions/' + note['id'] + '/review',
                            {'revision': note['revision'], 'decision': 'accepted'})
        for role in ('reader', 'owner'):
            current = run.body('cleanup.readback.' + role, role, 'GET', run.companion + '/contributions/' + note['id'])
            if (current.get('text') != CLEAN or current['status'] != 'accepted'
                    or current['model_use_author_allowed'] or current['model_use_owner_allowed']
                    or current.get('audio_id') or current['id'] == plan['original_note_id']):
                raise ValueError('New display opinion is not the clean model-disabled resource')
        shared.save(record.path.parent / 'clean-opinion.json', accepted)
        return {'old_note_id': plan['original_note_id'], 'new_note_id': note['id'], 'model_use': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('--go', action='store_true')
    args = parser.parse_args()
    if args.action == 'run' and not args.go:
        parser.error('Writes require --go from the parent; no runtime request sent')
    path = OUT / 'plan.json'
    if args.action == 'prepare':
        prepare(path)
        print('Clean opinion replacement prepared; no runtime call')
        return
    plan = shared.read(path)
    if plan['base_url'] != shared.BASE:
        raise ValueError('Only local approved runtime accepted')
    record = shared.Checkpoint(OUT / 'run.json', plan)
    with shared.run_lock(OUT / 'run.lock'):
        result = record.once('cleanup.run', lambda: execute(plan, record))
        print('Old display note withdrawn; clean opinion accepted with model use disabled')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Stopped (' + type(exc).__name__ + '); preserved cleanup checkpoint') from None
