import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('audit_platform_sync', Path(__file__).parents[1] / 'audit_platform_sync.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class StaticContractAuditTest(unittest.TestCase):
    def test_resolves_prefix_declared_after_router_without_executing_source(self):
        source = '''
raise RuntimeError('must never execute remote branch code')
router = APIRouter()
PREFIX = '/api/v1/subjects/{subject_id}/twin/voice'
@router.post(PREFIX + '/calls')
async def create(): pass
class CallRequest(BaseModel):
    voice_consent_id: str
'''
        result = audit.inspect_python(source, 'fixture.py')
        self.assertEqual(result['routes'][0]['path'], '/api/v1/subjects/{subject_id}/twin/voice/calls')
        self.assertEqual(result['models']['CallRequest'], {'voice_consent_id': 'str'})

    def test_dynamic_paths_remain_unresolved_not_false_equivalence(self):
        result = audit.inspect_python("router = APIRouter(prefix='/api')\n@router.get(load_path())\ndef route(): pass", 'fixture.py')
        self.assertIsNone(result['routes'][0]['path'])

    def test_different_fields_on_same_route_are_reported(self):
        base = {'routes': [{'method':'POST','path':'/answers'}], 'migrations':[], 'ios_tree':'same'}
        left = dict(base, request_model_declarations={'twin.py:TwinQuestion': {'mode': 'str'}})
        right = dict(base, request_model_declarations={'twin.py:TwinQuestion': {'conversation_mode': 'bool'}})
        diff = audit.compare(left, right)
        self.assertEqual(diff['shared_route_count_not_compatibility'], 1)
        self.assertIn('twin.py:TwinQuestion', diff['changed_request_models'])

    def test_distinct_migration_ids_not_numeric_filename_prefix(self):
        result = audit.inspect_python("revision='0017_evidence_chunks'\ndown_revision='0016_share_invitations'", '0017_evidence.py')
        self.assertEqual(result['migration']['revision'], '0017_evidence_chunks')
        self.assertEqual(result['migration']['down_revision'], '0016_share_invitations')


if __name__ == '__main__': unittest.main()
