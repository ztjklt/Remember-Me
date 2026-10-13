"""Real local API audio hashes and reader scope, no model requests or mutations."""
import argparse
import hashlib
import json
from pathlib import Path

import httpx
from product_loop import call
from speech_pipeline import OUT, save


def audit(run):
    pairs = json.loads((run / 'identities.json').read_text(encoding='utf-8'))
    mapping = json.loads((run / 'product-episodes.json').read_text(encoding='utf-8'))
    report = {'human_listening': False, 'audio': [], 'reader_denials': [], 'portraits': {}}
    with httpx.Client(base_url='http://127.0.0.1:8877', trust_env=False, timeout=40) as client:
        for pid, pair in pairs.items():
            root = '/api/v1/workbench/subjects/' + pair['owner']['subject_id']
            for name, item in mapping.items():
                if not name.startswith(pid + '-'): continue
                path = root + '/stories/' + item['episode_id'] + '/audio'
                response = client.get(path, headers={'Authorization': 'Bearer ' + pair['owner']['actor_token']})
                digest = hashlib.sha256(response.content).hexdigest()
                ok = response.status_code == 200 and digest == item['audio_sha256']
                report['audio'].append({'name': name, 'http_status': response.status_code, 'hash_matches': ok})
                if int(name[-2:]) in {1, 4, 7, 10}:
                    denied = client.get(path, headers={'Authorization': 'Bearer ' + pair['reader']['actor_token']})
                    report['reader_denials'].append({'name': name, 'http_status': denied.status_code, 'denied': denied.status_code == 404})
            visible = call('GET', root + '/stories', pair['reader'])['items']
            ids = {s['episode_id'] for s in visible if not s['unavailable']}
            portrait = call('GET', root + '/portrait', pair['reader'])
            used = {item['episode_id'] for items in portrait['views'].values() for item in items}
            report['portraits'][pid] = {'scope': portrait['scope'], 'all_sources_visible': used <= ids,
                                        'visible_story_count': len(ids)}
    save(run / 'audio-and-reader-scope-audit.json', report)
    assert len(report['audio']) == 30 and all(r['hash_matches'] for r in report['audio'])
    assert len(report['reader_denials']) == 12 and all(r['denied'] for r in report['reader_denials'])
    assert all(r['scope'] == 'shared_stories_only' and r['all_sources_visible'] for r in report['portraits'].values())
    print('30 original audio hashes match; 12 private/obsolete reader audio requests denied; 3 reader portraits scoped.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not args.run.replace('-', '').isalnum(): raise SystemExit('Invalid run')
    audit(OUT / 'cloud-asr-runs' / args.run)
