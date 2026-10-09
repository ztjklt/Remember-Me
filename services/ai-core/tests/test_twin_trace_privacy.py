import importlib.util
import json
from pathlib import Path


def test_diagnostic_trace_never_records_private_material_or_exception_text(tmp_path,monkeypatch):
    path=Path(__file__).resolve().parents[3]/'tools/round_two/traced_ai.py'
    spec=importlib.util.spec_from_file_location('local_trace',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'OUT',tmp_path)
    secret='未授权的私人录音正文'
    monkeypatch.setattr(module,'original',lambda *args:({'points':[{'text':secret}]},'actual'))
    module.traced(None,'twin-points-v2 '+secret,{'question':secret})
    def fail(*args):raise RuntimeError(secret)
    monkeypatch.setattr(module,'original',fail)
    try:module.traced(None,'twin-points-v2 '+secret,{'question':secret})
    except RuntimeError:pass
    traces=[json.loads(p.read_text(encoding='utf8')) for p in tmp_path.glob('*.json')]
    assert len(traces)==2
    assert secret not in json.dumps(traces,ensure_ascii=False)
    assert all('input' not in t and 'output' not in t and 'system' not in t for t in traces)
    assert {t['status'] for t in traces}=={'returned','failed'}
