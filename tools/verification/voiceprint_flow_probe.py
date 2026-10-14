"""Declared synthetic-only public recognition, memory and entrusted-range proof.

Credentials stay in ignored mode-0600 files. Never run on a person's Subject.
"""
import argparse,io,json,time,uuid,wave,sys,hashlib
from pathlib import Path
import httpx

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['origin','private-state','private-config','audio','segments','report']:p.add_argument('--'+name,required=True)
    args=p.parse_args();state=json.loads(Path(args.private_state).read_text());cfg=json.loads(Path(args.private_config).read_text())
    env=json.loads(cfg['ServerConfig']['EnvParams']);subject=state['subject_id'];assert subject.startswith('speaker_qa_')
    worker_secret=env['REMEMBER_REALTIME_WORKER_SECRET'];run=uuid.uuid4().hex
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'services/backend'))
    from app.voiceprints import pcm
    raw=pcm(Path(args.audio).read_bytes(),'audio/wav')
    rows=json.loads(Path(args.segments).read_text())['segments']
    def clip(segments):
        pcm=b''.join(raw[s['start_ms']*32:s['end_ms']*32] for s in segments);buf=io.BytesIO()
        with wave.open(buf,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(pcm)
        return buf.getvalue()
    own=[s for s in rows if s['speaker_name']=='小王'];guest=[s for s in rows if s['speaker_name']=='小李']
    intro=clip(own[:2]);story=clip([next(s for s in own if '大学校园' in s['text'])]);second=clip([next(s for s in own if '我希望' in s['text'])]);guest_intro=clip(guest[:2]);secret_audio=clip([next(s for s in guest if '每次回学校' in s['text'])])
    synthetic_secret=next(s['text'] for s in guest if '每次回学校' in s['text'])
    grants=[];calls=[];plans=[];answers=[];visit_headers=[];report={'synthetic_only':True,'human_accuracy_tested':False};legacy_created=False
    sys.path.insert(0,'/Users/jitian/.codex/worktrees/livekit-twin/Remember Me/build/private')
    from control import invoke
    def sql(name,statement):return invoke('voiceprint-probe-'+name,['db','execute','-e','remember-me-ios-d5f9twwlcae71c69','--sql',statement,'--json'])
    def expect(r,code=200):assert r.status_code==code, f'HTTP {r.status_code}, expected {code}: '+r.text[:300];return r.json()
    def wait(check,timeout=300):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            value=check()
            if value:return value
            # Exercise the same durable processing route without waiting for
            # the deployment's minute-based timer between every test stage.
            with httpx.Client(timeout=90,trust_env=False) as processing:
                tick=processing.post(args.origin+'/internal/jobs/processing-tick',headers={'Authorization':'Bearer '+env['CLOUDBASE_WORKER_TOKEN']})
                assert tick.status_code in (200,409), 'Processing tick unavailable'
            time.sleep(2)
        raise AssertionError('Synthetic verification timed out')
    with httpx.Client(base_url=args.origin,headers={'Authorization':'Bearer '+state['actor_token']},timeout=100,trust_env=False) as c,httpx.Client(base_url=args.origin,headers={'Authorization':'Bearer '+state['other_token']},timeout=100,trust_env=False) as visitor,httpx.Client(base_url=args.origin,headers={'Authorization':'Bearer '+worker_secret},timeout=100,trust_env=False) as w:
        prefix='/api/v1/subjects/'+subject
        def grant(scope):
            identifier=expect(c.post('/api/v1/consents',json={'subject_id':subject,'scope':scope,'evidence_ref':'declared-synthetic-voiceprint-qa'}),201)['consent_id'];grants.append(identifier);return identifier
        def utterance(call,turn,data,text):
            result=expect(w.post('/internal/voice-calls/'+call+'/answers',json={'turn_id':turn,'question':text}));answers.append(result['answer_id'])
            expect(w.post('/internal/voice-calls/'+call+'/utterances',data={'turn_id':turn},files={'sample':('synthetic.wav',data,'audio/wav')}))
            expect(w.post('/internal/voice-calls/'+call+'/turn-complete',json={'turn_id':turn}))
            return wait(lambda:(r if (r:=expect(w.get('/internal/voice-calls/'+call+'/utterances/'+turn)))['status'] in ['ready','skipped'] else None))
        try:
            cloud,voice,recording,speaker=[grant(s) for s in ['CLOUD_TWIN','VOICE','RECORDING','SPEAKER_IDENTIFICATION']]
            caps=expect(c.get(prefix+'/twin/voice/capabilities'));assert caps['voiceprint_available'] and caps['available']
            report['model_available']=True
            prior_episode_ids={r['episode_id'] for r in expect(c.get(prefix+'/episodes'))['items']}
            assert not expect(c.get(prefix+'/voice-identities'))['items'],'Use a fresh or cleaned dedicated synthetic Subject'
            recipient=expect(visitor.get('/api/v1/workbench/spaces'))['actor_id']
            call=expect(c.post(prefix+'/twin/voice/calls',json={'cloud_consent_id':cloud,'voice_consent_id':voice,'recording_consent_id':recording,'speaker_consent_id':speaker,'policy':caps['policy'],'voice_mode':'default','enroll_owner_voice':True}))['call_id'];calls.append(call)
            utterance(call,'enroll-'+run,intro,'你好，我叫小王，这是我自己的声音。')
            identities=expect(c.get(prefix+'/voice-identities'))['items'];assert len(identities)==1 and identities[0]['role']=='subject'
            report['owner_reference_registered']=True;report['encoder_version']=identities[0]['model_version']
            before=expect(c.get(prefix+'/person-model'))['version']
            utterance(call,'story-'+run,story,'我记得大学校园里的那段时光。')
            utterance(call,'second-'+run,second,'我希望朋友们还记得那棵树。')
            def processed():
                ep=expect(c.get(prefix+'/episodes'))['items'];owned=[r for r in ep if r['episode_id'] not in prior_episode_ids and r.get('capture_origin')=='natural_dialogue' and r['status']=='ready' and r.get('duration_ms')]
                return owned if len(owned)>=2 else None
            owned=wait(processed)
            assert all(r['source']=='IOS_MIC' for r in owned)
            for r in owned:assert c.get('/api/v1/episodes/'+r['episode_id']+'/audio').status_code==200
            report['owner_original_audio_preserved']=True
            after=expect(c.get(prefix+'/person-model'))['version'];assert after>before
            report['owner_dialogue_updates_model']=True
            metric=expect(c.get(prefix+'/person-model/coverage'));assert 0<metric['percentage']<=95;report['coverage_percentage']=metric['percentage']
            utterance(call,'guest-'+run,guest_intro,'你好，我叫小李，我也记得那棵树。')
            identities=expect(c.get(prefix+'/voice-identities'))['items'];assert any(r['role']=='contact' and r['label']=='小李' for r in identities)
            assert expect(c.get(prefix+'/person-model'))['version']==after
            report['guest_introduction_registered_without_person_update']=True
            expect(c.delete(prefix+'/twin/voice/calls/'+call));calls=[]
            handover=grant('DIGITAL_HANDOVER')
            for index,r in enumerate(owned[:2]):
                condition='immediate' if index==0 else 'after_verified_transition'
                if index:
                    expect(c.put(prefix+'/legacy/steward',json={'steward_actor_id':recipient}));legacy_created=True
                plan=expect(c.post(prefix+'/entrustments',json={'recipient_actor_id':recipient,'recipient_label':'小李','episode_ids':[r['episode_id']],'secret':synthetic_secret,'handover_consent_id':handover,'condition':condition}))['plan_id'];plans.append(plan)
            assert visitor.post('/api/v1/entrustments/'+plans[1]+'/start').status_code==404
            expect(visitor.post(prefix+'/legacy/verify',json={'verification_ref':'synthetic-transition-'+run,'verified':True}))
            report['future_scope_requires_designated_transition']=True
            for index,plan in enumerate(plans):
                base='/api/v1/entrustments/'+plan
                visit=expect(visitor.post(base+'/start'))['visit_id'];vh={'X-Entrust-Visit':visit};visit_headers.append(vh)
                hint=expect(visitor.post(base+'/voice-hint',headers=vh,files={'sample':('guest.wav',guest_intro,'audio/wav')}));assert hint['candidate_label']=='小李'
                report['voice_hint_auxiliary_only']=True
                assert visitor.post(base+'/questions',json={'question':'你喜欢什么','request_id':run}).status_code==404
                assert visitor.post(base+'/unlock',headers=vh,json={'phrase':'错误的测试密语'}).status_code==404
                response=visitor.post(base+'/transcribe-secret',headers=vh,files={'sample':('secret.wav',secret_audio,'audio/wav')})
                if response.status_code==200:unlocked=response.json();report['spoken_secret_verified']=True
                else:
                    unlocked=expect(visitor.post(base+'/unlock',headers=vh,json={'phrase':synthetic_secret}));report['spoken_secret_verified']=False;report['typed_fallback_verified']=True
                uh={'X-Entrust-Unlock':unlocked['unlock_token']}
                if index==1:
                    assert visitor.post(base+'/questions',headers=uh,json={'question':'继续刚才的话题','request_id':'wrong-parent-'+run,'previous_answer_id':answers[-1]}).status_code==404
                result=expect(visitor.post(base+'/questions',headers=uh,json={'question':'请根据我专属的资料，回忆你在大学校园和那棵树的往事。','request_id':'scope-'+str(index)+'-'+run}));answers.append(result['answer_id'])
                assert all(e['episode_id']==owned[index]['episode_id'] for e in result['evidence'])
                report['scoped_answers_do_not_cross_libraries']=True
                expect(visitor.delete(base+'/unlock',headers=uh))
                assert visitor.get(base+'/status',headers=uh).status_code==404
            report['explicit_lock_closes_access']=True
            assert expect(c.get(prefix+'/person-model'))['version']==after
            report['recipient_conversation_does_not_update_subject']=True
        finally:
            for call in calls:c.delete(prefix+'/twin/voice/calls/'+call)
            for plan in plans:c.post('/api/v1/entrustments/'+plan+'/revoke')
            # Select only this run's call-linked original copies, not another
            # synthetic run and never a person's Subject.
            q="SELECT episode_id FROM remember_ios.episodes WHERE subject_id='"+subject+"' AND capture_metadata->>'call_id'='"+call+"';" if 'call' in locals() else None
            if q:
                data=sql('own-episodes',q)
                ids=[json.loads(row)[0] for row in data.get('Rows',[])]
                for identifier in ids:expect(c.delete(prefix+'/dialogue-materials/'+identifier))
            for identifier in grants:c.post('/api/v1/consents/'+identifier+'/revoke').raise_for_status()
            if legacy_created:
                sql('legacy-cleanup',"DELETE FROM remember_ios.legacy_states WHERE subject_id='"+subject+"' AND verification_ref='synthetic-transition-"+run+"';")
            if answers:
                ids=','.join("'"+a+"'" for a in answers)
                sql('answer-cleanup',"DELETE FROM remember_ios.chat_turn_embeddings WHERE answer_id IN ("+ids+"); DELETE FROM remember_ios.twin_answers WHERE answer_id IN ("+ids+") AND subject_id='"+subject+"';")
            report['active_voice_templates_after_cleanup']=len(expect(c.get(prefix+'/voice-identities'))['items'])
            Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
