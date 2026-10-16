"""Three synthetic, storage-free requests through the existing DeepSeek adapter.

Run with the AI Core virtualenv. Reads a server-local env file without exporting
credentials. Does not call Backend, read user memory, synthesize speech or persist
an Episode. The output is model evidence for human review, not a quality score.
"""
import argparse
import json
from pathlib import Path
import sys
from contextlib import nullcontext
from time import monotonic


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--transport', choices=['voice','direct'], default='voice')
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Use a new output path to retain every attempt.')
    sys.path.insert(0, str(args.source.resolve()))
    from app.config import Settings
    from app.persona import PersonaInput, PersonaProvider
    from app.providers.weixin import WeixinChat

    settings = Settings(_env_file=args.env_file)
    chat = WeixinChat(api_key=settings.weixin_api_key.get_secret_value())
    basis = dict(voice_response=True, candidates=[dict(memory_item_id='fictional-memory',
        statement='虚构联调样本', traits=[], evidence=[
            dict(evidence_id='sample-1', excerpt='平常遇到临时安排，我会先问清楚，再决定。', source_type='SUBJECT'),
            dict(evidence_id='sample-2', excerpt='如果家里有急事，我也会先去处理。', source_type='SUBJECT')])],
        understandings=[dict(id='sample-understanding', statement='平常倾向先问清临时安排，但家庭急事可能优先。',
            context='普通临时安排；家庭急事是例外。', evidence_ids=['sample-1'], counter_evidence_ids=['sample-2'])],
        examples=[], contributions=[])
    cases = [
        ('ordinary', '临时来了一个安排，我一般会怎么处理？', []),
        ('followup', '那如果家里突然有急事呢？', [dict(question='临时来了一个安排，我一般会怎么处理？',
            heard_answer='平常我大概会先问清楚，再决定。', interrupted=False)]),
        ('unknown', '我第一次参加这种活动是哪一年？', []),
    ]
    report = dict(scope='synthetic material only; no user records or TTS', transport=args.transport,cases=[])
    try:
        for name, question, history in cases:
            entry = dict(case=name, question=question, status='started')
            report['cases'].append(entry)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            start = monotonic()
            try:
                with (chat.transport_scope(timeout_seconds=settings.voice_call_timeout_seconds,
                        json_retry_after_seconds=settings.effective_voice_json_retry_after_seconds)
                      if args.transport=='voice' else nullcontext()):
                    result = PersonaProvider(chat).answer(PersonaInput.model_validate(
                        dict(basis, question=question, dialogue_context=history)))
                entry.update(status='completed', result=result.model_dump(mode='json'))
            except Exception as exc:
                entry.update(status='failed', error_type=type(exc).__name__)
            entry['elapsed_seconds'] = round(monotonic() - start, 2)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(dict(case=name, status=entry['status']), ensure_ascii=False), flush=True)
    finally:
        chat.close()


if __name__ == '__main__':
    main()
