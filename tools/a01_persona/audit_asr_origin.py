"""Read-only provider-origin audit; append corrections without rewriting runs."""
from datetime import datetime
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('a01_voice_shared', Path(__file__).with_name('voice_companion_live.py'))
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)


def audit(folder):
    record = shared.read(folder / 'run.json')
    operation = record['operations']['contribution.audio.transcribe']
    start, end = (datetime.fromisoformat(operation[key]) for key in ('started_at', 'finished_at'))
    asr = shared.read(folder / 'asr/contribution.json')
    audit_path = shared.VAR / 'evaluation/asr-paraformer-v1/adapter-state/calls.jsonl'
    import json
    rows = [json.loads(line) for line in audit_path.read_text(encoding='utf8').splitlines()]
    rows = [r for r in rows if r.get('audio_sha256') == asr['audio_sha256']]
    selected = [r for r in rows if start <= datetime.fromisoformat(r['at']) <= end]
    if len(selected) != 1:
        raise ValueError('Expected one matching provider call for this endpoint operation')
    actual = selected[0]
    prior = [r for r in rows if datetime.fromisoformat(r['at']) < start and r.get('task_id') == actual.get('task_id')]
    value = {'audio_sha256': asr['audio_sha256'], 'endpoint_invoked_again': True,
             'actual_paraformer_http_readback': actual.get('http_status') == 200,
             'cloud_task_id': actual['task_id'], 'provider_call_at': actual['at'],
             'same_task_previously_observed_at': [r['at'] for r in prior],
             'new_cloud_recognition_task': False if prior else 'not_established',
             'new_paraformer_call_meaning': 'Another adapter invocation and actual HTTP result fetch, not necessarily a new cloud transcription submission',
             'correction': 'New backend audio/ASR resources; authorized readback of a resumed cloud task, not a fresh recognition job',
             'code_basis': 'Paraformer adapter checkpoint key is SHA256(policy_id + audio_sha256); an existing task_id is polled and its result fetched',
             'audited_at': shared.now()}
    shared.save(folder / 'asr/provider-task-provenance.json', value)
    comparison_path = folder / 'asr/comparison.json'
    if comparison_path.exists():
        comparison = shared.read(comparison_path)
        original = folder / 'asr/comparison.before-provider-audit.json'
        if not original.exists():
            shared.save(original, comparison)
        comparison.update(new_paraformer_call_meaning=value['new_paraformer_call_meaning'],
                          new_cloud_recognition_task=value['new_cloud_recognition_task'],
                          provider_task_id=value['cloud_task_id'],
                          reason='Actual provider task result readback with current source context; not a new recognition task or exact-input model regression')
        shared.save(comparison_path, comparison)
    heading = '\n## ASR 调用口径更正\n'
    report = folder / 'REPORT.md'
    if heading not in report.read_text(encoding='utf8'):
        with report.open('a', encoding='utf8') as output:
            output.write(heading + '\n此前“新 ASR/fresh ASR”的表述过宽。新音频资源和转写端点确实执行，'
                         '但适配器按 policy 与 WAV SHA 恢复了此前同一 Paraformer task，再次通过真实 HTTP 取回其结果。'
                         '不是新云端识别任务，也不构成独立 ASR 重复试验。原始过程记录保留，不清缓存、不补跑。\n\n'
                         '取证见 `asr/provider-task-provenance.json`。\n')
    return value


if __name__ == '__main__':
    for name in ('companion-v3-regression-20261012', 'companion-v4-regression-20261012'):
        result = audit(shared.VAR / name)
        print(name, 'new_cloud_recognition_task=', result['new_cloud_recognition_task'])
