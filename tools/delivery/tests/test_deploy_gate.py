import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('deploy_gate', Path(__file__).parents[1] / 'deploy_twin_candidate.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SmokeGateTest(unittest.TestCase):
    def test_proofreading_is_explicit_and_preserves_other_capabilities(self):
        for service in module.SERVICES:
            normal = module.release_updates(service, 'commit')
            enabled = module.release_updates(service, 'commit', True)
            self.assertNotIn('REMEMBER_TRANSCRIPT_CORRECTION_ENABLED', normal)
            self.assertEqual(enabled.get('REMEMBER_TRANSCRIPT_CORRECTION_ENABLED'),
                             'true' if service in ('api', 'worker') else None)
            self.assertEqual(enabled['REMEMBER_RELEASE_ID'], 'commit')
            self.assertFalse(any('KEY' in key or 'REGISTRATION' in key or 'VOICE' in key
                                 for key in enabled))

    def setUp(self):
        clause = '第一次独立开12路是1987年，不是1986年。'
        answer = {'mode': 'evidence', 'stale': False, 'model_version': 'Deepseek-v4-flash',
                  'answer_id': 'test-answer', 'source_version': 'test-source',
                  'response_type': 'SIMULATION', 'answer': '核对文字：“' + clause + '”',
                  'question': '第一次独立跑十二路是哪一年？',
                  'evidence': [{'evidence_id': 'test-evidence', 'episode_id': 'test-episode', 'excerpt': clause}]}
        self.smoke = {'service_info': {'release_id': 'test-commit'},
                      'evidence': answer, 'persona': {**copy.deepcopy(answer), 'mode': 'persona'}}

    def test_supported_multi_quote_synthesis_is_not_a_false_failure(self):
        module.validate_smoke(self.smoke, 'test-commit')

    def test_original_label_also_passes(self):
        self.smoke['evidence']['response_type'] = 'ORIGINAL'
        module.validate_smoke(self.smoke, 'test-commit')

    def test_rejects_wrong_or_unsupported_current_fact(self):
        for target in ['answer', 'excerpt']:
            probe = copy.deepcopy(self.smoke)
            if target == 'answer':
                probe['evidence']['answer'] = '第一次独立开12路是1986年。'
            else:
                probe['evidence']['evidence'][0]['excerpt'] = '没有年份'
            with self.subTest(target=target), self.assertRaises(AssertionError):
                module.validate_smoke(probe, 'test-commit')

    def test_rejects_stale_unknown_missing_source_or_other_model(self):
        for role in ['persona', 'evidence']:
            for key, value in [('stale', True), ('response_type', 'UNKNOWN'), ('evidence', []),
                               ('source_version', ''), ('model_version', 'different-model')]:
                probe = copy.deepcopy(self.smoke)
                probe[role][key] = value
                with self.subTest(role=role, key=key), self.assertRaises(AssertionError):
                    module.validate_smoke(probe, 'test-commit')

    def test_rejects_another_release(self):
        with self.assertRaises(AssertionError):
            module.validate_smoke(self.smoke, 'different-commit')


if __name__ == '__main__':
    unittest.main()
