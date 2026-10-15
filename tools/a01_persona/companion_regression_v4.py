"""One audio regression with an explicit saved-text review before speech.

The process waits up to 120 seconds for the development assistant to inspect the
actual saved answer and write a hash-bound review. Reject/timeout still withdraws
the temporary contribution. There is no second model attempt.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import time

spec = importlib.util.spec_from_file_location('a01_companion_v3_shared', Path(__file__).with_name('companion_regression_v3.py'))
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
shared = prior.shared
VERSION = 'v4'
OUT = shared.VAR / 'companion-v4-regression-20261012'
EXPECTED_PROMPT = 'persona-conditional-reviewed-v4'


def validate_review(review, answer):
    if (review.get('approved') is not True or review.get('reviewer') != 'development_assistant'
            or review.get('answer_sha256') != shared.digest(answer)
            or not isinstance(review.get('reason'), str) or not review['reason'].strip()):
        raise ValueError('Exact saved answer is not approved for synthesis')


class ReviewedRun(prior.RegressionRun):
    def speech(self, name, role, answer):
        if answer.get('prompt_version') != EXPECTED_PROMPT:
            raise ValueError('Saved answer is not from the expected versioned prompt')
        pending = {'answer': answer, 'answer_sha256': shared.digest(answer),
                   'actual_asr_path': str((self.folder / 'asr/contribution.json').resolve()),
                   'signed_note_path': str((self.folder / 'asr/signed-contribution.json').resolve()),
                   'reviewer': 'development_assistant', 'status': 'awaiting_text_review_not_listening',
                   'started_at': shared.now()}
        shared.save(self.folder / 'pending-semantic-review.json', pending)
        print('Saved ' + VERSION + ' answer awaiting development-assistant text review before speech', flush=True)

        def review_once():
            deadline = time.monotonic() + 120
            path = self.folder / 'semantic-review.json'
            while not path.exists() and time.monotonic() < deadline:
                time.sleep(0.25)
            if not path.exists():
                raise ValueError('Text review deadline; withdraw without synthesis')
            review = shared.read(path)
            validate_review(review, answer)
            return review

        self.record.once(VERSION + '.semantic_review', review_once, {'answer_sha256': shared.digest(answer)})
        return super().speech(name, role, answer)


def execute(plan, record):
    prior.verify_sources(plan)
    previous_traces = {path.name for path in prior.TRACE.glob('*.json')}
    record.data['operations'].setdefault('materials.companion', {
        'status': 'completed', 'request': {'operation': 'reuse_immutable_WAV', 'source_TTS_calls': 0},
        'result': plan['reused_audio']})
    record.flush()
    try:
        with shared.live_clients(plan) as clients:
            run = ReviewedRun(plan, record, clients)
            run.health(VERSION)
            narrative = run.body(VERSION + '.current_reader_narrative', 'reader', 'GET',
                                 f"/api/v1/workbench/subjects/{plan['subject_id']}/narrative")
            shared.save(record.path.parent / 'current-reader-narrative.json', narrative)
            profile = run.body(VERSION + '.reader_voice_profile', 'reader', 'GET', run.root + '/voice/profile')
            if not profile.get('can_synthesize'):
                raise ValueError('Existing reader voice permission unavailable')
            result = run.companion_stage()
            answer = record.data['operations']['companion.answer']['result']['body']
            new_audio = record.data['operations']['contribution.audio.upload']['result']['body']['audio_id']
            if (result['note_id'] == plan['original_note_id'] or new_audio == plan['original_audio_id']
                    or answer.get('prompt_version') != EXPECTED_PROMPT):
                raise ValueError('Separate versioned resource/prompt boundary failed')
            return result | {'audio_id': new_audio, 'prompt_version': answer['prompt_version']}
    finally:
        prior.collect_traces(record, previous_traces, EXPECTED_PROMPT)


def report(record):
    shared.write_report(record)
    with (record.path.parent / 'REPORT.md').open('a', encoding='utf8') as output:
        output.write('\n## ' + VERSION + ' 单次回归\n\n同一源WAV及原问题，新上传并授权取回实际Paraformer结果；'
                     '相同WAV可能恢复已有云端task，不能声称新识别提交。当前授权来源也已变化，不是完全相同输入回归。'
                     '声音生成前由本轮开发助手查看实际答案、ASR及归属，不代表真人听音或独立盲评。\n\n```json\n' +
                     json.dumps(record.data.get('asr_comparison'), ensure_ascii=False, indent=2) + '\n```\n')
        path = record.path.parent / 'semantic-review.json'
        if path.exists():
            output.write('\n文本检查记录：\n\n```json\n' + json.dumps(shared.read(path), ensure_ascii=False, indent=2) + '\n```\n')
    if (record.path.parent / 'asr/contribution.json').exists():
        audit_spec = importlib.util.spec_from_file_location('asr_task_audit', Path(__file__).with_name('audit_asr_origin.py'))
        auditor = importlib.util.module_from_spec(audit_spec)
        audit_spec.loader.exec_module(auditor)
        auditor.audit(record.path.parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run', 'status', 'report'])
    parser.add_argument('--go', action='store_true')
    args = parser.parse_args()
    if args.action == 'run' and not args.go:
        parser.error('One actual ' + VERSION + ' attempt requires explicit parent --go')
    path = OUT / 'plan.json'
    if args.action == 'prepare':
        prior.prepare(path, expected_prompt=EXPECTED_PROMPT, run_label='companion-full-audio-' + VERSION)
        print('Separate ' + VERSION + ' plan prepared offline')
        return
    plan = shared.read(path)
    record = shared.Checkpoint(OUT / 'run.json', plan)
    if args.action == 'status':
        print(json.dumps(record.data['stages'], ensure_ascii=False))
        return
    if args.action == 'report':
        report(record)
        return
    if plan['base_url'] != shared.BASE:
        raise ValueError('Only fixed local runtime allowed')
    with shared.run_lock(OUT / 'run.lock'):
        row = record.data['stages'].setdefault('companion_' + VERSION, {'status': 'started', 'started_at': shared.now()})
        try:
            row.update(result=record.once(VERSION + '.full_audio_regression', lambda: execute(plan, record)), status='completed')
        except Exception as exc:
            row.update(status='failed', error_type=type(exc).__name__)
            raise
        finally:
            row['finished_at'] = shared.now()
            record.flush()
            report(record)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Stopped (' + type(exc).__name__ + '); preserved v4 checkpoint; no second attempt') from None
