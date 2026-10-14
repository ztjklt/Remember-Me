"""One bounded SSE capability check after batch cooldown, without TTS/retries."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from app.config import Settings
from app.twin import TwinInput
from run_ablation import streamed_selection


async def main(args):
    os.umask(0o077)
    output = Path(args.output)
    if output.exists(): raise RuntimeError('Preserve the previous probe')
    rows = json.loads(Path(args.packets).read_text())
    payload = TwinInput.model_validate(rows[0]['payload'])
    record = {'probe': 'single_capability_call', 'timeout_seconds': 45, 'points_seen': 0}
    async def on_point(result): record['points_seen'] += 1
    try:
        key = Settings(_env_file=args.env).weixin_api_key.get_secret_value()
        result = await streamed_selection(key, payload, on_point, record, 45)
        record.update(status='ok', answer=result.model_dump(mode='json'))
    except Exception as exc:
        record.update(status='failed', error=type(exc).__name__)
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in record.items() if k not in {'answer', 'selection_json'}}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--env', required=True); p.add_argument('--packets', required=True); p.add_argument('--output', required=True)
    asyncio.run(main(p.parse_args()))
