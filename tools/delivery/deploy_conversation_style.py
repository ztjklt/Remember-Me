"""Hash-checked dialogue prompt release, without config or database changes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import deploy_recording_highlights as releases

releases.SERVICES = ['ai', 'api']


def validate(payload):
    record = json.loads((payload / 'deployment.json').read_text())
    candidate = Path(record['candidate'])
    for item in record['files']:
        assert releases.digest(candidate / item['path']) == item['after']
    suites = {'ai-core': [], 'backend': ['tests/test_voice_turns.py', 'tests/test_voice_sessions.py',
                                         'tests/test_voice_optimization.py', 'tests/test_voice_prefetch.py']}
    for service, tests in suites.items():
        folder = candidate / 'services' / service
        with (payload / (service + '-tests.log')).open('w') as out:
            subprocess.run([str(candidate / '.test-venv/bin/python'), '-m', 'pytest', *tests, '-q',
                '--junitxml=' + str(payload / (service + '-tests.xml'))], cwd=folder,
                stdout=out, stderr=out, check=True)
    record['validated'] = True
    (payload / 'deployment.json').write_text(json.dumps(record, indent=2))
    print('Candidate AI and voice tests passed; no user database accessed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['stage', 'validate', 'activate'])
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--name', default='paired-dialogue-0164-20261016')
    args = parser.parse_args()
    assert os.geteuid() == 0 and args.name.startswith('paired-') and '/' not in args.name
    if args.action == 'stage': releases.stage(args.payload.resolve(), args.name)
    elif args.action == 'validate': validate(args.payload.resolve())
    else: releases.activate(args.payload.resolve())
