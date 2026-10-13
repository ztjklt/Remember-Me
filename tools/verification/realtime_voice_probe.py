"""Isolated synthetic RTC regression. Reports contain numeric stages only.

The fixture must be a dedicated rvp_qa_transport_ preset profile. Supply a 0600
transport-state.json and two preset-generated qa-question-N.pcm files. The
operator must clear the preset reference and revoke the fixture VOICE grant
in a finally block; this probe always attempts to end its own call.
"""
import asyncio,json,time,sys,array,math,os,base64,copy,hashlib,hmac,re,traceback
from pathlib import Path
from collections import deque
import httpx
from livekit import rtc
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--private-dir',type=Path,required=True)
parser.add_argument('--report',type=Path,required=True)
parser.add_argument('--synthetic-qa',action='store_true',required=True)
parser.add_argument('--qa-agent-name',default=None,help='Explicit staging dispatch; default uses the production ticket unchanged')
args=parser.parse_args()
P=args.private_dir.resolve();args.report.parent.mkdir(parents=True,exist_ok=True)
state=json.loads((P/'transport-state.json').read_text())
assert state['profile_id'].startswith('rvp_qa_transport_'), 'Dedicated preset QA profile required'
assert (P/'transport-state.json').stat().st_mode & 0o077 == 0, 'Fixture credentials require mode 0600'
report={'scope':'synthetic QA account, system preset voice, enrollment bypassed for transport only','phase':'initializing','cleanup_errors':[]}
headers={'Authorization':'Bearer '+state['actor_token']};base=state['origin']+f"/api/v1/subjects/{state['subject_id']}/twin/voice";events=[];received=0;audio_times=[];reads=set();buffers=deque();started=time.monotonic()

def safe_events():
 return [{'type':e.get('type'),'state':e.get('state'),'time':e.get('time')} for e in events]

def qa_dispatch_ticket(ticket,agent_name):
 # Only the ignored synthetic probe can opt into another dispatch. Preserve the
 # backend-authorized participant, room and microphone-only grants verbatim.
 if not agent_name:return ticket
 assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',agent_name)
 credentials={}
 for line in (P/'realtime.env').read_text().splitlines():
  key,separator,value=line.partition('=')
  if separator and key.strip() in ['REMEMBER_LIVEKIT_API_KEY','REMEMBER_LIVEKIT_API_SECRET']:
   value=value.strip()
   if len(value)>=2 and value[0]==value[-1] and value[0] in ['"',"'"]:value=value[1:-1]
   credentials[key.strip()]=value
 key=credentials['REMEMBER_LIVEKIT_API_KEY'];secret=credentials['REMEMBER_LIVEKIT_API_SECRET'].encode()
 original_parts=ticket['token'].split('.');assert len(original_parts)==3
 def decoded(part):return json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))
 def encoded(value):return base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).rstrip(b'=').decode()
 header=decoded(original_parts[0]);original=decoded(original_parts[1])
 assert header.get('alg')=='HS256' and original.get('iss')==key
 original_signature=base64.urlsafe_b64decode(original_parts[2]+'='*(-len(original_parts[2])%4))
 assert hmac.compare_digest(original_signature,hmac.new(secret,'.'.join(original_parts[:2]).encode(),hashlib.sha256).digest())
 assert original['sub']==ticket['participant_identity']
 assert original['video']['room']==ticket['room']==ticket['call_id']
 assert original['video']['canPublishSources']==['microphone']
 replacement=copy.deepcopy(original)
 agents=replacement['roomConfig']['agents'];assert len(agents)==1
 assert json.loads(agents[0]['metadata'])=={'call_id':ticket['call_id']}
 agents[0]['agentName']=agent_name
 now=int(time.time());replacement['exp']=min(original['exp'],now+120,original['nbf']+120)
 assert original['nbf']<=now<replacement['exp']<=original['exp']
 assert replacement['exp']-now<=120 and replacement['exp']-replacement['nbf']<=120
 assert replacement['sub']==original['sub'] and replacement['video']==original['video']
 # No claim outside dispatch and the (possibly shortened) expiry may change.
 unchanged=copy.deepcopy(replacement);unchanged['exp']=original['exp']
 unchanged['roomConfig']['agents'][0]['agentName']=original['roomConfig']['agents'][0]['agentName']
 assert unchanged==original
 payload='.'.join([encoded(header),encoded(replacement)])
 signature=base64.urlsafe_b64encode(hmac.new(secret,payload.encode(),hashlib.sha256).digest()).rstrip(b'=').decode()
 result=dict(ticket,token=payload+'.'+signature)
 verified=decoded(result['token'].split('.')[1])
 assert verified==replacement and verified['video']==original['video'] and verified['sub']==original['sub']
 assert {k:v for k,v in result.items() if k!='token'}=={k:v for k,v in ticket.items() if k!='token'}
 return result

