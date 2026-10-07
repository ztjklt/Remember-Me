"""Run product operations via authenticated APIs; only identity bootstrap uses seed.

Does NOT automatically confirm ASR, share stories, or unlock later corpus days.
Auth tokens are saved in ignored server runtime files, never reported to stdout.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import httpx
from speech_pipeline import CORPUS,OUT,REPO,save,sha

BACKEND=REPO/'services/backend'
AUTH=OUT/'identities.json'
MAPPING=OUT/'product-episodes.json'

def identities(manifest):
    if AUTH.exists():return json.loads(AUTH.read_text(encoding='utf-8'))
    previous=Path.cwd();sys.path.insert(0,str(BACKEND));os.chdir(BACKEND)
    try:
        from app.config import get_settings
        from app.db import Database
        from app.seed import seed_development_data
        db=Database(get_settings().database_url);data={}
        with db.session() as session:
            for person in manifest['people']:
                data[person['id']]={role:asdict(seed_development_data(session,
                    subject_name='虚构月度测试·'+person['name'] if role=='owner' else '测试读者个人空间·'+person['name'],
                    actor_name=('测试记录者·' if role=='owner' else '独立测试读者·')+person['name'])) for role in ['owner','reader']}
        save(AUTH,data);return data
    finally:os.chdir(previous)

def call(method,path,identity,**kwargs):
    response=httpx.request(method,'http://127.0.0.1:8877'+path,
        headers={'Authorization':'Bearer '+identity['actor_token']},trust_env=False,timeout=90,**kwargs)
    if response.status_code>=400:
        try:code=response.json().get('error_code','request_failed')
        except ValueError:code='request_failed'
        raise RuntimeError(f'{method} {path}: HTTP {response.status_code} {code}')
    return response.json()


def check_qa_scope(person_id, protocol, mapping, grants, reader_stories, revisions):
    """Fail before model requests if the local benchmark's visibility setup differs."""
    def ids(field):
        return {mapping[f'{person_id}-{number:02}']['episode_id'] for number in protocol[field]}
    if any(row['status']!='confirmed' for row in revisions):
        raise RuntimeError('Resolve pending/rejected revision cases before monthly QA')
    correction_id=mapping[f'{person_id}-04']['episode_id']
    if not any(r.get('episode_id')==correction_id and r.get('kind')=='correction' for r in revisions):
        raise RuntimeError('Episode04 correction has not been explicitly confirmed; QA not started')
    active={g['episode_id']:g for g in grants if not g.get('revoked_at')}
    required=ids('reader_required_episode_suffixes')
    if not required<=active.keys() or any(not active[i]['cloud_processing_allowed'] for i in required):
        raise RuntimeError('Reader grants do not match the benchmark required stories/cloud scope')
    if ids('reader_private_episode_suffixes') & active.keys():
        raise RuntimeError('Private benchmark stories have active reader grants; QA not started')
    obsolete=ids('reader_unavailable_episode_suffixes')
    if any(s['episode_id'] in obsolete and not s['unavailable'] for s in reader_stories):
        raise RuntimeError('Corrected original is still available to reader; QA not started')

