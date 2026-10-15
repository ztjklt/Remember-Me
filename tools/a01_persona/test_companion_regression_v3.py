"""Fixed actual-ASR regression preparation; never contacts live services."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('companion_regression_v3.py')


def module():
    spec = importlib.util.spec_from_file_location('companion_regression_v3', SCRIPT)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class FixedInputRegression(unittest.TestCase):
    def test_run_requires_go_before_reading_private_accounts(self):
        result = subprocess.run([sys.executable, str(SCRIPT), 'run'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--go', result.stderr)

    def test_reused_asr_requires_exact_original_reviewed_text(self):
        mod = module()
        actual = {'actual_response': {'raw_transcript_text': '原始辨識。', 'transcript_text': '实际辨识。',
                                     'model_version': 'bailian/paraformer-v2'},
                  'technical_confirmation': {'text': '实际辨识。'}}
        note = {'text': '实际辨识。', 'classification': 'firsthand'}
        self.assertEqual(mod.fixed_asr_text(actual, note), '实际辨识。')
        for altered in ({'text': '创作原稿'}, {'classification': 'opinion'}):
            with self.assertRaises(ValueError):
                mod.fixed_asr_text(actual, note | altered)

    def test_asr_comparison_reports_difference_without_substituting_old_text(self):
        mod = module()
        old = {'actual_response': {'raw_transcript_text': '旧识别', 'transcript_text': '旧识别'}}
        new = {'raw_transcript_text': '新識別', 'transcript_text': '新识别', 'reviewed_text': '新识别'}
        result = mod.compare_asr(old, new)
        self.assertFalse(result['raw_equal'])
        self.assertFalse(result['display_equal'])
        self.assertEqual(new['reviewed_text'], '新识别')
        self.assertFalse(result['exact_input_regression'])

    def test_input_file_change_is_detected_before_live_execution(self):
        mod = module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.json'
            path.write_text('original', encoding='utf8')
            plan = {'source_files': [{'path': str(path), 'sha256': mod.shared.sha(path.read_bytes())}]}
            mod.verify_sources(plan)
            path.write_text('changed', encoding='utf8')
            with self.assertRaises(ValueError):
                mod.verify_sources(plan)

    def test_question_is_original_failed_question_without_historical_trait_ids(self):
        mod = module()
        run = object.__new__(mod.RegressionRun)
        original = {'question': 'original failed question', 'mode': 'persona', 'cloud_consent_id': 'existing'}
        run.plan = {'original_question': original}
        with patch.object(mod.shared.Run, 'body', return_value={}) as call:
            run.body('companion.answer', 'reader', 'POST', '/api/v1/subjects/s/twin/answers', {'question': 'accidental new question'})
        self.assertEqual(call.call_args.args[4], original)
        self.assertNotIn('understanding_ids', call.call_args.args[4])


if __name__ == '__main__':
    unittest.main()
