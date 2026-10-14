"""Public API probe with an isolated QA owner and declared synthetic audio only.

Supply an ignored, mode-0600 JSON state {actor_token, subject_id, other_token}.
Never use a production person's account or recording for this engineering probe.
Results include no credentials. Created grants are revoked and originals deleted.
"""
import argparse, hashlib, json, time, wave, uuid
from datetime import datetime, timezone
from pathlib import Path
import httpx

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--origin',required=True);p.add_argument('--private-state',type=Path,required=True)
    p.add_argument('--synthetic-audio',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();state=json.loads(args.private_state.read_text())
    assert state['subject_id'].startswith('speaker_qa_'), 'Dedicated QA Subject required'
    with wave.open(str(args.synthetic_audio)) as wav:
        assert wav.getnchannels()==1
        duration=round(wav.getnframes()/wav.getframerate()*1000)
    data=args.synthetic_audio.read_bytes();grant=None;rid=None;summary={}
    with httpx.Client(base_url=args.origin.rstrip('/'),headers={'Authorization':'Bearer '+state['actor_token']},timeout=100,trust_env=False) as c:
        prefix='/api/v1/subjects/'+state['subject_id']+'/speaker-recordings'
        def expect(response,code):
            assert response.status_code==code, f'HTTP {response.status_code}, expected {code}'
            return response.json()
        caps=expect(c.get(prefix+'/capabilities'),200);assert caps['available'] and caps['identification_scope']=='recording'
        grant=expect(c.post('/api/v1/consents',json={'subject_id':state['subject_id'],'scope':'SPEAKER_IDENTIFICATION','evidence_ref':'synthetic-engineering-qa'}),201)['consent_id']
        try:
            fields={'consent_id':grant,'policy':caps['policy'],'idempotency_key':'synthetic-'+uuid.uuid4().hex,
                'recorded_at':datetime.now(timezone.utc).isoformat(),'duration_ms':duration,'participant_consents_confirmed':'true','speaker_count':2}
            files={'file':('synthetic.wav',data,'audio/wav')}
            row=expect(c.post(prefix,data=fields,files=files),201);rid=row['recording_id']
            assert expect(c.post(prefix,data=fields,files=files),200)['recording_id']==rid
            expect(c.get(prefix+'/'+rid,headers={'Authorization':'Bearer '+state['other_token']}),404)
            for attempt in range(30):
                row=expect(c.post(prefix+'/'+rid+'/process',json={'policy':caps['policy']}),200)
                if row['status']=='ready':break
                assert row['status'] in {'uploaded','analyzing'}, 'Identification failed'
                time.sleep(3)
            assert row['status']=='ready'
            report=row['report'];labels=[s['speaker_name'] for s in report['segments']]
            args.output.with_suffix('.observed.json').write_text(json.dumps({'speaker_labels':labels,'speakers':report['speakers'],'segments':report['segments']},ensure_ascii=False,indent=2)+'\n')
            assert set(labels)=={'小王','小李'} and len(labels)>=6, 'Unexpected synthetic speaker labels'
            for token,name in [('大学校园','小王'),('每次回学校','小李'),('我希望','小王'),('树长高','小李')]:
                rows=[x for x in report['segments'] if token in x['text']]
                assert rows and all(x['speaker_name']==name for x in rows), 'Subsequent statement attributed to wrong speaker'
            audio=c.get(prefix+'/'+rid+'/audio');assert audio.status_code==200 and hashlib.sha256(audio.content).digest()==hashlib.sha256(data).digest()
            expect(c.post('/api/v1/consents/'+grant+'/revoke'),200)
            revoked=expect(c.get(prefix+'/'+rid),200);assert revoked['status']=='revoked' and revoked['report'] is None
            expect(c.get(prefix+'/'+rid+'/audio'),403)
            summary={'synthetic_audio':args.synthetic_audio.name,'audio_sha256':hashlib.sha256(data).hexdigest(),'duration_ms':duration,
                'speaker_labels':labels,'segments':len(labels),'speakers':len(report['speakers']),'idempotent_upload':True,
                'other_owner_hidden':True,'original_checksum_verified':True,'revocation_clears_report_and_blocks_audio':True,
                'identification_scope':'recording','actual_human_accuracy_tested':False}
        finally:
            if rid:
                deleted=expect(c.delete(prefix+'/'+rid),200);assert deleted['status']=='deleted' and deleted['report'] is None and not deleted['error']
                summary['original_cleanup_verified']=True
            if grant:c.post('/api/v1/consents/'+grant+'/revoke').raise_for_status()
    args.output.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
