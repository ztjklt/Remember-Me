"""Reuse the hash-checked staged release / readiness rollback procedure."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import deploy_recording_highlights as releases

releases.SERVICES = ['api', 'worker', 'profile']


def validate(payload):
    record = json.loads((payload / 'deployment.json').read_text())
    candidate = Path(record['candidate'])
    for item in record['files']:
        assert releases.digest(candidate / item['path']) == item['after']
    tests = ['test_automatic_capture_analysis', 'test_worker', 'test_work3200_ingestion',
             'test_profile_material_version', 'test_agent_workbench', 'test_profile_updates',
             'test_profile_batches', 'test_profile_relations', 'test_recording_highlights',
             'test_transcript_correction']
    backend = candidate / 'services/backend'
    with (payload / 'backend-tests.log').open('w') as output:
        subprocess.run([str(backend / '.venv/bin/python'), '-m', 'pytest',
            *[f'tests/{name}.py' for name in tests], '-q',
            '--junitxml=' + str(payload / 'backend-tests.xml')], cwd=backend,
            env={**os.environ, 'PYTHONPATH': str(payload / 'test-support')},
            stdout=output, stderr=output, check=True)
    record['validated'] = True
    (payload / 'deployment.json').write_text(json.dumps(record, indent=2))
    print('Candidate tests passed using isolated test databases.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['stage', 'validate', 'activate'])
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--name', default='paired-auto-capture-20261016')
    args = parser.parse_args()
    assert os.geteuid() == 0 and args.name.startswith('paired-') and '/' not in args.name
    payload = args.payload.resolve()
    if args.action == 'stage': releases.stage(payload, args.name)
    elif args.action == 'validate': validate(payload)
    else: releases.activate(payload)