async def main():
 global received
 room=None;source=None;sending=None;client=None;ticket=None;streams=[]
 metrics={'captured_frames':0,'injected_frames':0,'capture_errors':0}
 async def cleanup(label,operation,seconds=8):
  try:
   await asyncio.wait_for(operation,seconds)
   return True
  except Exception as exc:
   report['cleanup_errors'].append({'step':label,'error_type':type(exc).__name__})
   return False
 try:
  room=rtc.Room();source=rtc.AudioSource(16000,1,queue_size_ms=100)
  args.report.with_suffix('.progress.json').write_text(json.dumps({'phase':report['phase'],'events':[]}))
  @room.on('data_received')
  def data(packet):
   if packet.topic!='remember.twin.voice.v1':return
   value=json.loads(packet.data);value['time']=round(time.monotonic()-started,3);events.append(value);args.report.with_suffix('.progress.json').write_text(json.dumps({'phase':report['phase'],'events':safe_events()}))
  @room.on('track_subscribed')
  def track(track,publication,participant):
   if track.kind!=rtc.TrackKind.KIND_AUDIO:return
   stream=rtc.AudioStream(track,sample_rate=24000,num_channels=1);streams.append(stream)
   async def consume():
    global received
    async for frame in stream:
     values=array.array('h',bytes(frame.frame.data))
     if values and math.sqrt(sum(x*x for x in values)/len(values))>200:
      received+=1;audio_times.append(time.monotonic()-started)
   task=asyncio.create_task(consume());reads.add(task);
  async def wait_for(predicate,seconds=60):
   deadline=time.monotonic()+seconds
   while not predicate():
    errors=[e for e in events if e.get('type') in ['error','ended']]
    if errors:raise RuntimeError('Agent error event')
    if sending and sending.done():sending.result();raise RuntimeError('Microphone producer stopped')
    if time.monotonic()>deadline:raise TimeoutError('Agent event timed out')
    await asyncio.sleep(.1)
  def inject(index):
   raw=(P/f'qa-question-{index}.pcm').read_bytes()
   for pos in range(0,len(raw),640):buffers.append(raw[pos:pos+640].ljust(640,b'\0'));metrics['injected_frames']+=1
  async def feed():
   while True:
    try:
     await source.capture_frame(rtc.AudioFrame(data=buffers.popleft() if buffers else b'\0'*640,sample_rate=16000,num_channels=1,samples_per_channel=320))
    except Exception:
     metrics['capture_errors']+=1
     raise
    metrics['captured_frames']+=1
  client=httpx.AsyncClient(timeout=45,follow_redirects=False,trust_env=False)
  report['phase']='create_call'
  r=await client.post(base+'/calls',headers=headers,json={'cloud_consent_id':state['grants']['CLOUD_TWIN'],'voice_consent_id':state['grants']['VOICE'],'policy':state['policy']});r.raise_for_status();ticket=r.json();state['call_id']=ticket['call_id'];(P/'transport-state.json').write_text(json.dumps(state))
  claims=json.loads(base64.urlsafe_b64decode(ticket['token'].split('.')[1]+'='*(-len(ticket['token'].split('.')[1])%4)))
  assert claims['roomConfig']['agents'][0]['agentName']=='remember-twin'
  assert claims['video']['canPublishSources']==['microphone']
  qa_agent_name=args.qa_agent_name
  ticket=qa_dispatch_ticket(ticket,qa_agent_name)
  if qa_agent_name:report['test_dispatch']=qa_agent_name
  report['phase']='connect_rtc'
  await asyncio.wait_for(room.connect(ticket['livekit_url'],ticket['token']),30);report['rtc_connected']=True
  report['phase']='publish_microphone'
  track=rtc.LocalAudioTrack.create_audio_track('synthetic QA microphone',source)
  await room.local_participant.publish_track(track,rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE));sending=asyncio.create_task(feed())
  report['phase']='wait_agent_ready'
  await wait_for(lambda:any(e.get('type')=='state' and e.get('state')=='listening' for e in events),35);report['agent_ready']=True
  report['phase']='first_answer';inject(1)
  await wait_for(lambda:any(e.get('type')=='answer' for e in events),25);first=next(e for e in events if e.get('type')=='answer');report['first_response_type']=first['answer']['response_type']
  report['phase']='first_audio'
  await wait_for(lambda:received>=3,30);report['received_audio_before_barge_in']=received;barge=time.monotonic()-started;report['barge_time']=round(barge,3);inject(2)
  report['phase']='second_answer'
  await wait_for(lambda:len([e for e in events if e.get('type')=='answer'])>=2,75)
  answers=[e for e in events if e.get('type')=='answer'];report['second_response_type']=answers[-1]['answer']['response_type'];report['turn_id_changed']=first['turn_id']!=answers[-1]['turn_id'];report['first_turn_late_restart']=any(e.get('type')=='state' and e.get('state')=='speaking' and e.get('turn_id')==first['turn_id'] and e['time']>barge+.6 for e in events)
  assert report['turn_id_changed'] and not report['first_turn_late_restart']
  report['phase']='second_audio';second_baseline=received
  await wait_for(lambda:received>second_baseline+5,30);report['second_reply_audio_frames']=received-second_baseline;report['received_nonzero_audio_frames']=received
  second_speaking=next(e['time'] for e in events if e.get('state')=='speaking' and e.get('turn_id')==answers[-1]['turn_id'])
  report['audio_frames_during_interrupted_gap']=sum(barge+1.2<t<second_speaking for t in audio_times)
  assert report['audio_frames_during_interrupted_gap']==0
  report['phase']='manual_interrupt'
  await room.local_participant.publish_data(json.dumps({'type':'interrupt','turn_id':answers[-1]['turn_id']}).encode(),reliable=True,topic='remember.twin.voice.v1');report['manual_interrupt_sent']=True;report['manual_interrupt_time']=round(time.monotonic()-started,3)
  await asyncio.sleep(.8)
  sys.path.insert(0,str(P.resolve()));from control import invoke
  sql="SELECT CASE WHEN active_turn='' THEN 1 ELSE 0 END AS interrupted FROM remember_ios.voice_calls WHERE call_id='"+ticket['call_id']+"';"
  deadline=time.monotonic()+8;report['manual_interrupt_confirmed']=False
  while time.monotonic()<deadline:
   proof=await asyncio.to_thread(invoke,'qa-manual-interrupt-proof',['db','execute','-e','remember-me-ios-d5f9twwlcae71c69','--sql',sql,'--json'])
   report['manual_interrupt_confirmed']=json.loads(proof['Rows'][0])[0] in [1,'1']
   if report['manual_interrupt_confirmed']:break
   await asyncio.sleep(.3)
  assert report['manual_interrupt_confirmed']
  report['phase']='long_silence';quiet_start=time.monotonic();await asyncio.sleep(65)
  report['quiet_seconds']=round(time.monotonic()-quiet_start,1)
  prior=len([e for e in events if e.get('type')=='answer']);report['third_injection_time']=round(time.monotonic()-started,3)
  report['audio_frames_after_manual_interrupt']=sum(report['manual_interrupt_time']+1.2<t<report['third_injection_time'] for t in audio_times)
  assert report['audio_frames_after_manual_interrupt']==0
  report['phase']='third_answer';inject(1)
  await wait_for(lambda:len([e for e in events if e.get('type')=='answer'])>prior,40)
  report['phase']='third_audio';third_baseline=received
  await wait_for(lambda:received>third_baseline+5,30)
  report['speech_after_long_silence']=True
  report['phase']='checks_complete'
 except Exception as exc:
  report['failure_phase']=report['phase'];report['primary_error_type']=type(exc).__name__
  report['failure_line']=traceback.extract_tb(exc.__traceback__)[-1].lineno
  raise
 finally:
  report['events']=safe_events()
  report['microphone']=dict(metrics,unsent_frames=len(buffers),producer_started=sending is not None,
   producer_stopped_before_cleanup=sending.done() if sending else False)
  if sending:
   sending.cancel()
   joined=await cleanup('microphone_producer',asyncio.gather(sending,return_exceptions=True))
   report['microphone']['producer_cleanup_done']=joined and sending.done()
  else:report['microphone']['producer_cleanup_done']=True
  readers=list(reads)
  for task in readers:task.cancel()
  if readers:await cleanup('audio_readers',asyncio.gather(*readers,return_exceptions=True))
  for index,stream in enumerate(streams):await cleanup('audio_stream_'+str(index),stream.aclose())
  if room is not None:await cleanup('rtc_room',room.disconnect())
  if source is not None:await cleanup('audio_source',source.aclose())
  if client is not None and ticket is not None:
   async def end_call():
    end=await client.delete(base+'/calls/'+ticket['call_id'],headers=headers,timeout=8)
    report['end_http_status']=end.status_code;end.raise_for_status()
   await cleanup('end_call',end_call(),10)
  if client is not None:await cleanup('http_client',client.aclose())
  report['events']=safe_events()
  args.report.with_suffix('.progress.json').write_text(json.dumps({'phase':report['phase'],'events':safe_events()}))
try:
 asyncio.run(main())
 report['result']='failed' if report['cleanup_errors'] else 'passed'
 if report['cleanup_errors']:report['error_type']='CleanupError';report['failure_phase']='cleanup'
 else:report['phase']='complete'
except Exception as exc:
 report['result']='failed';report['error_type']=type(exc).__name__
args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False))
sys.exit(0 if report['result']=='passed' else 1)
