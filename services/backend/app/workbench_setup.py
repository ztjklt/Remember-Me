"""Explicit local identity bootstrap / legacy ownership mapping (no public signup)."""
import argparse
import json
from pathlib import Path
from .config import get_settings
from .db import Database
from .models import Subject, Actor
from .seed import seed_development_data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='var/local-identities.json')
    parser.add_argument('--map-subject')
    parser.add_argument('--owner-actor')
    args = parser.parse_args()
    db = Database(get_settings().database_url)
    try:
        with db.session() as session:
            if args.map_subject or args.owner_actor:
                if not args.map_subject or not args.owner_actor:
                    parser.error('Both mapping arguments are required')
                subject = session.get(Subject, args.map_subject)
                actor = session.get(Actor, args.owner_actor)
                if not subject or not actor or subject.owner_actor_id not in (None, actor.actor_id):
                    parser.error('Mapping must reference existing records and cannot transfer an owned space')
                subject.owner_actor_id = actor.actor_id
                session.commit()
                print('Explicit ownership mapping saved; no new grants created.')
                return
            target = Path(args.output)
            if target.exists():
                parser.error('Identity file already exists; refusing to replace credentials')
            target.parent.mkdir(parents=True, exist_ok=True)
            results = {}
            for role, name in [('owner', '本机记录者'), ('reader', '本机读者')]:
                result = seed_development_data(session, subject_name=name, actor_name=name)
                results[role] = vars(result)
            with target.open('x', encoding='utf-8') as file:
                json.dump(results, file, ensure_ascii=False, indent=2)
            target.chmod(0o600)
            print(f'Created two local identities. Credentials are only in {target.resolve()}')
    finally:
        db.dispose()


if __name__ == '__main__':
    main()
