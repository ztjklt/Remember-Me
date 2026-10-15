import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).with_name('clean_display_note.py')


class CleanOpinionSafety(unittest.TestCase):
    def test_run_requires_parent_go(self):
        result = subprocess.run([sys.executable, str(SCRIPT), 'run'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--go', result.stderr)

    def test_text_is_only_the_reviewed_opinion_and_no_attachment(self):
        spec = importlib.util.spec_from_file_location('clean_display', SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        body = mod.create_body({'replacement_text': mod.CLEAN, 'original_note_id': 'old'})
        self.assertEqual(body['text'], mod.CLEAN)
        self.assertEqual(body['classification'], 'opinion')
        self.assertNotIn('audio_id', body)
        for technical in ('ASR', '模型', '授权', '技术样例', '【'):
            self.assertNotIn(technical, body['text'])
        with self.assertRaises(ValueError):
            mod.create_body({'replacement_text': 'changed'})


if __name__ == '__main__':
    unittest.main()
