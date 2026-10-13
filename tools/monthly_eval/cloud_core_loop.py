"""Isolated, real Groq/Weixin profile and calibration acceptance.

Reuses a hashed fictional Xiaomi recording, never old ASR. Profile approval is
an explicit second command after inspecting the actual candidate and evidence.
New calibration speech is generated only after the Twin answer is locked.
No benchmark gold or author transcript enters ASR, extraction or Twin requests.
"""
import argparse
import base64
import hashlib
import json
from datetime import datetime, timezone

import httpx
from dotenv import dotenv_values
import product_loop as product
from cloud_asr_samples import wait_for_review
from cloud_followthrough import Steps, wait_profile
from speech_pipeline import REPO, OUT, save, synthesize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    parser.add_argument('--confirm-candidate')
    args = parser.parse_args()
    if not args.run.replace('-', '').isalnum():
        raise SystemExit('Invalid run name')
    run = OUT / 'core-runs' / args.run
    run.mkdir(parents=True, exist_ok=True)
    product.AUTH = run / 'identities.json'
    pair = product.identities({'people':[{'id':'core', 'name':'许川·独立云端校准验证'}]})['core']
    owner, reader = pair['owner'], pair['reader']
    subject = owner['subject_id']
    api = '/api/v1/subjects/' + subject
    root = '/api/v1/workbench/subjects/' + subject
    profiles = root + '/profile-candidates'
    state_path = run / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf8')) if state_path.exists() else {
        'human_listening':False, 'fictional':True, 'episodes':{}, 'phase':'initial'}
    if state['phase']=='complete':
        print('Completed checkpoint retained; no models called again.',flush=True)
        return
    steps = Steps(run / 'steps.json')
    def persist(): save(state_path, state)
    def mutate(label, method, path, identity=owner, **kw):
        return steps.once(label, lambda: product.call(method, path, identity, **kw))
    caps = product.call('GET', '/api/v1/workbench/capabilities', owner)
    if caps['stt'] != 'groq' or not caps['stt_configured']:
        raise RuntimeError('Live Groq required; no fallback.')
    if state.get('policy', caps['cloud_asr_policy']) != caps['cloud_asr_policy']:
        raise RuntimeError('ASR policy changed; no automatic migration.')
    state['policy'] = caps['cloud_asr_policy']; persist()
    cloud = mutate('cloud-consent','POST','/api/v1/consents',json={
        'subject_id':subject,'scope':'CLOUD_TWIN',
        'evidence_ref':'authorized-fictional-cloud-profile-calibration-test'})['consent_id']

    def upload(name, audio, metadata=None):
        raw = audio.read_bytes(); checksum = hashlib.sha256(raw).hexdigest()
        row = state['episodes'].setdefault(name, {'audio_sha256':checksum})
        if row['audio_sha256'] != checksum:
            raise RuntimeError('Immutable original changed.')
        ep = mutate('upload/'+name, 'POST', '/api/v1/episodes', data={
            'subject_id':subject,'recording_consent_id':owner['consent_id'],
            'source':'IMPORT','recorded_at':datetime.now(timezone.utc).isoformat(),
            'audio_ref':audio.name,'idempotency_key':args.run+'-'+name,
            'metadata':json.dumps({'fictional':True,'cloud_asr_policy':state['policy'],
                                  **(metadata or {})})}, files={'file':(audio.name,raw,'audio/wav')})['episode_id']
        row['episode_id'] = ep; persist()
        wait_for_review(owner,ep,run/(name+'.asr-review.json'),row,persist,seconds=300)
        story = next(s for s in product.call('GET',root+'/stories',owner)['items'] if s['episode_id']==ep)
        if story['stt_model_version'] != 'groq/whisper-large-v3':
            raise RuntimeError('Unexpected ASR provenance.')
        if not story['memories'] or not all(e['excerpt'] in story['transcript']
                for m in story['memories'] for e in m['evidence']):
            raise RuntimeError('Nonempty grounded extraction required.')
        save(run/(name+'.story.json'), story)
        response = httpx.get('http://127.0.0.1:8877'+root+'/stories/'+ep+'/audio',
            headers={'Authorization':'Bearer '+owner['actor_token']},trust_env=False,timeout=30)
        if response.status_code != 200 or hashlib.sha256(response.content).hexdigest()!=checksum:
            raise RuntimeError('Original audio read-back failed.')
        row['audio_hash_verified']=True; row['status']='ready'; persist()
        return story

    initial = OUT/'state-loop/initial.wav'
    original = json.loads(initial.with_suffix('.json').read_text(encoding='utf8'))
    if original['audio_sha256'] != hashlib.sha256(initial.read_bytes()).hexdigest():
        raise RuntimeError('Original Xiaomi audio hash mismatch.')
    upload('initial', initial)
    job = mutate('profile','POST',profiles+'/refresh',json={'cloud_consent_id':cloud})
    snapshot_path = run/'profile-before-approval.json'
    if not snapshot_path.exists():
        snapshot = wait_profile(lambda: product.call('GET',profiles,owner),job['job_id'])
        save(snapshot_path,snapshot)
    if not args.confirm_candidate:
        state['phase']='awaiting_operator_evidence_review';persist()
        print('Actual profile saved. Inspect evidence before explicit --confirm-candidate.',flush=True)
        return
    snapshot=json.loads(snapshot_path.read_text(encoding='utf8'))
    chosen=next((c for c in snapshot['items'] if c['candidate_id']==args.confirm_candidate),None)
    if chosen is None or not chosen['evidence']:
        raise RuntimeError('Candidate absent from this actual profile run.')
    if state.get('approved_candidate_id',args.confirm_candidate)!=args.confirm_candidate:
        raise RuntimeError('Approval differs from checkpoint; do not silently substitute a candidate.')
    state['approved_candidate_id']=args.confirm_candidate;persist()
    update = mutate('profile-ADD','POST',profiles+'/updates',json={
        'candidate_id':args.confirm_candidate,'action':'ADD',
        'reason':'虚构测试：操作者已逐条核对原文，仅确认本次情境观察，不代表稳定人格或真人确认。'})
    mutate('confirm-profile-ADD','POST',profiles+'/updates/'+update['update_id']+'/confirm')
    state['approval_basis']='assistant evidence review of fictional technical test; not human participant approval'
    twin = mutate('twin-before-human','POST',api+'/twin/answers',json={
        'question':'如果工作收入和家人安全发生冲突，讲述者会怎样选择？','cloud_consent_id':cloud})
    if twin['response_type']=='UNKNOWN' or not twin['evidence']:
        raise RuntimeError('Grounded Twin answer required before calibration.')
    locked=mutate('lock-calibration','POST',api+'/calibrations',json={
        'twin_answer_id':twin['answer_id'],'cloud_consent_id':cloud})
    cid=locked['calibration_id']
    # Only now read and synthesize the prewritten human-response fixture.
    audio=run/'human-answer.wav'; manifest=run/'human-answer.json'
    if not manifest.exists():
        if audio.exists():
            raise RuntimeError('Unmanifested audio exists; preserve and inspect before resuming.')
        corpus=json.loads((REPO/'evaluations/agent-loop-smoke-v1/scripts.json').read_text(encoding='utf8'))
        answer=next(c['text'] for c in corpus['clips'] if c['id']=='calibration')
        key=dotenv_values(REPO/'services/backend/.env.speech-eval').get('MIMO_API_KEY')
        if not key: raise RuntimeError('Xiaomi key missing; no provider switch.')
        voice='data:audio/wav;base64,'+base64.b64encode((OUT/'bus_driver/synthetic-voice.wav').read_bytes()).decode()
        data,meta=synthesize(key,'mimo-v2.5-tts-voiceclone',answer,
            '虚构男性声音，清晰普通话，逐字完整朗读，不添加内容。',voice)
        audio.write_bytes(data)
        save(manifest,meta|{'locked_calibration_id':cid,'human_listening':False})
    meta=json.loads(manifest.read_text(encoding='utf8'))
    if meta['locked_calibration_id']!=cid or meta['audio_sha256']!=hashlib.sha256(audio.read_bytes()).hexdigest():
        raise RuntimeError('Calibration audio provenance mismatch.')
    human=upload('human-answer',audio,{'calibration_id':cid})
    before=product.call('GET',profiles,owner)
    result=mutate('compare','POST',api+'/calibrations/'+cid+'/complete',json={'cloud_consent_id':cloud})
    after=product.call('GET',profiles,owner)
    after_story=next(s for s in product.call('GET',root+'/stories',owner)['items'] if s['episode_id']==human['episode_id'])
    if (result['status']!='complete' or result['locked_answer']!=twin['answer']
            or result['comparison_model_version']!='Deepseek-v4-flash'
            or before!=after or after_story['memories']!=human['memories']):
        raise RuntimeError('Calibration completion/immutability check failed.')
    if not all(d['human_excerpt'] is None or d['human_excerpt'] in human['transcript'] for d in result['dimensions']):
        raise RuntimeError('Calibration citation not in actual reviewed ASR.')
    reader_response=httpx.get('http://127.0.0.1:8877'+root+'/stories',
        headers={'Authorization':'Bearer '+reader['actor_token']},trust_env=False,timeout=30)
    # An entirely private space is deliberately indistinguishable from absent.
    if reader_response.status_code != 404:
        raise RuntimeError('An unshared subject must be hidden from an independent reader.')
    state['reader_http_status']=reader_response.status_code
    save(run/'calibration-result.json',result)
    state.update(phase='complete',no_automatic_profile_or_memory_edit=True,
        reader_private=True,locked_before_tts=True,semantic_review='pending')
    persist();print('Real cloud profile ADD and locked-answer calibration complete; review report semantics.',flush=True)


if __name__=='__main__': main()
