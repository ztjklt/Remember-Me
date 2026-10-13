"""Opt-in signed-APK cloud test; gRPC injects fictional sound into AudioRecord.
No HTTP tunnelling, TLS override or direct transcript injection is used.
"""
import argparse,json,os,subprocess,sys,threading,time,wave
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
    stub.setMicrophoneState(p.MicrophoneState(realAudioEnabled=False),metadata=metadata,timeout=10)
    pcm=out/'input-16k.wav'
    subprocess.run([args.ffmpeg,'-y','-loglevel','error','-i',args.audio,'-ar','16000','-ac','1','-c:a','pcm_s16le',str(pcm)],check=True)
    interrupted=out/'interrupt-16k.wav'
    subprocess.run([args.ffmpeg,'-y','-loglevel','error','-i',args.interrupt_audio,'-ar','16000','-ac','1','-c:a','pcm_s16le',str(interrupted)],check=True)
    run('shell','rm','-f',remote+'/ready',remote+'/interrupt-ready',remote+'/result.json',remote+'/failure.png').check_returncode()
    failures=[];videos=[]
    def inject():
        try:
            deadline=time.monotonic()+170
            while time.monotonic()<deadline:
                if run('shell','cat',remote+'/ready').returncode==0:break
                time.sleep(.5)
            else:raise RuntimeError('Call did not become ready')
            videos.append(subprocess.Popen([str(adb),'-s','emulator-5554','shell','screenrecord','--time-limit','90','/sdcard/voice-20261014.mp4'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
            def packets(path):
                with wave.open(str(path),'rb') as f:
                    fmt=p.AudioFormat(samplingRate=16000,channels=p.AudioFormat.Mono,format=p.AudioFormat.AUD_FMT_S16)
                    # Lead-in allows the call's microphone coroutine to start.
                    for _ in range(30):yield p.AudioPacket(format=fmt,audio=bytes(640))
                    while chunk:=f.readframes(320):yield p.AudioPacket(format=fmt,audio=chunk)
                    for _ in range(80):yield p.AudioPacket(format=fmt,audio=bytes(640))
            stub.injectAudio(packets(pcm),metadata=metadata,timeout=45)
            deadline=time.monotonic()+170
            while time.monotonic()<deadline:
                if run('shell','cat',remote+'/interrupt-ready').returncode==0:break
                time.sleep(.1)
            else:raise RuntimeError('First playback did not start')
            stub.injectAudio(packets(interrupted),metadata=metadata,timeout=45)
            (out/'injection.json').write_text(json.dumps({'synthetic_audio':True,'through':'emulator microphone gRPC','input':pcm.name,'physical_microphone':False}))
        except Exception as error:failures.append(type(error).__name__)
    worker=threading.Thread(target=inject,daemon=True);worker.start()
    result=run('shell','am','instrument','-w','-e','class','me.remember.app.ContinuousVoiceLiveTest',package+'.test/androidx.test.runner.AndroidJUnitRunner',timeout=400)
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
