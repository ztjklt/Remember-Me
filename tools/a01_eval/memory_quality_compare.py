"""Paired extraction on frozen fictional ASR and unseen boundary cases.

Run with the AI Core virtualenv. No production database is touched. The baseline
is the pre-change source snapshot, not cherry-picked historical model outputs.
"""
import hashlib
import importlib.util
import json
import logging
import sys
from pathlib import Path
from time import perf_counter
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'services/ai-core'))
from dotenv import dotenv_values
from app.providers.weixin import WeixinProvider, MODEL
from app.contracts import AICoreInput
from app.extractor import MemoryExtractor


def main():
    out = ROOT / 'services/backend/var/memory-quality-20261015/comparison'
    out.mkdir(parents=True, exist_ok=True)
    baseline = out.parent / 'before/weixin.py'
    spec = importlib.util.spec_from_file_location('app.providers.memory_baseline', baseline)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    key = dotenv_values(ROOT.parents[3] / 'services/ai-core/.env').get('WEIXIN_CHAT_API_KEY')
    if not key:
        raise SystemExit('Existing Weixin credential unavailable')
    cases = []
    for identifier in ('A01_02','A01_06','A01_07','A01_08'):
        source = ROOT / f'services/backend/var/a01-20261012/evaluation/asr-paraformer-v1/{identifier}.raw-asr.json'
        record = json.loads(source.read_text(encoding='utf-8'))
        cases.append(dict(id=identifier, text=record['text'], input_type='historical_actual_ASR_unchanged'))
    cases.extend([
        dict(id='boundary_01', input_type='new_authored_fictional_text_not_audio',
             text='周阿姨说老张天天喜欢去公园。我只见过他上周二去过一次。至于他平常爱不爱去，我不知道。那天他是陪孙女，不是去晨练。'),
        dict(id='boundary_02', input_type='new_authored_fictional_text_not_audio',
             text='以前出门，我总是自己骑车。去年摔了一跤以后，下雨时我就让孩子来接。天晴、路近，我仍然自己骑。我没说以后都不骑了。')])
    manifest = {'started_at':datetime.now(timezone.utc).isoformat(), 'cases':cases,
        'baseline_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),
        'candidate_sha256':hashlib.sha256((ROOT/'services/ai-core/app/providers/weixin.py').read_bytes()).hexdigest(),
        'model':MODEL,'retries':0,'attempts':[]}
    providers = {'baseline':old.WeixinProvider(api_key=key), 'candidate':WeixinProvider(api_key=key)}
    logging.getLogger('remember_me.ai_core').disabled = True
    try:
        for index, case in enumerate(cases):
            for arm in (('baseline','candidate') if index % 2 == 0 else ('candidate','baseline')):
                provider = providers[arm]
                result = dict(case_id=case['id'], arm=arm, input_type=case['input_type'],
                    transcript=case['text'], input_sha256=hashlib.sha256(case['text'].encode()).hexdigest(),
                    prompt_version=provider.prompt_version)
                started = perf_counter()
                try:
                    output = MemoryExtractor(provider=provider,model=MODEL,model_version=MODEL).process(
                        AICoreInput(episode_id=case['id'],subject_id='fictional-quality-audit',
                            transcript=case['text'],existing_model_version='v1'))
                    result.update(status='ok',output=output.model_dump(mode='json'))
                except Exception as exc:
                    result.update(status='failed', error_type=type(exc).__name__)
                result['duration_seconds']=round(perf_counter()-started,3)
                (out/f"{case['id']}.{arm}.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                manifest['attempts'].append({k:v for k,v in result.items() if k not in {'transcript','output'}})
                (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
                print(case['id'],arm,result['status'],result['duration_seconds'],flush=True)
    finally:
        for provider in providers.values():provider.close()


if __name__ == '__main__':main()
