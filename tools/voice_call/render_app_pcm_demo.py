"""Unaccelerated multi-turn video, with explicit input seam and real received speech."""
import argparse, json, struct, subprocess, wave
from pathlib import Path
import numpy as np


def main(a):
    d=Path(a.input).resolve();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
    events=json.loads((d/'android/timing-events.json').read_text('utf8'))
    result=json.loads((d/'android/result.json').read_text('utf8'))
    assert result.get('instrumented_app_pcm') is True
    raw=d/'screen-unedited.mp4';data=raw.read_bytes();marker=data.find(b'#VV1NSC0PET1ME2#')
    assert marker>=0
    version,offset,count,first=struct.unpack_from('<IqIQ',data,marker+16)
    assert version==2 and count>0
    start=(offset+first)/1e6
    def get(kind,r):return next(x for x in events if x['kind']==kind and x['round']==r)
    completed=[e['round'] for e in events if e['kind'] in {'playback_finished','playback_interrupted'}]
    assert completed
    turns=[]
    for r in completed:
        played=get('audio_track_started',r);input_end=get('question_input_ended',r)['epoch_ms']
        with wave.open(str(d/f'question-{r}.wav'),'rb') as qf:
            rate=qf.getframerate();qpcm=np.frombuffer(qf.readframes(qf.getnframes()),'<i2').astype(float)
        block=max(1,rate//100)
        voiced=[i for i in range(0,len(qpcm),block) if np.sqrt(np.mean(qpcm[i:i+block]**2))>200]
        tail_ms=(len(qpcm)-min(len(qpcm),(voiced[-1]+block) if voiced else len(qpcm)))/rate*1000
        end=input_end-tail_ms
        audio_start=played['epoch_ms']-played['played_samples']/24
        answer=get('answer_visible',r)
        final_answer=[e for e in events if e['kind']=='answer_visible' and e['round']==r][-1]
        pcm=np.frombuffer((d/f"android/demo-turn-{played['turn_id']}.pcm").read_bytes(),'<i2').astype(float)
        active=[i for i in range(0,len(pcm),240) if np.sqrt(np.mean(pcm[i:i+240]**2))>200]
        lead_ms=(active[0]/24) if active else 0
        audible_start=audio_start+lead_ms
        recognized=[e['text'] for e in events if e['kind']=='transcript' and e['round']==r and e['epoch_ms']<=answer['epoch_ms']]
        stops=[e for e in events if e['kind']=='playback_interrupted' and e['round']==r]
        stop=stops[0] if stops else None
        if stop:
            assert audio_start <= stop['stopped_epoch_ms'] <= stop['epoch_ms'], 'Inconsistent interruption timestamps; do not render this capture'
            assert 0 < stop['played_samples'] <= len(pcm), 'Invalid interrupted playback position'
        turns.append(dict(round=r,interrupted=bool(stop),played_samples=stop['played_samples'] if stop else None,question_start=get('question_started',r)['epoch_ms'],question_end=end,
            audio_start=audio_start,audible_start=audible_start,input_tail_ms=round(tail_ms),tts_leading_silence_ms=round(lead_ms),finished=stop['stopped_epoch_ms'] if stop else get('playback_finished',r)['epoch_ms'],turn_id=played['turn_id'],
            text=final_answer['text'],question=recognized[-1],latency_ms=round(audible_start-end),latency_to_playback_ms=round(audio_start-input_end),
            text_ms=answer['epoch_ms']-end))
    turns.sort(key=lambda t:t['round'])
    duration=(turns[-1]['finished']-start)/1000+1
    mix=np.zeros(int((duration+.1)*24000),dtype=np.float64)
    def insert(pcm,at):
        i=round((at-start)*24)
        if i<0:pcm=pcm[-i:];i=0
        n=min(len(pcm),len(mix)-i)
        if n>0:mix[i:i+n]+=pcm[:n]
    for t in turns:
        q=subprocess.check_output(['ffmpeg','-v','error','-i',str(d/f"question-{t['round']}.wav"),'-ar','24000','-ac','1','-f','s16le','pipe:1'])
        insert(np.frombuffer(q,'<i2'),t['question_start'])
        answer_pcm=np.frombuffer((d/f"android/demo-turn-{t['turn_id']}.pcm").read_bytes(),'<i2')
        if t['interrupted']:answer_pcm=answer_pcm[:t['played_samples']]
        progress=[e for e in events if e['kind']=='playback_progress' and e.get('turn_id')==t['turn_id']]
        if t['interrupted']:progress.append(dict(epoch_ms=t['finished'],played_samples=t['played_samples']))
        else:progress.append(dict(epoch_ms=t['finished'],played_samples=len(answer_pcm)))
        if len(progress)>1:
            previous=0;cursor=t['audio_start']
            for e in sorted(progress,key=lambda e:e['epoch_ms']):
                position=min(len(answer_pcm),e['played_samples'])
                if position<=previous:continue
                duration_ms=(position-previous)/24
                at=max(cursor,e['epoch_ms']-duration_ms)
                insert(answer_pcm[previous:position],at)
                previous=position;cursor=at+duration_ms
        else:insert(answer_pcm,t['audio_start'])
    with wave.open(str(out/'soundtrack.wav'),'wb') as f:
        f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(np.clip(mix,-32768,32767).astype('<i2').tobytes())
    def ts(t):
        cs=max(0,round(t*100));return f'{cs//360000}:{cs//6000%60:02}:{cs%6000//100:02}.{cs%100:02}'
    lines=['[Script Info]','ScriptType: v4.00+','PlayResX: 1080','PlayResY: 1200','WrapStyle: 0',
        '[V4+ Styles]','Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
        'Style: Main,Microsoft YaHei,27,&H00EDF1E3,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1',
        '[Events]','Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    def text(value,y,frm=0,to=duration,size=27):
        lines.append(f'Dialogue: 0,{ts(frm)},{ts(to)},Main,,0,0,0,,{{\\pos(575,{y})\\fs{size}}}'+value.replace('\n',r'\N'))
    text('勿忘我 · 连续语音',55,size=35)
    text('Android '+result['version']+' → ECS',120,size=26)
    text('Realtime 试用 / 实际记忆检索' if result.get('voice_engine')=='step_realtime' else ('快速回复 / 无独立模型审阅' if result['response_speed']!='reviewed' else '标准回复 / 保留模型审阅'),165,size=24)
    text('1× 原速 · 保留完整等待',215,size=26)
    for index,t in enumerate(turns):
        begin=0 if index==0 else (t['question_start']-start)/1000
        until=(turns[index+1]['question_start']-start)/1000 if index+1<len(turns) else duration
        stopped=(t['question_end']-start)/1000;playing=(t['audible_start']-start)/1000
        question=t['question'];wrapped='\n'.join(question[i:i+13] for i in range(0,len(question),13))
        text(f"第 {t['round']} 轮\n{wrapped}",310,begin,until,size=30)
        text('正在提问…',500,begin,stopped,size=32)
        tick=stopped
        while tick<playing:
            text(f'等待回复 {tick-stopped:.1f} 秒',500,tick,min(tick+.1,playing),size=32);tick+=.1
        text(f"{t['latency_ms']/1000:.1f} 秒后听到回答",500,playing,until,size=32)
    text('演示范围\n预录问题送入 App 通话音频通道\n绕过模拟器系统麦克风\n\n转写、模型回答、合成均为实调\n声音来自 App 本轮收到的音频\n按 AudioTrack 播放进度同步',750,size=22)
    text('连续追问＋插话打断 · 原速实录' if result['ok'] and any(t['interrupted'] for t in turns) else '连续追问；本次未演示打断。',1080,size=22)
    (out/'demo.ass').write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(raw),'-i',str(out/'soundtrack.wav'),'-t',str(duration),
        '-vf','fps=30,scale=540:1200,pad=1080:1200:0:0:color=0x17352D,ass=demo.ass',
        '-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart','android-fast-voice.mp4'],cwd=out,check=True)
    report=dict(silence_measurement='10ms PCM windows, RMS > 200; digital signal, not physical microphone/speaker latency',turns=turns,seconds=duration,instrumentation_ok=result['ok'],microphone_bypassed=True,speed=1)
    (out/'timing.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True)
    main(p.parse_args())
