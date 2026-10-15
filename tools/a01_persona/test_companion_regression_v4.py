import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).with_name('companion_regression_v4.py')


def module():
    spec = importlib.util.spec_from_file_location('companion_v4', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SemanticGate(unittest.TestCase):
    def test_run_requires_explicit_go(self):
        response = subprocess.run([sys.executable, str(SCRIPT), 'run'], capture_output=True, text=True)
        self.assertNotEqual(response.returncode, 0)
        self.assertIn('--go', response.stderr)

    def test_speech_requires_review_of_exact_saved_answer(self):
        mod = module()
        answer = {'answer_id': 'saved', 'answer': '具名的单次观察', 'contribution_ids': ['note']}
        valid = {'approved': True, 'reviewer': 'development_assistant',
                 'answer_sha256': mod.shared.digest(answer), 'reason': 'Checked against actual ASR; ambiguous action not asserted'}
        mod.validate_review(valid, answer)
        for invalid in ({'approved': False}, {'answer_sha256': 'different'}, {'reason': ''}):
            with self.assertRaises(ValueError):
                mod.validate_review(valid | invalid, answer)


if __name__ == '__main__':
    unittest.main()
