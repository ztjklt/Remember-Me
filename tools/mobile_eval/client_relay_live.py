"""Opt-in native Android -> desktop Groq -> ECS acceptance; no script-as-ASR.

Uses ignored private run config, an already installed debug/test APK pair, and
the matching verified HTTPS service URL compiled in the APK. Does not deploy.
"""
from pathlib import Path
import hashlib,json,os,subprocess,sys,threading,time,wave,math,array

ROOT=Path(__file__).resolve().parents[2]
BACKEND=ROOT/'services/backend'
OUT=BACKEND/'var/android-client-relay-20261009'
if len(sys.argv)>1:
    OUT=Path(sys.argv[1]).resolve()
    if not OUT.is_relative_to((BACKEND/'var').resolve()): raise ValueError('Acceptance output must stay under backend/var')
ADB=Path('D:/codex_work/remember-me-toolchain/sdk/platform-tools/adb.exe')
PACKAGE='me.remember.app'

def adb(*args,input=None,check=True):
    r=subprocess.run([str(ADB),*args],input=input,capture_output=True)
    if check and r.returncode: raise RuntimeError('ADB operation failed')
    return r

def app_file(name,content):
    # Only fixed harness filenames; credentials travel through stdin, not argv.
    adb('shell','run-as',PACKAGE,'mkdir','-p','files')
    adb('shell','run-as',PACKAGE,'sh','-c',"'cat > files/"+name+"'",input=content)

def await_file(name,seconds):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if adb('shell','run-as',PACKAGE,'test','-f','files/'+name,check=False).returncode==0: return
        time.sleep(.5)
    raise TimeoutError('Android did not reach '+name)

def reset_virtual_mic():
    import grpc
    sys.path.insert(0,str(BACKEND/'var/mobile-product/grpc'))
    import emulator_controller_pb2 as p,emulator_controller_pb2_grpc as rpc
    run=Path(os.environ['LOCALAPPDATA'])/'Temp/avd/running'
    cfg=dict(line.split('=',1) for line in max(run.glob('pid_*.ini'),key=lambda p:p.stat().st_mtime).read_text().splitlines() if '=' in line)
    channel=grpc.insecure_channel('127.0.0.1:'+cfg['grpc.port'],options=[('grpc.enable_http_proxy',0)])
    rpc.EmulatorControllerStub(channel).setMicrophoneState(p.MicrophoneState(realAudioEnabled=False),metadata=[('authorization','Bearer '+cfg['grpc.token'])],timeout=10)
    channel.close()

