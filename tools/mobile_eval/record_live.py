"""Opt-in local emulator acceptance. Fictional TTS -> virtual mic -> native recorder.

Never copies the script to ASR. Secrets stay in ignored local test/app storage.
Requires built APKs, running backend, emulator, grpcio/grpcio-tools and ffmpeg.
"""
from pathlib import Path
import hashlib,json,os,secrets,shutil,subprocess,sys,threading,time,wave
import httpx

ROOT=Path(__file__).resolve().parents[2]
BACKEND=ROOT/'services/backend'
OUT=BACKEND/'var/mobile-product'
ADB=Path('D:/codex_work/remember-me-toolchain/sdk/platform-tools/adb.exe')
SDK=ADB.parent.parent
PACKAGE='me.remember.app'
BASE='http://127.0.0.1:8877'

def adb(*args,input=None,check=True):
    r=subprocess.run([str(ADB),*args],input=input,capture_output=True)
    if check and r.returncode:raise RuntimeError('ADB command failed: '+r.stderr.decode(errors='replace')[:300])
    return r

def app_file(name,content):
    # Filenames here are fixed test paths, never user-controlled shell input.
    adb('shell','run-as',PACKAGE,'mkdir','-p','files')
    adb('shell','run-as',PACKAGE,'sh','-c',"'cat > files/"+name+"'",input=content)

def api(client,path,**kwargs):
    r=client.request(kwargs.pop('method','GET'),BASE+path,**kwargs)
    if not r.is_success:raise RuntimeError(f'{path}: HTTP {r.status_code} '+r.text[:300])
    return r.json()

def inject(errors):
    try:
        deadline=time.monotonic()+160
        while time.monotonic()<deadline:
            if adb('shell','run-as',PACKAGE,'cat','files/mobile-audio-start',check=False).returncode==0:break
            time.sleep(.5)
        else:raise RuntimeError('Android recording did not request injection')
        import grpc,grpc_tools
        proto=SDK/'emulator/lib';generated=OUT/'grpc';generated.mkdir(exist_ok=True)
        subprocess.run([sys.executable,'-m','grpc_tools.protoc','-I'+str(proto),'-I'+str(Path(grpc_tools.__file__).parent/'_proto'),'--python_out='+str(generated),'--grpc_python_out='+str(generated),str(proto/'emulator_controller.proto')],check=True)
        sys.path.insert(0,str(generated));import emulator_controller_pb2 as p,emulator_controller_pb2_grpc as rpc
        run=Path(os.environ['LOCALAPPDATA'])/'Temp/avd/running'
        config=dict(line.split('=',1) for line in max(run.glob('pid_*.ini'),key=lambda p:p.stat().st_mtime).read_text().splitlines() if '=' in line)
        channel=grpc.insecure_channel('127.0.0.1:'+config['grpc.port'],options=[('grpc.enable_http_proxy',0)])
        stub=rpc.EmulatorControllerStub(channel)
        metadata=[('authorization','Bearer '+config['grpc.token'])]
        # Stop real host microphone use: test input is only the supplied fictional WAV.
        stub.setMicrophoneState(p.MicrophoneState(realAudioEnabled=False),metadata=metadata,timeout=10)
        def packets():
            with wave.open(str(OUT/'input.wav'),'rb') as f:
                fmt=p.AudioFormat(samplingRate=16000,channels=p.AudioFormat.Mono,format=p.AudioFormat.AUD_FMT_S16)
                while data:=f.readframes(320):yield p.AudioPacket(format=fmt,audio=data)
        start=time.monotonic();stub.injectAudio(packets(),metadata=metadata,timeout=55)
        (OUT/'injection.json').write_text(json.dumps({'source':'Xiaomi fictional TTS, injected virtual microphone','elapsed_seconds':time.monotonic()-start,'sha256':hashlib.sha256((OUT/'input.wav').read_bytes()).hexdigest()},indent=2))
        app_file('mobile-audio-done',b'fictional audio injected')
    except Exception as e:errors.append(str(e))

def main():
    OUT.mkdir(exist_ok=True)
    source=BACKEND/'var/monthly-eval/core-runs/groq-core-v4/human-answer.wav'
    subprocess.run([shutil.which('ffmpeg'),'-y','-loglevel','error','-i',str(source),'-ar','16000','-ac','1','-c:a','pcm_s16le',str(OUT/'input.wav')],check=True)
    adb('reverse','tcp:8877','tcp:8877')
    adb('install','-r',str(ROOT/'apps/android/app/build/outputs/apk/debug/app-debug.apk'))
    adb('install','-r',str(ROOT/'apps/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk'))
    config={'username':'mobile_'+secrets.token_hex(5),'password':secrets.token_urlsafe(20),'display_name':'虚构许川 · 手机测试',
      'supplement':'我常说的方言“落屋”就是回家，不是辞职。老隗是同事隗师傅，不是亲戚。'}
    with httpx.Client(timeout=120,trust_env=False) as client:
        if (OUT/'credentials.json').exists():
            config=json.loads((OUT/'credentials.json').read_text(encoding='utf-8'))
        else:
            result=api(client,'/api/v1/accounts/register',method='POST',json={k:config[k] for k in ('username','password','display_name')})
            config['actor_token']=result['actor_token']
            (OUT/'credentials.json').write_text(json.dumps(config,ensure_ascii=False),encoding='utf-8')
        # Remove only this harness's control markers; preserve all app originals.
        adb('shell','run-as',PACKAGE,'rm','-f','files/mobile-audio-start','files/mobile-audio-done','files/mobile-product-complete')
        app_file('mobile-product-config.json',json.dumps(config,ensure_ascii=False).encode())
        errors=[];thread=threading.Thread(target=inject,args=(errors,),daemon=True)
        if not (OUT/'injection.json').exists():thread.start()
        test=adb('shell','am','instrument','-w','-e','class','me.remember.app.MobileProductLiveTest#nativeRecordingToCloudMemoryAndTwin',PACKAGE+'.test/androidx.test.runner.AndroidJUnitRunner',check=False)
        (OUT/'instrumentation.log').write_bytes(test.stdout+test.stderr)
        (OUT/f'instrumentation-{int(time.time())}.log').write_bytes(test.stdout+test.stderr)
        if thread.is_alive():thread.join(timeout=1)
        for name in ('product-login','product-today','product-stories','product-twin'):
            image=adb('exec-out','run-as',PACKAGE,'cat','files/'+name+'.png',check=False)
            if image.returncode==0:(OUT/(name+'.png')).write_bytes(image.stdout)
        client.headers['Authorization']='Bearer '+config['actor_token']
        spaces=api(client,'/api/v1/workbench/spaces')['items'];subject=spaces[0]['subject_id']
        stories=api(client,f'/api/v1/workbench/subjects/{subject}/stories')['items']
        (OUT/'stories.json').write_text(json.dumps(stories,ensure_ascii=False,indent=2),encoding='utf-8')
        complete=adb('shell','run-as',PACKAGE,'cat','files/mobile-product-complete',check=False).returncode==0
        report={'complete':complete,'injection_errors':errors,'stories':len(stories),'subject_id':subject,
          'stt_models':[s['stt_model_version'] for s in stories],'text_models':[s['model_version'] for s in stories],
          'source':'ANDROID_MIC (emulator with injected fictional TTS; not a human microphone test)'}
        (OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)
        if not complete:return 1
        return 0

if __name__=='__main__':raise SystemExit(main())
