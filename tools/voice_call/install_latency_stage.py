"""Prepare a loopback-only candidate using the already restored voice test DB.

Root on ECS only. Does not change current, production config, nginx or firewall.
"""
from pathlib import Path
import os, subprocess, json
from dotenv import dotenv_values

root=Path('/opt/remember-me/releases/voice-speed-20261014')
stage=Path('/var/lib/remember-me/voice-speed-20261014')
assert os.geteuid()==0
assert not root.exists(), 'Inspect existing candidate; do not overwrite a running release'
root.mkdir();stage.mkdir(mode=0o700,exist_ok=True)
subprocess.run(['tar','-xf',str(stage/'candidate.tar'),'-C',str(root)],check=True)
for service in ['backend','ai-core']:
    old=(Path('/opt/remember-me/current/services')/service/'.venv').resolve()
    target=root/'services'/service/'.venv'
    subprocess.run([str(old/'bin/python'),'-m','venv','--without-pip',str(target)],check=True)
    def site(venv):return subprocess.check_output([str(venv/'bin/python'),'-c','import site;print(site.getsitepackages()[0])'],text=True).strip()
    paths=subprocess.check_output([str(old/'bin/python'),'-c',
        "import sys;print(chr(10).join(p for p in sys.path if p.endswith('site-packages')))"],text=True)
    (Path(site(target))/'remember-existing-runtime.pth').write_text(paths)
for name in ['api','ai']:
    env=dotenv_values('/var/lib/remember-me/voice-stage-20261014/'+name+'.env')
    env.update(REMEMBER_RELEASE_ID='voice-speed-20261014-candidate',
        HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HOME='/var/lib/remember-me/model-cache',
        OMP_NUM_THREADS='2',TOKENIZERS_PARALLELISM='false')
    file=stage/(name+'.env');file.write_text('\n'.join(k+'='+str(v) for k,v in env.items() if v is not None)+'\n');file.chmod(0o600)
print(json.dumps(dict(candidate=str(root),stage=str(stage),production_switched=False)))
