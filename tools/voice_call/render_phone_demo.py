"""Render a 1x excerpt using screenrecord's Winscope clock and observed playback.

The question is synthetic input. The answer track is received live PCM, aligned
to AudioTrack progress, not a physical loudspeaker recording. No waits removed.
"""
import argparse,json,struct,subprocess,wave
from pathlib import Path
import numpy as np


def main(a):
    d=Path(a.input).resolve();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=True)
    events=json.loads((d/'android/timing-events.json').read_text('utf8'))
    capture=json.loads((d/'capture-events.json').read_text('utf8'))
    summary=json.loads((d/'capture-summary.json').read_text('utf8'))
    test_result=json.loads((d/'android/result.json').read_text('utf8'))
    speed=test_result.get('response_speed','reviewed')
    raw=d/'screen-unedited.mp4'
    metadata=subprocess.check_output(['ffmpeg','-v','error','-i',str(raw),'-map','0:2','-c','copy','-f','data','pipe:1'])
    if not metadata:
        # Some Android MP4 edit lists hide the data packet from ffmpeg even
        # though screenrecord wrote its Winscope payload in mdat.
        container=raw.read_bytes();marker=container.find(b'#VV1NSC0PET1ME2#')
        assert marker>=0
        count=struct.unpack_from('<I',container,marker+28)[0]
        assert 0<count<1_000_000
        metadata=container[marker:marker+32+8*count]
    assert metadata.startswith(b'#VV1NSC0PET1ME2#')
    version,offset,count,first=struct.unpack_from('<IqIQ',metadata,16)
    assert version==2 and len(metadata)==32+8*count
    start=(offset+first)/1e6
    device_offset=summary['clock']['device_minus_host_ms']
    def ct(kind,r):return next(x['epoch_ms']+device_offset for x in capture if x['kind']==kind and x.get('round')==r)
    def event(kind,r):return next(x for x in events if x['kind']==kind and x['round']==r)
    end_question=ct('question_input_ended',1)
    beginning=ct('question_started',1)
    played=event('audio_track_started',1)
    audio_start=played['epoch_ms']-played['played_samples']/24
    answer_at=event('answer_visible',1)['epoch_ms']
    finished=event('playback_finished',1)['epoch_ms']
    duration=(finished-start)/1000+1.0
    rate=24000;mix=np.zeros(int((duration+.1)*rate),dtype=np.float64)
    def insert(pcm,at):
        i=round((at-start)/1000*rate)
        if i<0:pcm=pcm[-i:];i=0
        n=min(len(pcm),len(mix)-i)
        if n>0:mix[i:i+n]+=pcm[:n]
    q=subprocess.check_output(['ffmpeg','-v','error','-i',str(d/'question-1.wav'),'-ar','24000','-ac','1','-f','s16le','pipe:1'])
    insert(np.frombuffer(q,'<i2'),beginning)
    response=np.frombuffer((d/f"android/demo-turn-{played['turn_id']}.pcm").read_bytes(),'<i2')
    insert(response,audio_start)
    with wave.open(str(out/'demo-soundtrack.wav'),'wb') as f:
        f.setparams((1,2,rate,0,'NONE','not compressed'));f.writeframes(np.clip(mix,-32768,32767).astype('<i2').tobytes())
    report=dict(input=str(d),screen_clock='Winscope v2 metadata',video_start_device_epoch_ms=start,
        question_end_to_text_ms=round(answer_at-end_question),question_end_to_playback_ms=round(audio_start-end_question),
        question_audio_seconds=len(q)/48000,question_feed_seconds=(end_question-beginning)/1000,
        response_seconds=len(response)/rate,observed_playback_seconds=(finished-audio_start)/1000,
        excerpt_seconds=duration,clock_roundtrip_ms=summary['clock']['roundtrip_ms'],
        mode=speed,synthetic_input=True,physical_speaker_capture=False,
        continuous_followup_passed=False,clip='First round only; all waiting and complete first reply retained',
        transcript=event('answer_visible',1)['text'])
    (out/'timing.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    def ts(t):
        cs=max(0,round(t*100));return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'
    lines=['[Script Info]','ScriptType: v4.00+','PlayResX: 1080','PlayResY: 1200','WrapStyle: 0',
        '[V4+ Styles]','Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
        'Style: Main,Microsoft YaHei,27,&H00EDF1E3,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1',
        '[Events]','Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    def text(value,y,frm=0,to=duration,size=27):
        lines.append(f'Dialogue: 0,{ts(frm)},{ts(to)},Main,,0,0,0,,{{\\pos(575,{y})\\fs{size}}}'+value.replace('\n',r'\N'))
    text('勿忘我 · 语音实跑',55,size=35)
    text('Android → 公网 ECS',120,size=26)
    text('快速回复 / 无独立模型审阅' if speed=='fast' else '标准回复 / 保留模型审阅',162,size=22)
    text('第一轮完整片段\n1× 原速，等待未剪掉',240,size=28)
    text('提问\n你喜欢喝什么茶？',345,size=30)
    wait_start=(end_question-start)/1000;playing=(audio_start-start)/1000
    text('正在提问…',490,0,wait_start,size=32)
    t=wait_start
    while t<playing:
        text(f'等待回复  {t-wait_start:.1f} 秒',490,t,min(t+.1,playing),size=32);t+=.1
    latency=(audio_start-end_question)/1000
    text(f'{latency:.1f} 秒后开始播放',490,playing,duration,size=34)
    text('回答主题\n喜欢淡茶，太甜的喝不惯。',610,playing,duration,size=27)
    text('说明\n问题：合成声音送入模拟麦克风\n回答：本轮 App 收到的声音，\n按实际播放进度对齐。\n不是实体手机扬声器录音。',795,size=22)
    text('本段只证明首轮识别、回答和播放。\n后续追问未通过，详见完整录像。',1060,size=22)
    ass=out/'demo.ass';ass.write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')
    command=['ffmpeg','-y','-v','error','-i',str(raw),'-i',str(out/'demo-soundtrack.wav'),'-t',str(duration),
        '-vf','fps=30,scale=540:1200,pad=1080:1200:0:0:color=0x17352D,ass=demo.ass',
        '-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','fast','-crf','23','-r','30',
        '-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart','android-voice-demo.mp4']
    subprocess.run(command,cwd=out,check=True)
    print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True)
    main(p.parse_args())