def main():
    ap=argparse.ArgumentParser();group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--ingest-samples',action='store_true');group.add_argument('--approve',metavar='EPISODE')
    group.add_argument('--ingest-episode',metavar='EPISODE')
    group.add_argument('--qa',action='store_true')
    ap.add_argument('--reviewed-file',type=Path)
    ap.add_argument('--relation-target');ap.add_argument('--relation-kind',choices=['supplement','correction','change'])
    ap.add_argument('--time-text');args=ap.parse_args()
    manifest=json.loads((CORPUS/'manifest.json').read_text(encoding='utf-8'))
    auth=identities(manifest);mapping=json.loads(MAPPING.read_text()) if MAPPING.exists() else {}
    if args.ingest_samples or args.ingest_episode:
        for person in manifest['people']:
            ep=person['episodes'][0] if args.ingest_samples else next((e for e in person['episodes'] if e['id']==args.ingest_episode),None)
            if ep is None:continue
            if args.ingest_episode:
                prior=person['episodes'][:person['episodes'].index(ep)]
                if any(e['id'] not in mapping for e in prior):raise SystemExit('Earlier simulated dates must be ingested first')
                if ep['kind'] in {'纠正','同名与补充','时间变化'} and (not args.relation_target or not args.relation_kind):
                    raise SystemExit('Provide actual earlier memory ID and explicit relation kind before transcript review')
                for earlier in prior:
                    status=call('GET','/api/v1/episodes/'+mapping[earlier['id']]['episode_id'],auth[person['id']]['owner'])
                    if status['status']!='ready':raise SystemExit('Earlier recording has not completed actual processing')
            folder=OUT/person['id'];wav=folder/(ep['id']+'.wav')
            if not wav.exists():print(ep['id'],'waiting for generated WAV');continue
            meta=json.loads((folder/(ep['id']+'.json')).read_text(encoding='utf-8'))
            if not meta['duration_pass']:print(ep['id'],'blocked: duration outside180–300seconds');continue
            if sha(wav.read_bytes())!=meta['audio_sha256']:raise RuntimeError('Audio hash mismatch')
            owner=auth[person['id']]['owner']
            if ep['id'] not in mapping:
                result=call('POST','/api/v1/episodes',owner,data={
                    'subject_id':owner['subject_id'],'recording_consent_id':owner['consent_id'],
                    'source':'IMPORT','audio_ref':wav.name,'recorded_at':ep['simulated_recorded_at'],
                    'duration_ms':round(meta['duration_seconds']*1000),'idempotency_key':'monthly:'+meta['audio_sha256'],
                    'metadata':json.dumps({'evaluation_id':ep['id'],'synthetic':True,
                        'generated_at':meta['at'],'tts_model':meta['response_model']})},
                    files={'file':(wav.name,wav.read_bytes(),'audio/wav')})
                mapping[ep['id']]={'episode_id':result['episode_id'],'person':person['id'],'audio_sha256':meta['audio_sha256']}
                save(MAPPING,mapping)
            product_id=mapping[ep['id']]['episode_id']
            if args.relation_target:
                if not args.relation_kind:raise SystemExit('Explicit relation kind is required')
                call('POST',f"/api/v1/workbench/subjects/{owner['subject_id']}/revisions",owner,
                    json={'target_memory_id':args.relation_target,'episode_id':product_id,
                        'kind':args.relation_kind,'time_text':args.time_text})
            start=time.monotonic()
            while time.monotonic()-start<330:
                review=call('GET',f'/api/v1/episodes/{product_id}/transcript-review',owner)
                if review['state']=='reviewing':
                    save(folder/(ep['id']+'.product-asr.json'),{'episode_id':product_id,**review,'review_status':'pending'})
                    print(ep['id'],'persisted original audio; awaiting reviewed text; cloud extraction NOT authorized',flush=True);break
                status=call('GET',f'/api/v1/episodes/{product_id}',owner)
                if status['status']=='failed':raise RuntimeError('Product transcription failed; original remains saved')
                time.sleep(2)
            else:raise RuntimeError('Review wait timeout; original remains saved')
    elif args.approve:
        if not args.reviewed_file or not args.reviewed_file.is_file():raise SystemExit('Provide a separately reviewed text file; author script cannot be used as ASR replacement')
        if CORPUS.resolve() in args.reviewed_file.resolve().parents:raise SystemExit('Author/gold files cannot stand in for reviewed ASR')
        item=mapping[args.approve];owner=auth[item['person']]['owner']
        text=args.reviewed_file.read_text(encoding='utf-8').strip()
        if not text:raise SystemExit('Reviewed text is empty')
        call('PATCH',f"/api/v1/episodes/{item['episode_id']}/transcript-review",owner,json={'transcript':text})
        save(OUT/item['person']/(args.approve+'.reviewed.json'),{'episode_id':item['episode_id'],'text':text,
            'source_file':str(args.reviewed_file.resolve()),'asr_kept_separately':True,'confirmation':'explicit CLI operation'})
        print(args.approve,'review saved and extraction queued; not a success claim')
    elif args.qa:
        expected={ep['id'] for p in manifest['people'] for ep in p['episodes']}
        if not expected<=mapping.keys():raise SystemExit('All30 chronological episodes must be ingested first; monthly QA not started')
        for person in manifest['people']:
            pair=auth[person['id']];subject=pair['owner']['subject_id']
            story_path=f'/api/v1/workbench/subjects/{subject}'
            stories=call('GET',story_path+'/stories',pair['owner'])['items']
            if any(s['status']!='ready' or not s['reviewed'] for s in stories):raise SystemExit('All stories must finish actual reviewed extraction first')
            owner_consents=call('GET','/api/v1/consents?subject_id='+subject,pair['owner'])
            cloud=next((c['consent_id'] for c in owner_consents if c['scope']=='CLOUD_TWIN' and c['status']=='granted'),None)
            if not cloud:raise SystemExit('Enable owner CLOUD_TWIN consent explicitly in workbench first')
            grants=call('GET',story_path+'/grants',pair['reader'])['items']
            reader_cloud=next((g['grant_id'] for g in grants if g['cloud_processing_allowed']),None)
            if not reader_cloud:raise SystemExit('Explicitly authorize selected stories and reader cloud QA first')
            # The local evaluator can inspect gold, but only the question crosses
            # the service boundary. Facts and expected answers are never sent.
            gold=json.loads((CORPUS/'gold'/f"{person['id']}.json").read_text(encoding='utf-8'))
            check_qa_scope(person['id'],gold['qa_protocol'],mapping,grants,
                call('GET',story_path+'/stories',pair['reader'])['items'],
                call('GET',story_path+'/revisions',pair['owner'])['items'])
            checks=gold['qa']
            results=[]
            for check in checks:
                start=time.monotonic()
                result=call('POST',f'/api/v1/subjects/{subject}/twin/answers',pair[check['role']],
                    json={'question':check['question'],'cloud_consent_id':cloud if check['role']=='owner' else reader_cloud})
                results.append({'check_id':check['id'],'role':check['role'],'question':check['question'],
                    'result':result,'elapsed_seconds':time.monotonic()-start,
                    'fact_accuracy':'pending_manual_review','source_support':'pending_manual_review'})
                save(OUT/person['id']/'qa-results.json',results)
                print(check['id'],'API returned; factual and source acceptance pending',flush=True)

if __name__=='__main__':main()
