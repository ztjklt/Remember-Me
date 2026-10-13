"""Two actual emulators against the isolated local UI corpus, not ECS acceptance.

No model calls. Explicit ordinary fixture accounts; no secrets on command lines.
The ADB reverse links are removed in finally and never described as IP HTTPS.
"""
import json,subprocess
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'services/backend/var/paired-delivery'
ADB='D:/codex_work/remember-me-toolchain/sdk/platform-tools/adb.exe'
DEVICES={'owner':'emulator-5554','reader':'emulator-5556'}

def main():
    config=json.loads((OUT/'sharing-ui.json').read_text('utf8'))
    assert config['url']=='http://127.0.0.1:8892'
    report={'server':config['url'],'devices':DEVICES,'physical_phone':False,'ecs':False,'fresh_asr':False,'phases':[]}
    def save():(OUT/'two-device-local-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    def adb(device,*args):return subprocess.run([ADB,'-s',device,*args],capture_output=True,check=True)
    # Clean only the explicitly designated test pair in an isolated test clone.
    with httpx.Client(base_url=config['url'],trust_env=False,timeout=60) as c:
        p=config['owner'];r=c.post('/api/v1/accounts/login',json={k:p[k] for k in ['username','password']});r.raise_for_status()
        c.headers['Authorization']='Bearer '+r.json()['actor_token'];root='/api/v1/workbench/subjects/'+config['subject']
        try:
            r=c.get(root+'/grants');r.raise_for_status()
            for g in r.json()['items']:
                if g['episode_id']==config['episode'] and g['reader_actor_id']==config['reader']['actor_id'] and not g.get('revoked_at'):
                    c.delete(root+'/grants/'+g['grant_id']).raise_for_status()
        finally:c.post('/api/v1/accounts/logout').raise_for_status()
    try:
        for dev in DEVICES.values():adb(dev,'reverse','tcp:8892','tcp:8892')
        for cycle in range(1,4):
            invite={}
            for role,phase in [('owner','create'),('reader','claim'),('owner','approve'),('reader','play'),('owner','revoke'),('reader','verify_revoked')]:
                device=DEVICES[role]
                cfg={k:config[k] for k in ['url','subject','episode']}
                cfg.update(account=config[role],phase=phase,**invite)
                tmp=OUT/'paired-device-input.json';tmp.write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf8')
                adb(device,'push',str(tmp),'/data/local/tmp/remember-paired-device.json')
                result=adb(device,'shell','am','instrument','-w','-r','-e','class','me.remember.app.PairedDevicesLiveTest','me.remember.app.test/androidx.test.runner.AndroidJUnitRunner')
                name=f'two-device-{cycle}-{phase}';log=(result.stdout+result.stderr).decode('utf8','replace')
                (OUT/(name+'.log')).write_text(log,encoding='utf8')
                if 'OK (1 test)' not in log:raise RuntimeError('Instrumentation failed at '+name)
                remote='/sdcard/Android/data/me.remember.app/files/'
                adb(device,'pull',remote+'paired-device-result.json',str(OUT/(name+'.json')))
                adb(device,'pull',remote+'paired-device.png',str(OUT/(name+'.png')))
                data=json.loads((OUT/(name+'.json')).read_text('utf8'))
                if phase=='create':invite={k:data[k] for k in ['code','invitation_id']}
                report['phases'].append({'cycle':cycle,'device':device,'phase':phase,'passed':True});save()
                print(name,'passed',flush=True)
        report['complete']=True;save()
    except Exception as e:
        report['error']=str(e);save();raise
    finally:
        for dev in DEVICES.values():
            adb(dev,'shell','rm','-f','/data/local/tmp/remember-paired-device.json')
            adb(dev,'reverse','--remove','tcp:8892')

if __name__=='__main__':main()
