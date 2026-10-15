"""Bounded, credential-redacted Step capability probe; no production changes."""
import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values


async def main(args):
    key = dotenv_values(args.env)['STEP_API_KEY']
    result = {'model': 'step-3.5-flash-2603', 'reasoning_effort': 'low'}
    headers = {'Authorization': 'Bearer ' + key}
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
        async with asyncio.timeout(15):
            response = await client.get('https://api.stepfun.com/v1/models', headers=headers)
        result['models_status'] = response.status_code
        try:
            data = response.json()
            result['models'] = [m['id'] for m in data.get('data', [])]
            if not response.is_success:
                error = data.get('error', {})
                result['error'] = {k: str(error.get(k, ''))[:400].replace(key, '[redacted]')
                                   for k in ('code', 'type', 'message')}
        except (ValueError, TypeError):
            result['error'] = 'Non-JSON model listing'
        if response.is_success:
            body = {'model': result['model'], 'reasoning_effort': 'low', 'stream': True,
                    'max_tokens': 2048, 'response_format': {'type': 'json_object'},
                    'messages': [{'role': 'system', 'content': '只输出JSON对象。'},
                                 {'role': 'user', 'content': '回答格式为 {"ready":true}。'}]}
            start = time.perf_counter()
            text = ''; reason_chars = 0; done = False
            async with asyncio.timeout(25):
                async with client.stream('POST', 'https://api.stepfun.com/v1/chat/completions',
                                         headers=headers, json=body) as response:
                    result['chat_status'] = response.status_code
                    result['headers_ms'] = round((time.perf_counter() - start) * 1000, 3)
                    if not response.is_success:
                        error = json.loads(await response.aread()).get('error', {})
                        result['chat_error'] = {k: str(error.get(k, ''))[:400].replace(key, '[redacted]')
                                                for k in ('code', 'type', 'message')}
                    else:
                        async for line in response.aiter_lines():
                            if not line.startswith('data:'): continue
                            raw = line[5:].strip()
                            if raw == '[DONE]': done = True; continue
                            event = json.loads(raw)
                            if event.get('usage'): result['usage'] = event['usage']
                            if event.get('model'): result['response_model'] = event['model']
                            for choice in event.get('choices', []):
                                delta = choice.get('delta') or {}
                                reasoning = delta.get('reasoning_content') or delta.get('reasoning')
                                if reasoning:
                                    result.setdefault('first_reasoning_ms', round((time.perf_counter()-start)*1000, 3))
                                    reason_chars += len(reasoning)
                                if delta.get('content'):
                                    result.setdefault('first_content_ms', round((time.perf_counter()-start)*1000, 3))
                                    text += delta['content']
                                if choice.get('finish_reason'): result['finish_reason'] = choice['finish_reason']
            result.update(total_ms=round((time.perf_counter()-start)*1000, 3),
                          content=text, reasoning_chars=reason_chars, done=done)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--env', required=True)
    parser.add_argument('--output', required=True)
    asyncio.run(main(parser.parse_args()))