def inject():
        await_file('relay-mic-start',120)
        import grpc
        sys.path.insert(0,str(BACKEND/'var/mobile-product/grpc'))
        import emulator_controller_pb2 as p,emulator_controller_pb2_grpc as rpc
        run=Path(os.environ['LOCALAPPDATA'])/'Temp/avd/running'
        cfg=dict(line.split('=',1) for line in max(run.glob('pid_*.ini'),key=lambda p:p.stat().st_mtime).read_text().splitlines() if '=' in line)
        channel=grpc.insecure_channel('127.0.0.1:'+cfg['grpc.port'],options=[('grpc.enable_http_proxy',0)])
        stub=rpc.EmulatorControllerStub(channel);metadata=[('authorization','Bearer '+cfg['grpc.token'])]
        def packets():
            with wave.open(str(OUT/'input.wav'),'rb') as f:
                fmt=p.AudioFormat(samplingRate=f.getframerate(),channels=p.AudioFormat.Mono,format=p.AudioFormat.AUD_FMT_S16)
                while data:=f.readframes(f.getframerate()//50): yield p.AudioPacket(format=fmt,audio=data)
        started=time.monotonic();stub.injectAudio(packets(),metadata=metadata,timeout=60)
        (OUT/'injection.json').write_text(json.dumps({'source':'existing fictional Xiaomi TTS via virtual mic, not human speech',
            'input_sha256':hashlib.sha256((OUT/'input.wav').read_bytes()).hexdigest(),'elapsed_seconds':time.monotonic()-started},indent=2))
        app_file('relay-mic-done',b'done')

def relay(errors):
    try:
        config=json.loads((OUT/'config.json').read_text(encoding='utf-8'))
        if not config.get('existing_recording_sha256'): inject()
        capture_only=config.get('capture_only',False)
        await_file('relay-capture-only' if capture_only else 'relay-asr-start',70)
        audio=OUT/'native-original.m4a'
        audio.write_bytes(adb('exec-out','run-as',PACKAGE,'cat','files/relay-original.m4a').stdout)
        pcm=subprocess.run(['ffmpeg','-v','error','-i',str(audio),'-f','s16le','-ac','1','-ar','16000','-'],capture_output=True,check=True).stdout
        samples=array.array('h',pcm)
        rms=math.sqrt(sum(x*x for x in samples)/max(1,len(samples)))
        db=20*math.log10(max(rms,1e-8)/32768)
        (OUT/'audio-quality.json').write_text(json.dumps({'rms_dbfs':db,'threshold_dbfs':-55,'is_speech_validation':False}))
        if capture_only: return
        if db < -55: raise ValueError('Native virtual-mic capture is too quiet; do not call or technically confirm ASR')
        sys.path.insert(0,str(BACKEND));sys.path.insert(0,str(ROOT/'tools'))
        from app.config import Settings
        from app.groq_asr import GroqSttProvider
        from client_asr_capture import transcribe_recording
        settings=Settings(_env_file=BACKEND/'.env',groq_asr_state_dir=str(OUT/'groq-calls'))
        draft=OUT/'machine.json'
        cached=config.get('existing_machine_checkpoint')
        if cached:
            result=json.loads(Path(cached).read_text(encoding='utf-8'))
            if result['client_transcript']['audio_sha256'] != hashlib.sha256(audio.read_bytes()).hexdigest(): raise ValueError('Cached ASR belongs to different audio')
            draft.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            (OUT/'asr-reuse.json').write_text(json.dumps({'existing_actual_call':cached,'matching_audio_sha256':result['client_transcript']['audio_sha256']}))
        else:
            result=transcribe_recording(audio,draft,GroqSttProvider(settings),audio_export_confirmed=True)
        # Synthetic acceptance oracle only. Never sent to ASR/LLM or used to replace text.
        expected=json.loads((OUT/'config.json').read_text(encoding='utf-8')).get('expected_asr_fragments',[])
        quality={'required_fragments_present':all(s in result['client_transcript']['text'] for s in expected),'human_listening':False}
        (OUT/'asr-quality.json').write_text(json.dumps(quality))
        if not quality['required_fragments_present']: raise ValueError('ASR does not contain the known test-story facts; technical confirmation refused')
        # Write atomically in app storage so the running test cannot read half JSON.
        app_file('relay-machine.tmp',draft.read_bytes())
        adb('shell','run-as',PACKAGE,'mv','files/relay-machine.tmp','files/relay-machine.json')
    except Exception as e:
        errors.append(type(e).__name__) # Provider exceptions must not echo credentials.
        (OUT/'relay-error.json').write_text(json.dumps({'error_type':type(e).__name__}))
        app_file('relay-error',type(e).__name__.encode())

def main():
    config_file=OUT/'config.json'
    if not config_file.is_file(): raise SystemExit('Create private config.json and input.wav first; no credentials in argv.')
    if (OUT/'machine.json').exists(): raise SystemExit('Run already has an ASR checkpoint. Inspect and archive before a deliberate new recording.')
    adb('install','-r',str(ROOT/'apps/android/app/build/outputs/apk/debug/app-debug.apk'))
    adb('install','-r',str(ROOT/'apps/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk'))
    app_file('client-relay-config.json',config_file.read_bytes())
    # Only control files belonging to this harness, never app recordings.
    markers=['relay-mic-start','relay-mic-done','relay-asr-start','relay-machine.json','relay-complete','relay-capture-only','relay-result.json','relay-error']
    markers += ['relay-'+name+'.png' for name in ('original','draft','memory','twin','portrait')]
    adb('shell','run-as',PACKAGE,'rm','-f',*[f'files/{name}' for name in markers])
    if not json.loads(config_file.read_text(encoding='utf-8')).get('existing_recording_sha256'): reset_virtual_mic()
    errors=[];thread=threading.Thread(target=relay,args=(errors,),daemon=True);thread.start()
    test=adb('shell','am','instrument','-w','-e','class','me.remember.app.ClientRelayLiveTest#nativeCaptureClientDraftEcsMemoryAndTwin',PACKAGE+'.test/androidx.test.runner.AndroidJUnitRunner',check=False)
    (OUT/'instrumentation.log').write_bytes(test.stdout+test.stderr)
    for name in ('original','draft','memory','twin','portrait'):
        r=adb('exec-out','run-as',PACKAGE,'cat','files/relay-'+name+'.png',check=False)
        if r.returncode==0 and r.stdout.startswith(b'\x89PNG'): (OUT/(name+'.png')).write_bytes(r.stdout)
    r=adb('exec-out','run-as',PACKAGE,'cat','files/relay-result.json',check=False)
    if r.returncode==0 and r.stdout.startswith(b'{'): (OUT/'result.json').write_bytes(r.stdout)
    thread.join(timeout=10)
    complete=adb('shell','run-as',PACKAGE,'test','-f','files/relay-complete',check=False).returncode==0
    capture_only=json.loads(config_file.read_text(encoding='utf-8')).get('capture_only',False)
    (OUT/'status.json').write_text(json.dumps({'complete':complete,'capture_only':capture_only,'relay_errors':errors,'connection':'SSH-forwarded verified TLS; not direct public IP','real_handset':False},indent=2))
    adb('shell','run-as',PACKAGE,'rm','-f','files/client-relay-config.json')
    print(json.dumps({'complete':complete,'relay_errors':errors}),flush=True)
    return 0 if complete else 1

if __name__=='__main__':raise SystemExit(main())
