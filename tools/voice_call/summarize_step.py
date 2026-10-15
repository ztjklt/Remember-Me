"""Describe all benchmark rows; semantic verdicts are supplied separately by review."""
import argparse
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path


def distribution(values):
    values = sorted(values)
    if not values: return None
    return dict(n=len(values), median_ms=round(statistics.median(values), 3),
                p95_nearest_rank_ms=round(values[math.ceil(len(values)*.95)-1], 3),
                min_ms=round(values[0], 3), max_ms=round(values[-1], 3))


def analyze(rows):
    output = {}
    for name in sorted({r['provider'] for r in rows}):
        group = [r for r in rows if r['provider'] == name]
        success = [r for r in group if r['ok']]
        timings = []; attempts = []
        for row in group:
            for log in row['logs']:
                if log.get('event') in ('step_chat_stream', 'weixin_chat_stream'):
                    attempts.extend(log.get('attempts', [log]))
                    if row['ok']: timings.append(log)
        output[name] = dict(requests=len(group), returned=len(success),
            errors=dict(Counter(r['error'] for r in group if not r['ok'])),
            returned_within_2s=sum(r['ok'] and r['total_ms'] <= 2000 for r in group),
            completed=distribution([r['total_ms'] for r in success]),
            completed_non_unknown=distribution([r['total_ms'] for r in success if r['sample'] != 'unknown']),
            first_content=distribution([l['first_content_ms'] for l in timings if 'first_content_ms' in l]),
            first_point=distribution([l['first_point_ms'] for l in timings if 'first_point_ms' in l]),
            attempts=len(attempts), cancelled_attempts=sum(bool(x.get('cancelled')) for x in attempts),
            attempts_with_reasoning=sum('first_reasoning_ms' in x for x in attempts),
            attempt_headers=distribution([x['transport']['headers_ms'] for x in attempts
                if 'headers_ms' in x.get('transport', {})]),
            per_question={s: dict(n=sum(r['sample']==s for r in group),
                returned=sum(r['sample']==s and r['ok'] for r in group),
                completed=distribution([r['total_ms'] for r in success if r['sample']==s]))
                for s in dict.fromkeys(r['sample'] for r in group)})
    return output


def review_catalog(rows):
    catalog = {}
    for row in rows:
        if not row['ok']: continue
        text = row['answer']['answer']
        key = hashlib.sha256((row['sample']+'\n'+text).encode()).hexdigest()[:12]
        item = catalog.setdefault(key, dict(question=row['question'], sample=row['sample'],
            answer=text, response_type=row['answer']['response_type'], occurrences=[]))
        item['occurrences'].append(dict(provider=row['provider'], repeat=row['repeat']))
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('results'); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    rows = json.loads(Path(args.results).read_text('utf8'))
    result = dict(summary=analyze(rows), review_catalog=review_catalog(rows))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
