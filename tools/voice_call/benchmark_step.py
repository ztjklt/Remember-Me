"""Interleaved Step low vs deployed Weixin voice path on frozen authorized packets.

Run with the deployed AI Core on PYTHONPATH; import only the experimental Step
adapter by path. Does not modify service files, model defaults, or memory data.
"""
import argparse
import hashlib
import importlib.util
import inspect
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from app.providers.weixin import WeixinChat
from app.quoted_twin import QuotedTwin, VOICE_SYSTEM
from app.twin import TwinInput
from app.voice_stream import generation_streamed, semantic_review_required


def main(args):
    spec = importlib.util.spec_from_file_location('app.providers.step_candidate', args.adapter)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    samples = json.loads(Path(args.packets).read_text('utf8'))
    output = Path(args.output); output.mkdir(parents=True, exist_ok=False)
    manifest = dict(started_utc=datetime.now(timezone.utc).isoformat(), rounds=args.rounds,
        interval_seconds=args.interval, shared_deadline_seconds=args.deadline, retry_at_seconds=args.retry_after,
        policy='Shared deadline; serial requests; identical authorized materials; no semantic review',
        step_model='step-3.5-flash-2603', reasoning_effort='low', step_max_tokens=2048,
        weixin_model='Deepseek-v4-flash', weixin_max_tokens='provider default (unchanged)',
        packets_sha256=hashlib.sha256(Path(args.packets).read_bytes()).hexdigest(),
        quoted_twin_file=inspect.getfile(QuotedTwin),
        quoted_twin_sha256=hashlib.sha256(Path(inspect.getfile(QuotedTwin)).read_bytes()).hexdigest(),
        prompt_sha256=hashlib.sha256(VOICE_SYSTEM.encode()).hexdigest(),
        adapter_sha256=hashlib.sha256(Path(args.adapter).read_bytes()).hexdigest(),
        semantic_review=False, production_changed=False)
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2), 'utf8')
    providers = {'weixin': WeixinChat(api_key=dotenv_values(args.weixin_env)['WEIXIN_CHAT_API_KEY']),
                 'step': module.StepVoiceChat(api_key=dotenv_values(args.step_env)['STEP_API_KEY'])}
    twins = {k: QuotedTwin(v) for k, v in providers.items()}
    rows = []; logs = []
    class Recorder(logging.Handler):
        def emit(self, record):
            try: logs.append(json.loads(record.getMessage()))
            except ValueError: pass
    logger = logging.getLogger('remember_me.ai_core')
    old_handlers, old_propagate = logger.handlers[:], logger.propagate
    logger.handlers = [Recorder()]; logger.propagate = False
    stream = generation_streamed.set(True); review = semantic_review_required.set(False)
    try:
        for repeat in range(args.rounds):
            for index, sample in enumerate(samples):
                order = ['weixin', 'step'] if (repeat+index)%2 == 0 else ['step', 'weixin']
                order = [name for name in order if name in args.providers.split(',')]
                for name in order:
                    logs.clear(); began = time.perf_counter()
                    row = dict(repeat=repeat+1, sample=sample['id'], question=sample['payload']['question'],
                               provider=name, started_utc=datetime.now(timezone.utc).isoformat(), ok=False)
                    try:
                        with providers[name].transport_scope(timeout_seconds=args.deadline, retry_after_seconds=args.retry_after):
                            answer = twins[name].answer(TwinInput.model_validate(sample['payload']))
                        row.update(ok=True, answer=answer.model_dump())
                    except Exception as error: row['error'] = type(error).__name__
                    row.update(total_ms=round((time.perf_counter()-began)*1000, 3), logs=list(logs))
                    rows.append(row)
                    (output/'results.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), 'utf8')
                    print(json.dumps({k: v for k, v in row.items() if k not in ('question', 'answer', 'logs')}), flush=True)
                    if row.get('error') in ('ProviderAuthenticationFailed', 'ProviderRateLimited'):
                        # A quota/auth failure is observable, not silently retried or dropped.
                        return
                    time.sleep(args.interval)
    finally:
        generation_streamed.reset(stream); semantic_review_required.reset(review)
        for provider in providers.values(): provider.close()
        logger.handlers = old_handlers; logger.propagate = old_propagate
        manifest.update(finished_utc=datetime.now(timezone.utc).isoformat(),
                        completed_requests=len(rows), expected_requests=len(samples)*args.rounds*len(args.providers.split(',')))
        (output/'manifest.json').write_text(json.dumps(manifest, indent=2), 'utf8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('packets', 'output', 'adapter', 'step-env'): parser.add_argument('--'+name, required=True)
    parser.add_argument('--weixin-env', default='/etc/remember-me/ai.env')
    parser.add_argument('--rounds', type=int, default=5)
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--deadline', type=float, default=8)
    parser.add_argument('--retry-after', type=float, default=3)
    parser.add_argument('--providers', choices=['weixin,step', 'step', 'weixin'], default='weixin,step')
    main(parser.parse_args())
