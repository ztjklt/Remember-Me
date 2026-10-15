"""Explicit app-audio test seam: real public WSS/ASR/LLM/TTS, NO microphone claim."""
import argparse, json, subprocess, threading, time, wave
from pathlib import Path


def main(a):
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
    remote='/sdcard/Android/data/me.remember.app.internal/files/continuous-voice'
    def run(*args,**kw):
        return subprocess.run([a.adb,'-s','emulator-5554',*args],capture_output=True,timeout=kw.pop('timeout',10),**kw)
    assert not run('reverse','--list').stdout.strip()
    for i,source in enumerate(a.audio,1):
        path=out/f'question-{i}.wav'
        subprocess.run(['ffmpeg','-y','-v','error','-i',source,'-ac','1','-ar','16000','-c:a','pcm_s16le',str(path)],check=True)
        with wave.open(str(path),'rb') as w:pcm=w.readframes(w.getnframes())
        data=out/f'input-{i}.pcm';data.write_bytes(pcm)
        run('push',str(data),f'/data/local/tmp/voice-demo-input-{i}.pcm').check_returncode()
    names=run('shell','ls',remote).stdout.decode().splitlines()
    owned=[n for n in names if n.startswith('demo-') or n in {'timing-events.json','result.json'}]
    if owned:run('shell','rm','-f',*[remote+'/'+n for n in owned]).check_returncode()
    stop=threading.Event();video=[]
    def watch():
        for i in range(1,len(a.audio)+1):
            while not stop.is_set():
                if run('shell','test','-f',remote+f'/demo-ready-{i}').returncode==0:break
                stop.wait(.2)
            if stop.is_set():return
            if i==1:
                video.append(subprocess.Popen([a.adb,'-s','emulator-5554','shell','screenrecord','--time-limit','180','--bit-rate','3000000','/sdcard/voice-app-pcm.mp4'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
                stop.wait(2)
            run('shell','touch',remote+f'/demo-start-{i}').check_returncode()
    watcher=threading.Thread(target=watch,daemon=True);watcher.start()
    try:
        result=run('shell','am','instrument','-w','-e','class','me.remember.app.ContinuousVoiceLiveTest',
            '-e','timingDemo','true','-e','appPcm','true','-e','timingRounds',str(len(a.audio)),
            '-e','responseSpeed',a.response_speed,'-e','voiceEngine',a.engine,'-e','interruptDemo',str(a.interrupt_demo).lower(),'me.remember.app.internal.test/androidx.test.runner.AndroidJUnitRunner',timeout=240)
        (out/'instrumentation.log').write_bytes(result.stdout+result.stderr)
    finally:
        stop.set();watcher.join(5)
        if video:
            run('shell','pkill','-INT','screenrecord');video[0].wait(15)
            run('pull','/sdcard/voice-app-pcm.mp4',str(out/'screen-unedited.mp4')).check_returncode()
        run('pull',remote,str(out/'android')).check_returncode()
    event_file=out/'android/timing-events.json'
    events=json.loads(event_file.read_text('utf8')) if event_file.exists() else []
    (out/'capture-events.json').write_text(json.dumps([e for e in events if e['kind'] in {'question_started','question_input_ended'}],indent=2),encoding='utf8')
    (out/'capture-summary.json').write_text(json.dumps(dict(clock=dict(device_minus_host_ms=0,roundtrip_ms=0),
        synthetic_input=True,instrumented_app_pcm=True,microphone_bypassed=True,speed=1.0),indent=2),encoding='utf8')
    print(json.dumps(dict(output=str(out),ok=b'OK (1 test)' in result.stdout,microphone_bypassed=True)))
    return b'OK (1 test)' in result.stdout


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--adb',required=True);p.add_argument('--audio',action='append',required=True)
    p.add_argument('--output',required=True);p.add_argument('--response-speed',choices=['reviewed','fast','streamed'],default='fast')
    p.add_argument('--interrupt-demo',action='store_true')
    p.add_argument('--engine',choices=['pipeline','step_realtime'],default='pipeline')
    raise SystemExit(0 if main(p.parse_args()) else 1)
