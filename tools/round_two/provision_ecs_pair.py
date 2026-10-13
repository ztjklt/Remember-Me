"""On ECS only: provision dedicated ordinary demo accounts using admin rules.
Passwords are written once to a root-only file, never printed or reset on rerun.
"""
import json,os,secrets
from pathlib import Path
from dotenv import dotenv_values
from app.account_admin import create_account
from app.db import Database
from app.access import publication_lock
from app.models import Account
from sqlalchemy.engine import make_url
from sqlalchemy import text

def main():
    assert os.geteuid()==0
    target=Path('/var/lib/remember-me/private/paired-accounts.json')
    target.parent.mkdir(mode=0o700,exist_ok=True)
    if target.exists():
        print('Existing dedicated account file retained; no passwords reset.');return
    config=dotenv_values('/etc/remember-me/api.env')
    url=make_url(config['REMEMBER_DATABASE_URL'])
    peer_user=url.username if url.drivername.startswith('postgresql') and not url.host and not url.password else None
    db=Database(url.render_as_string(hide_password=False))
    try:
        with db.session() as session:
            if peer_user:
                # Connect using the existing service user's Unix peer identity;
                # no database grants or authentication settings are changed.
                import pwd
                uid=os.geteuid()
                try:
                    os.seteuid(pwd.getpwnam(peer_user).pw_uid)
                    session.connection()
                finally:os.seteuid(uid)
            revision=session.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
            if revision!='0016_share_invitations':
                raise RuntimeError('Deploy and verify the paired-release migrations before provisioning these accounts; nothing created')
            publication_lock(session,'');result={}
            for role,name in [('owner','内测记录者'),('reader','内测亲友')]:
                username='paired_'+role+'_20261009'
                if session.get(Account,username):raise RuntimeError('Account exists without handoff; inspect rather than resetting it')
                password=secrets.token_urlsafe(20)
                result[role]={**create_account(session,username,password,name),'password':password}
            temp=target.with_suffix('.pending')
            with temp.open('x') as f:os.chmod(temp,0o600);json.dump(result,f,ensure_ascii=False,indent=2)
            session.commit();temp.replace(target)
        print('Two ordinary accounts provisioned; credentials saved to the restricted file only.')
    finally:db.dispose()

if __name__=='__main__':main()
