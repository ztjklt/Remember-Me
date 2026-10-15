"""Record the real APK, timing and live received PCM; only the QUESTION is injected.

Keeps the unedited video, live answer PCM, input audio and timing evidence.
No provider credentials, answer substitution, speed-up, or business tunnel.
"""
import argparse, atexit, json, os, subprocess, sys, threading, time, wave
from pathlib import Path


def main(a):
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
    adb=Path(a.sdk)/'platform-tools/adb.exe'
    def run(*args,**kw):
        kw.setdefault('timeout',10)
        return subprocess.run([str(adb),'-s','emulator-5554',*args],capture_output=True,**kw)
    assert not run('reverse','--list').stdout.strip(), 'Business tunnels are not allowed in this demo'
    sys.path.insert(0,a.grpc_stubs)
    import grpc, emulator_controller_pb2 as p, emulator_controller_pb2_grpc as rpc
    from google.protobuf.empty_pb2 import Empty
    cfg=dict(l.split('=',1) for l in max((Path(os.environ['LOCALAPPDATA'])/'Temp/avd/running').glob('pid_*.ini'),key=lambda f:f.stat().st_mtime).read_text().splitlines() if '=' in l)
    channel=grpc.insecure_channel('127.0.0.1:'+cfg['grpc.port'],options=[('grpc.enable_http_proxy',0)])
    stub=rpc.EmulatorControllerStub(channel);md=[('authorization','Bearer '+cfg['grpc.token'])]
    old=stub.getMicrophoneState(Empty(),metadata=md,timeout=10)
    def restore():
        try:stub.setMicrophoneState(old,metadata=md,timeout=10)
        finally:channel.close()
    atexit.register(restore)
    stub.setMicrophoneState(p.MicrophoneState(realAudioEnabled=False),metadata=md,timeout=10)
    inputs=[]
    for i,source in enumerate(a.audio,1):
        path=out/f'question-{i}.wav'
        subprocess.run(['ffmpeg','-y','-v','error','-i',source,'-ac','1','-ar','16000','-c:a','pcm_s16le',str(path)],check=True)
        with wave.open(str(path),'rb') as f:inputs.append(f.readframes(f.getnframes()))
    remote='/sdcard/Android/data/me.remember.app.internal/files/continuous-voice'
    run('shell','rm','-f',*[remote+'/'+n for n in ('demo-ready-1','demo-ready-2','demo-connect-mic','demo-microphone-connected','timing-events.json','result.json')]).check_returncode()
    # Clear only prior timing-demo tracks/logs, whose full local copies are retained.
    prior=run('shell','ls',remote).stdout.decode('utf8').splitlines()
    owned=[n for n in prior if n.startswith('demo-turn-') and n.endswith('.pcm') or n=='demo-protocol.jsonl']
    if owned:run('shell','rm','-f',*[remote+'/'+n for n in owned]).check_returncode()
    stop=threading.Event();events=[];errors=[];videos=[]
    # Paced input uses the emulator's real-time delivery mode; the default mode
    # queues behind the device consumer and can leave a later question behind silence.
    fmt=p.AudioFormat(samplingRate=16000,channels=p.AudioFormat.Mono,format=p.AudioFormat.AUD_FMT_S16,mode=p.AudioFormat.MODE_REAL_TIME)
    ready=[threading.Event() for _ in inputs]
    connect_mic=threading.Event();mic_registered=threading.Event()
    def mark(kind,**kw):
        events.append(dict(kind=kind,epoch_ms=time.time()*1000,**kw))
        (out/'capture-events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf8')
    def inject():
        try:
            # Do not open an empty audio RPC while Android is still launching.
            deadline=time.monotonic()+130
            while not connect_mic.wait(.1):
                if stop.is_set():return
                if time.monotonic()>deadline:raise TimeoutError('Call was not ready')
            def stream():
                next_frame=time.monotonic()
                def frame(data):
                    nonlocal next_frame
                    # One stream throughout the call; never replace the microphone.
                    next_frame+=.02
                    time.sleep(max(0,next_frame-time.monotonic()))
                    return p.AudioPacket(format=fmt,audio=data)
                for _ in range(50):yield frame(bytes(640))
                mic_registered.set()
                while not ready[0].is_set():
                    if stop.is_set():return
                    yield frame(bytes(640))
                mark('screenrecord_command_started')
                videos.append(subprocess.Popen([str(adb),'-s','emulator-5554','shell','screenrecord','--time-limit','180','--bit-rate','3000000','/sdcard/voice-timing-demo.mp4'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
                for _ in range(100):yield frame(bytes(640))
                for i,pcm in enumerate(inputs,1):
                    if i>1:
                        deadline=time.monotonic()+125
                        while not ready[i-1].is_set():
                            if stop.is_set():return
                            if time.monotonic()>deadline:raise TimeoutError('Next round was not ready')
                            yield frame(bytes(640))
                    mark('question_started',round=i)
                    for offset in range(0,len(pcm),640):
                        yield frame(pcm[offset:offset+640])
                    mark('question_input_ended',round=i)
                while not stop.is_set():yield frame(bytes(640))
            stub.injectAudio(stream(),metadata=md,timeout=275)
        except Exception as e:
            if not stop.is_set():errors.append('microphone: '+type(e).__name__+(' '+e.code().name if isinstance(e,grpc.RpcError) else ''))
    worker=threading.Thread(target=inject,daemon=True);worker.start();time.sleep(1)
    def watch_ready():
        try:
            while not stop.is_set():
                if run('shell','test','-f',remote+'/demo-connect-mic').returncode==0:
                    connect_mic.set();break
                stop.wait(.25)
            while not stop.is_set() and not mic_registered.wait(.1):pass
            if stop.is_set():return
            run('shell','touch',remote+'/demo-microphone-connected').check_returncode()
            for i,signal in enumerate(ready,1):
                while not stop.is_set():
                    if run('shell','test','-f',remote+f'/demo-ready-{i}').returncode==0:
                        signal.set();break
                    stop.wait(.25)
        except Exception as e:errors.append('readiness: '+type(e).__name__)
    threading.Thread(target=watch_ready,daemon=True).start()
    t0=time.time()*1000
    device=float(run('shell','date','+%s%3N').stdout.strip())
    t1=time.time()*1000
    clock=dict(device_minus_host_ms=device-(t0+t1)/2,roundtrip_ms=t1-t0)
    result=None
    try:
        result=run('shell','am','instrument','-w','-e','class','me.remember.app.ContinuousVoiceLiveTest','-e','timingDemo','true','-e','timingRounds',str(len(inputs)),'-e','responseSpeed',a.response_speed,'me.remember.app.internal.test/androidx.test.runner.AndroidJUnitRunner',timeout=240)
        (out/'instrumentation.log').write_bytes(result.stdout+result.stderr)
    finally:
        mark('capture_finished');stop.set();worker.join(timeout=8)
        run('shell','pkill','-INT','screenrecord')
        for video in videos:video.wait(timeout=15)
        run('pull',remote,str(out/'android'))
        if videos:run('pull','/sdcard/voice-timing-demo.mp4',str(out/'screen-unedited.mp4')).check_returncode()
        (out/'capture-summary.json').write_text(json.dumps(dict(clock=clock,errors=errors,synthetic_input=True,output='live app received PCM aligned to observed AudioTrack progress; not physical speaker capture',server='public IP HTTPS/WSS',speed=1.0),indent=2),encoding='utf8')
    print(json.dumps(dict(output=str(out),errors=errors,instrumentation_ok=result is not None and b'OK (1 test)' in result.stdout)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sdk',required=True);p.add_argument('--grpc-stubs',required=True)
    p.add_argument('--audio',action='append',required=True);p.add_argument('--output',required=True)
    p.add_argument('--response-speed',choices=['reviewed','fast'],default='reviewed')
    main(p.parse_args())
