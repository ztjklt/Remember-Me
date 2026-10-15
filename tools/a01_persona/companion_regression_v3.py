"""Separate v3 full audio regression. Prepare only until the parent gives --go.

Reuses immutable synthetic WAV bytes, uploads a NEW audio resource, invokes the
actual Paraformer adapter again and confirms the returned ASR unchanged. The
adapter can resume the same cloud task for identical bytes; this does not prove
a new recognition job. No source-TTS regeneration or text-only shortcut.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('a01_voice_shared', Path(__file__).with_name('voice_companion_live.py'))
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
OUT = shared.VAR / 'companion-v3-regression-20261012'
SOURCE = shared.OUT
TRACE = shared.ROOT / 'services/ai-core/var/persona-fictional-traces'
EXPECTED_PROMPT = 'persona-conditional-reviewed-v3'


def fixed_asr_text(actual, note):
    response = actual['actual_response']
    text = response['transcript_text']
    if (not text or not response['raw_transcript_text'] or response['model_version'] != 'bailian/paraformer-v2'
            or actual['technical_confirmation']['text'] != text or note['text'] != text
            or note['classification'] != 'firsthand'):
        raise ValueError('Historical actual ASR provenance mismatch')
    return text


def compare_asr(old, new):
    before = old['actual_response']
    if new['reviewed_text'] != new['transcript_text']:
        raise ValueError('New actual ASR must be confirmed unchanged')
    return {'same_source_wav': True, 'new_paraformer_call': True,
            'new_cloud_recognition_task': 'not_established_by_endpoint_response',
            'raw_equal': before['raw_transcript_text'] == new['raw_transcript_text'],
            'display_equal': before['transcript_text'] == new['transcript_text'],
            'exact_input_regression': False,
            'reason': 'Actual provider result readback and current authorized source context; task freshness requires provider audit'}


def verify_sources(plan):
    for item in plan['source_files']:
        if shared.sha(Path(item['path']).read_bytes()) != item['sha256']:
            raise ValueError('Immutable regression source changed; no live operation sent')


def prepare(path, source=SOURCE, *, expected_prompt=EXPECTED_PROMPT, run_label='companion-full-audio-v3'):
    path, source = Path(path), Path(source)
    historical = shared.read(source / 'run.json')
    old_plan = shared.read(source / 'plan.json')
    asr = shared.read(source / 'asr/contribution.json')
    note = shared.read(source / 'asr/signed-contribution.json')
    old_text = fixed_asr_text(asr, note)
    failure = historical['operations']['companion.answer']
    if (failure['status'] != 'failed' or failure['response']['body']['error_code'] != 'AI_SCHEMA_INVALID'
            or failure['request']['json']['mode'] != 'persona'):
        raise ValueError('Expected original failed persona request')
    original_audio = source / 'materials/companion.wav'
    audio = original_audio.read_bytes()
    metadata = shared.wav_metadata(audio)
    if metadata['audio_sha256'] != asr['audio_sha256']:
        raise ValueError('Historical ASR is not bound to this immutable audio')
    # Freeze copies under a separate output tree without changing the historical run.
    frozen = path.parent / 'input'
    frozen.mkdir(parents=True, exist_ok=True)
    shared.save_audio(frozen / 'companion.wav', audio)
    for name, value in [('old-asr.json', asr), ('old-signed-note.json', note), ('old-failure.json', failure)]:
        target = frozen / name
        if target.exists() and shared.read(target) != value:
            raise ValueError('Frozen original evidence differs; do not overwrite')
        if not target.exists():
            shared.save(target, value)
    sources = [frozen / name for name in ('companion.wav', 'old-asr.json', 'old-signed-note.json', 'old-failure.json')]
    plan = {'schema': 'a01-companion-full-audio-v3-v1', 'run_label': run_label,
            'subject_id': old_plan['subject_id'], 'owner_actor_id': old_plan['owner_actor_id'],
            'reader_actor_id': old_plan['reader_actor_id'], 'state_path': old_plan['state_path'],
            'base_url': shared.BASE, 'source_run_path': str((source / 'run.json').resolve()),
            'source_run_sha256_at_prepare': shared.digest(historical), 'original_question': failure['request']['json'],
            'original_reviewed_text': old_text, 'original_note_id': note['id'], 'original_audio_id': note['audio_id'],
            'reused_audio': metadata | {'path': str((frozen / 'companion.wav').resolve())},
            'old_asr_path': str((frozen / 'old-asr.json').resolve()), 'expected_prompt_version': expected_prompt,
            'source_files': [{'path': str(p.resolve()), 'sha256': shared.sha(p.read_bytes())} for p in sources],
            'provenance': shared.PROVENANCE, 'asr_policy': 'Actual Paraformer task readback; unchanged technical confirmation',
            'comparison_limit': 'Same source WAV and question, but new backend ASR resource and current source context; not exact-input regression'}
    if path.exists() and shared.read(path) != plan:
        raise ValueError('Existing v3 plan differs; preserve prior run')
    shared.save(path, plan)
    return plan


class RegressionRun(shared.Run):
    def actual_asr(self, purpose, role):
        confirmed, audio_root = super().actual_asr(purpose, role)
        comparison = compare_asr(shared.read(self.plan['old_asr_path']), confirmed)
        self.record.data['asr_comparison'] = comparison
        self.record.flush()
        shared.save(self.folder / 'asr/comparison.json', comparison)
        return confirmed, audio_root

    def body(self, name, role, method, path, body=None, **kwargs):
        if name == 'companion.answer':
            body = dict(self.plan['original_question'])
        return super().body(name, role, method, path, body, **kwargs)


def collect_traces(record, previous, expected_prompt=EXPECTED_PROMPT):
    rows = []
    for path in sorted(TRACE.glob('*.json')):
        if path.name in previous:
            continue
        value = shared.read(path)
        if value.get('prompt_version') != expected_prompt or not value.get('fictional_debug_only'):
            continue
        target = record.path.parent / 'traces' / path.name
        shared.save(target, value)
        rows.append({'path': str(target.resolve()), 'trace_id': value.get('trace_id'), 'stage': value.get('stage')})
    record.data['new_fictional_traces'] = rows
    trace_ids = {row['trace_id'] for row in rows}
    log = shared.VAR / 'runtime/ai.log'
    events = []
    if log.exists():
        for line in log.read_text(encoding='utf8', errors='replace').splitlines():
            if not line.startswith('{'):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('trace_id') in trace_ids:
                events.append(event)
    shared.save(record.path.parent / 'traces/events.json', events)
    record.flush()


def write_report(record):
    shared.write_report(record)
    path = record.path.parent / 'REPORT.md'
    lines = ['', '## v3 回归边界', '',
             '复用同一源 WAV、新建音频 ID，重新调用真实 Paraformer，确认稿完全来自本次 ASR。'
             '问题与原失败请求一致，但当前人物理解及授权来源已更新，不是输入完全相同的回归。', '',
             '```json', json.dumps(record.data.get('asr_comparison'), ensure_ascii=False, indent=2), '```', '',
             '本次新增音频、补记、回答与原失败记录互不覆盖。模型拒绝时仍执行撤回并核查两方新原音访问。'
             '未保存答案就没有该答案的 speech/缓存撤回成功证据，不能以旧答案结果替代。', '']
    with path.open('a', encoding='utf8') as output:
        output.write('\n'.join(lines))


def execute(plan, record):
    verify_sources(plan)
    previous_traces = {p.name for p in TRACE.glob('*.json')}
    # The shared companion pipeline expects a material record. This records only
    # reuse of old immutable bytes, not a new provider synthesis or listening pass.
    record.data['operations'].setdefault('materials.companion', {
        'status': 'completed', 'request': {'operation': 'reuse_immutable_WAV', 'source_TTS_calls': 0},
        'result': plan['reused_audio']})
    record.flush()
    try:
        with shared.live_clients(plan) as clients:
            run = RegressionRun(plan, record, clients)
            run.health('v3')
            # Read the current authorized understanding after the owner's new
            # recording/update. Never pass historical candidate IDs to the model.
            narrative = run.body('v3.current_reader_narrative', 'reader', 'GET',
                                 f"/api/v1/workbench/subjects/{plan['subject_id']}/narrative")
            shared.save(record.path.parent / 'current-reader-narrative.json', narrative)
            profile = run.body('v3.reader_voice_profile', 'reader', 'GET', run.root + '/voice/profile')
            if not profile.get('can_synthesize'):
                raise ValueError('Existing reader voice permission unavailable')
            result = run.companion_stage()
            answer = record.data['operations']['companion.answer']['result']['body']
            if answer.get('prompt_version') != EXPECTED_PROMPT:
                raise ValueError('Observed persona prompt does not match v3')
            if result['note_id'] == plan['original_note_id']:
                raise ValueError('Regression must create a new contribution identity')
            new_audio = record.data['operations']['contribution.audio.upload']['result']['body']['audio_id']
            if new_audio == plan['original_audio_id']:
                raise ValueError('Regression must create a new uploaded audio identity')
            return result | {'audio_id': new_audio, 'prompt_version': answer['prompt_version']}
    finally:
        collect_traces(record, previous_traces)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run', 'status', 'report'])
    parser.add_argument('--plan', type=Path, default=OUT / 'plan.json')
    parser.add_argument('--go', action='store_true', help='Only after explicit parent authorization; local writes and real ASR/model calls')
    args = parser.parse_args()
    if args.action == 'run' and not args.go:
        parser.error('Runtime writes/model calls require --go; preparation alone is not authorization')
    if args.action == 'prepare':
        prepare(args.plan)
        print('Independent v3 full audio plan frozen; no runtime requests or credentials loaded')
        return
    plan = shared.read(args.plan)
    if plan['base_url'] != shared.BASE or not args.plan.resolve().is_relative_to(shared.VAR.resolve()):
        raise ValueError('Only ignored local A01 output and approved localhost runtime are accepted')
    record = shared.Checkpoint(args.plan.parent / 'run.json', plan)
    if args.action == 'status':
        print(json.dumps(record.data.get('stages', {}), ensure_ascii=False))
        return
    if args.action == 'report':
        write_report(record)
        return
    with shared.run_lock(args.plan.parent / 'run.lock'):
        row = record.data['stages'].setdefault('companion_v3', {'status': 'started', 'started_at': shared.now()})
        try:
            row.update(result=record.once('v3.full_audio_regression', lambda: execute(plan, record)), status='completed')
        except Exception as exc:
            row.update(status='failed', error_type=type(exc).__name__)
            raise
        finally:
            row['finished_at'] = shared.now()
            record.flush()
            write_report(record)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Stopped (' + type(exc).__name__ + '); preserved v3 checkpoint; no silent retry') from None
