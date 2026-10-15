import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.a01_eval import run_baseline as runner

class SafetyTests(unittest.TestCase):
    def test_started_checkpoint_does_not_make_duplicate_call(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)
            runner.save(out/'tasks/probe.json',{'status':'started','id':'probe'})
            with patch.object(runner,'OUT',out), self.assertRaisesRegex(RuntimeError,'Uncertain prior'):
                runner.checkpoint_task('probe',lambda:self.fail('Must not call provider'))

    def test_failure_checkpoint_is_not_retried_on_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(runner,'OUT',Path(folder)):
                calls=[]
                def fail():
                    calls.append(1)
                    raise runner.AIOutputInvalid('Malformed output')
                first=runner.checkpoint_task('probe',fail)
                second=runner.checkpoint_task('probe',fail)
                self.assertEqual(first,second)
                self.assertEqual(calls,[1])

    def test_every_recorded_payload_excludes_hidden_truth(self):
        forbidden=['1950','2024','测试真值档案','参考：','测试验收题']
        for path in (runner.OUT/'calls').glob('*.json'):
            row=json.loads(path.read_text(encoding='utf-8'))
            payload=json.dumps(row['payload'],ensure_ascii=False)
            for token in forbidden:
                self.assertNotIn(token,payload,path.name)
            self.assertEqual(row['endpoint'],'https://chatapi.weixin.qq.com/openai/v1/chat/completions')
            self.assertEqual(row['requested_model'],'Deepseek-v4-flash')
            self.assertEqual(row['attempt'],1)

if __name__=='__main__':unittest.main()
