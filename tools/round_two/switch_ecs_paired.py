"""Run on ECS after a source archive, restore drill and explicit quality gate.

Does not alter firewall/registration or delete any data. Application rollback
restores the old code/config only; the additive database migration is retained.
"""
import argparse,json,os,shutil,subprocess,time
from pathlib import Path

ROOT=Path('/opt/remember-me');CONFIG=Path('/etc/remember-me')
SERVICES=['ai','worker','profile','api']

def command(args,**kw):return subprocess.run(args,check=True,**kw)

def switch(link):
    temp=ROOT/'current.paired-next'
    if temp.exists() or temp.is_symlink():raise RuntimeError('Pending switch link exists; inspect first')
    temp.symlink_to(link);temp.replace(ROOT/'current')

def main():
    p=argparse.ArgumentParser();p.add_argument('--release',required=True);p.add_argument('--snapshot',required=True)
    args=p.parse_args();release=Path(args.release).resolve();snapshot=Path(args.snapshot).resolve()
    assert os.geteuid()==0 and release.parent==ROOT/'releases' and release.name.startswith('paired-')
    assert snapshot.parent==Path('/var/lib/remember-me/backups') and (snapshot/'restore-check.json').is_file()
    gate=json.loads((release/'quality-gate.json').read_text())
    assert gate['critical_failures']==0 and gate['whole_question_passes']>=54 and gate['total']==60
    assert gate['review_type']=='source-by-source semantic review' and gate['release_commit']
    previous=(ROOT/'current').resolve()
    assert previous!=release and str(previous)==(snapshot/'previous-release.txt').read_text().strip()
    previous_config=snapshot/'switch-config';previous_config.mkdir(mode=0o700)
    for name in SERVICES:shutil.copy2(CONFIG/(name+'.env'),previous_config/(name+'.env'))
    manifest={'previous_release':str(previous),'release':str(release),'snapshot':str(snapshot),'switched':False}
    def record(): (snapshot/'switch-result.json').write_text(json.dumps(manifest,indent=2))
    record()
    try:
        command(['systemctl','stop',*[f'remember-me@{x}' for x in ['api','worker','profile']]])
        # python-dotenv is already a runtime dependency. No config values go to logs.
        migrate="""import os,subprocess
from dotenv import dotenv_values
env={**os.environ,**{k:v for k,v in dotenv_values('/etc/remember-me/api.env').items() if v is not None}}
subprocess.run(['.venv/bin/python','-m','alembic','upgrade','head'],env=env,check=True)
"""
        with (snapshot/'production-migration.log').open('w') as log:
            command([str(release/'services/backend/.venv/bin/python'),'-c',migrate],cwd=release/'services/backend',stdout=log,stderr=log)
        for name in SERVICES:
            path=CONFIG/(name+'.env');updates={'REMEMBER_RELEASE_ID':gate['release_commit']}
            if name=='ai':
                updates['AI_TWIN_STRUCTURED_ANSWERS']='false'
                updates['AI_TWIN_QUOTE_ANSWERS']='true'
            if name in ['api','worker','profile']:updates['REMEMBER_AI_TIMEOUT_SECONDS']='120'
            lines=[line for line in path.read_text().splitlines() if line.split('=',1)[0] not in updates]
            tmp=path.with_suffix('.paired-next');tmp.write_text('\n'.join(lines+[k+'='+v for k,v in updates.items()])+'\n');tmp.chmod(0o600);tmp.replace(path)
        switch(release)
        for name in SERVICES:command(['systemctl','restart',f'remember-me@{name}'])
        import urllib.request
        for attempt in range(40):
            try:
                ready=json.load(urllib.request.urlopen('http://127.0.0.1:8877/ready',timeout=3))
                info=json.load(urllib.request.urlopen('http://127.0.0.1:8877/api/v1/service-info',timeout=3))
                assert info['release_id']==gate['release_commit'] and info['sharing_invitations'] and not info['registration_allowed']
                assert ready['status']=='ready';break
            except Exception:
                if attempt==39:raise
                time.sleep(1)
        for name in SERVICES:command(['systemctl','is-active','--quiet',f'remember-me@{name}'])
        manifest.update(switched=True,ready=ready,service_info=info);record()
        print(json.dumps(manifest))
    except Exception:
        # No database overwrite/downgrade: 0016 is additive and old code ignores it.
        command(['systemctl','stop',*[f'remember-me@{x}' for x in SERVICES]])
        for name in SERVICES:shutil.copy2(previous_config/(name+'.env'),CONFIG/(name+'.env'))
        if (ROOT/'current').resolve()!=previous:switch(previous)
        command(['systemctl','restart',*[f'remember-me@{x}' for x in SERVICES]])
        manifest['application_rolled_back']=True;record()
        raise

if __name__=='__main__':main()
