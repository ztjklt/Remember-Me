"""Run on ECS as root with the current backend on PYTHONPATH.

Creates independent ordinary owner/reader account pairs using existing admin
rules. Credentials remain in a root-only file. Reruns validate and retain them.
No provider configuration, registration setting or permission rule is changed.
"""
import argparse
import json
import os
from pathlib import Path
import secrets


def main():
    from dotenv import dotenv_values
    from sqlalchemy.engine import make_url
    from app.account_admin import create_account
    from app.access import publication_lock
    from app.db import Database
    from app.models import Account, Subject

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--groups', type=int, default=4)
    parser.add_argument('--batch', default='20261010')
    parser.add_argument('--output', type=Path, default=Path('/var/lib/remember-me/private/team-20261010.json'))
    args = parser.parse_args()
    if os.geteuid() != 0 or not 1 <= args.groups <= 8 or not args.batch.isdigit():
        parser.error('Requires root, 1..8 groups and a numeric batch')
    target = args.output.resolve()
    if target.parent != Path('/var/lib/remember-me/private'):
        parser.error('Credentials must remain in the service private directory')
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    pending = target.with_suffix('.pending')
    config = dotenv_values('/etc/remember-me/api.env')
    url = make_url(config['REMEMBER_DATABASE_URL'])
    db = Database(url.render_as_string(hide_password=False))
    try:
        with db.session() as session:
            if url.drivername.startswith('postgresql') and not url.host and not url.password and url.username:
                import pwd
                uid = os.geteuid()
                try:
                    os.seteuid(pwd.getpwnam(url.username).pw_uid)
                    session.connection()
                finally:
                    os.seteuid(uid)
            publication_lock(session, '')
            existing = target if target.exists() else pending if pending.exists() else None
            if existing:
                data = json.loads(existing.read_text(encoding='utf-8'))
                if data['batch'] != args.batch or len(data['groups']) != args.groups:
                    raise RuntimeError('Existing credential batch differs; nothing reset')
                for group in data['groups']:
                    for role in ('owner', 'reader'):
                        row = group[role]
                        account, subject = session.get(Account, row['username']), session.get(Subject, row['subject_id'])
                        if not account or account.actor_id != row['actor_id'] or not subject or subject.owner_actor_id != row['actor_id']:
                            raise RuntimeError('Existing handoff does not match database; inspect without resetting')
                if existing == pending:
                    pending.replace(target)
                os.chmod(target, 0o600)
                print(f'Validated {args.groups * 2} existing ordinary accounts; passwords retained.')
                return
            data = {'batch': args.batch, 'groups': []}
            for number in range(1, args.groups + 1):
                group = {'group': number}
                for role, name in [('owner', '记录者'), ('reader', '亲友')]:
                    username = f'team_{args.batch}_{number:02d}_{role}'
                    if session.get(Account, username):
                        raise RuntimeError('Username exists without handoff; inspect without resetting')
                    password = secrets.token_urlsafe(20)
                    group[role] = {**create_account(session, username, password, f'内测{number}组{name}'), 'password': password}
                data['groups'].append(group)
            with pending.open('x', encoding='utf-8') as output:
                os.chmod(pending, 0o600)
                json.dump(data, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            session.commit()
            pending.replace(target)
            print(f'Created {args.groups * 2} ordinary accounts. Credentials saved privately; none printed.')
    finally:
        db.dispose()


if __name__ == '__main__':
    main()
