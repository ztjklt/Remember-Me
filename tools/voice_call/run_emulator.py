"""Opt-in signed-APK cloud test; gRPC injects fictional sound into AudioRecord.
No HTTP tunnelling, TLS override or direct transcript injection is used.
"""
import argparse,atexit,json,os,subprocess,sys,threading,time,wave
from pathlib import Path


def main(args):
    sdk=Path(args.sdk);adb=sdk/'platform-tools/adb.exe';out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    package='me.remember.app.internal'
    remote=f'/sdcard/Android/data/{package}/files/continuous-voice'
    def run(*cmd,**kwargs):return subprocess.run([str(adb),'-s','emulator-5554',*cmd],capture_output=True,**kwargs)
    assert not run('reverse','--list').stdout.strip(), 'This acceptance must not use ADB reverse'
    sys.path.insert(0,args.grpc_stubs)
    import grpc,emulator_controller_pb2 as p,emulator_controller_pb2_grpc as rpc
    config=dict(line.split('=',1) for line in max((Path(os.environ['LOCALAPPDATA'])/'Temp/avd/running').glob('pid_*.ini'),key=lambda f:f.stat().st_mtime).read_text().splitlines() if '=' in line)
    channel=grpc.insecure_channel('127.0.0.1:'+config['grpc.port'],options=[('grpc.enable_http_proxy',0)])
    stub=rpc.EmulatorControllerStub(channel);metadata=[('authorization','Bearer '+config['grpc.token'])]
    from google.protobuf.empty_pb2 import Empty
    original_microphone=stub.getMicrophoneState(Empty(),metadata=metadata,timeout=10)
    def restore_microphone():
        try:stub.setMicrophoneState(original_microphone,metadata=metadata,timeout=10)
        finally:channel.close()
    atexit.register(restore_microphone)
    stub.setMicrophoneState(p.MicrophoneState(realAudioEnabled=False),metadata=metadata,timeout=10)
    pcm=out/'input-16k.wav'
    subprocess.run([args.ffmpeg,'-y','-loglevel','error','-i',args.audio,'-ar','16000','-ac','1','-c:a','pcm_s16le',str(pcm)],check=True)
    interrupted=out/'interrupt-16k.wav'
    subprocess.run([args.ffmpeg,'-y','-loglevel','error','-i',args.interrupt_audio,'-ar','16000','-ac','1','-c:a','pcm_s16le',str(interrupted)],check=True)
    # Remove only this test's known device artifacts; each local attempt is kept.
    artifacts=('ready','interrupt-ready','result.json','failure.png','01-listening.png',
        '02-response.png','03-interrupted-response.png','03-paused.png','04-return-paused.png')
    run('shell','rm','-f',*(remote+'/'+name for name in artifacts)).check_returncode()
    failures=[];videos=[];stop=threading.Event()
    def inject():
        try:
            deadline=time.monotonic()+170
            while time.monotonic()<deadline:
                if stop.is_set():return
                if run('shell','cat',remote+'/ready').returncode==0:break
                time.sleep(.5)
            else:raise RuntimeError('Call did not become ready')
            videos.append(subprocess.Popen([str(adb),'-s','emulator-5554','shell','screenrecord','--time-limit','90','/sdcard/voice-20261014.mp4'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
            def packets(path):
                with wave.open(str(path),'rb') as f:
                    fmt=p.AudioFormat(samplingRate=16000,channels=p.AudioFormat.Mono,format=p.AudioFormat.AUD_FMT_S16)
                    next_frame=time.monotonic()
                    def frame(chunk):
                        nonlocal next_frame
                        time.sleep(max(0,next_frame-time.monotonic()))
                        # Emulator injectAudio only buffers about 300ms. Do
                        # not burst an entire file into the microphone ring.
                        next_frame=time.monotonic()+len(chunk)/32000
                        return p.AudioPacket(format=fmt,audio=chunk)
                    # Lead-in allows the call's microphone coroutine to start.
                    for _ in range(30):yield frame(bytes(640))
                    while chunk:=f.readframes(320):yield frame(chunk)
                    for _ in range(80):yield frame(bytes(640))
            def conversation_packets():
                # Keep one virtual microphone registered across both utterances.
                # Reopening injectAudio can detach the device AudioRecord holds.
                yield from packets(pcm)
                deadline=time.monotonic()+170;next_check=0
                fmt=p.AudioFormat(samplingRate=16000,channels=p.AudioFormat.Mono,format=p.AudioFormat.AUD_FMT_S16)
                while time.monotonic()<deadline:
                    if stop.is_set():return
                    if time.monotonic()>=next_check:
                        if run('shell','cat',remote+'/interrupt-ready').returncode==0:break
                        next_check=time.monotonic()+.2
                    yield p.AudioPacket(format=fmt,audio=bytes(640));time.sleep(.02)
                else:raise RuntimeError('First playback did not start')
                yield from packets(interrupted)
            stub.injectAudio(conversation_packets(),metadata=metadata,timeout=230)
            (out/'injection.json').write_text(json.dumps({'synthetic_audio':True,'through':'continuous paced emulator microphone gRPC','input':pcm.name,'physical_microphone':False}))
        except Exception as error:failures.append(type(error).__name__)
    worker=threading.Thread(target=inject,daemon=True);worker.start()
    try:
        result=run('shell','am','instrument','-w','-e','class','me.remember.app.ContinuousVoiceLiveTest',package+'.test/androidx.test.runner.AndroidJUnitRunner',timeout=400)
    finally:
        stop.set()
        worker.join(timeout=10)
    (out/'instrumentation.log').write_bytes(result.stdout+result.stderr)
    worker.join(timeout=5)
    run('pull',remote,str(out/'screens')).check_returncode()
    (out/'runner.json').write_text(json.dumps({'injection_errors':failures,'instrumentation_exit':result.returncode,'business_connection':'public IP HTTPS/WSS'}))
    print(json.dumps({'instrumentation_exit':result.returncode,'injection_errors':failures}))
    for video in videos:video.wait(timeout=100)
    if videos:run('pull','/sdcard/voice-20261014.mp4',str(out/'voice-20261014.mp4')).check_returncode()
    # Android's instrumentation shell may exit zero even when JUnit failed.
    report=json.loads((out/'screens/result.json').read_text(encoding='utf-8'))
    assert not failures and report.get('ok') and b'OK (1 test)' in result.stdout, 'Inspect retained instrumentation log and screenshots'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sdk',required=True);p.add_argument('--grpc-stubs',required=True)
    p.add_argument('--audio',required=True);p.add_argument('--output',required=True);p.add_argument('--ffmpeg',default='ffmpeg')
    p.add_argument('--interrupt-audio',required=True)
    main(p.parse_args())
