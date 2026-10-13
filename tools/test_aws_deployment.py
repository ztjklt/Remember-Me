"""Deployment boundaries exercised without credentials or AWS resource writes."""
from fnmatch import fnmatchcase
from io import BytesIO
from pathlib import Path
import shlex
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'services/backend'))
from app.storage.s3 import S3ObjectStore


class CfnLoader(yaml.SafeLoader):
    pass


CfnLoader.add_multi_constructor('!', lambda loader, tag, node:
    loader.construct_scalar(node) if isinstance(node, yaml.ScalarNode) else
    loader.construct_sequence(node) if isinstance(node, yaml.SequenceNode) else
    loader.construct_mapping(node))


class PolicyBoundObjects:
    def __init__(self):
        template = yaml.load((ROOT/'infra/aws/pilot.yaml').read_text(), Loader=CfnLoader)
        self.statements = template['Resources']['RuntimeRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
        self.objects = {}

    def check(self, action, key):
        resource = '${Data.Arn}/' + key
        for statement in self.statements:
            patterns = statement['Resource']
            if isinstance(patterns, str):
                patterns = [patterns]
            if (statement['Effect']=='Allow' and action in statement['Action'] and
                    any(fnmatchcase(resource, pattern) for pattern in patterns)):
                return
        raise PermissionError('Deployment role does not allow '+action+' '+key)

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.check('s3:PutObject', Key)
        self.objects[Key] = Body

    def get_object(self, *, Bucket, Key):
        self.check('s3:GetObject', Key)
        return {'Body': BytesIO(self.objects[Key])}

    def delete_object(self, *, Bucket, Key):
        self.check('s3:DeleteObject', Key)
        del self.objects[Key]


def test_actual_storage_readiness_can_write_read_delete_under_role_policy():
    store = S3ObjectStore('fictional-test-bucket')
    store._client = PolicyBoundObjects()
    store.healthcheck()
    assert not store.client.objects
    with pytest.raises(PermissionError):
        store.put('unrelated/private', b'data', 'application/octet-stream')


def test_prewarm_receives_same_environment_file_as_backend():
    script = (ROOT/'infra/aws/activate.sh').read_text(encoding='utf-8').replace('\\\n', ' ')
    command = next(line for line in script.splitlines() if '--unit=remember-me-prewarm' in line)
    assert '--property=EnvironmentFile=/etc/remember-me/api.env' in shlex.split(command)
