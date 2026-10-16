"""Hash-checked voice latency patch; preserve providers, permissions and data."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import deploy_recording_highlights as releases

releases.SERVICES=['ai','api']

def validate(payload):
    record=json.loads((payload/'deployment.json').read_text())
    candidate=Path(record['candidate'])
    for item in record['files']:assert releases.digest(candidate/item['path'])==item['after']
    suites={'ai-core':[], 'backend':['test_voice_turns','test_voice_sessions','test_voice_optimization',
        'test_voice_prefetch','test_twin_rag_integration','test_rag_contract','test_twin_voice',
        'test_reader_understandings','test_persona_dialogue','test_twin_context','test_retrieval_batching']}
    for service,tests in suites.items():
        with (payload/(service+'-tests.log')).open('w') as out:
            subprocess.run([str(candidate/'.test-venv/bin/python'),'-m','pytest',
                *['tests/'+name+'.py' for name in tests],'-q','--junitxml='+str(payload/(service+'-tests.xml'))],
                cwd=candidate/'services'/service,stdout=out,stderr=out,check=True)
    record['validated']=True
    (payload/'deployment.json').write_text(json.dumps(record,indent=2))
    print('AI and retrieval/voice checks passed against isolated test databases.')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['stage','validate','activate'])
    parser.add_argument('--payload',type=Path,required=True)
    parser.add_argument('--name',default='paired-voice-latency-20261017')
    args=parser.parse_args()
    assert os.geteuid()==0 and args.name.startswith('paired-') and '/' not in args.name
    if args.action=='stage':releases.stage(args.payload.resolve(),args.name)
    elif args.action=='validate':validate(args.payload.resolve())
    else:releases.activate(args.payload.resolve())
