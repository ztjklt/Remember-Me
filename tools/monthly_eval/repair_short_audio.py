"""Explicitly replace an abnormally short synthetic clip, preserving its original."""
import argparse,base64,io,json,time,wave
from dotenv import dotenv_values
from speech_pipeline import CORPUS,OUT,REPO,synthesize,save,sha
from nightly_rules import publish_repair

def concat_wav(parts):
    fmt=None;frames=[]
    for data in parts:
        with wave.open(io.BytesIO(data),'rb') as w:
            current=(w.getnchannels(),w.getsampwidth(),w.getframerate())
            if fmt is not None and fmt!=current:raise ValueError('incompatible PCM formats')
            fmt=current;frames.append(w.readframes(w.getnframes()))
    if not fmt:raise ValueError('no audio')
    out=io.BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(fmt[0]);w.setsampwidth(fmt[1]);w.setframerate(fmt[2]);w.writeframes(b''.join(frames))
    return out.getvalue()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('episode');args=ap.parse_args()
    manifest=json.loads((CORPUS/'manifest.json').read_text(encoding='utf-8'))
    person=next(p for p in manifest['people'] if any(e['id']==args.episode for e in p['episodes']))
    ep=next(e for e in person['episodes'] if e['id']==args.episode);folder=OUT/person['id']
    path=folder/(ep['id']+'.wav');record=path.with_suffix('.json');original=json.loads(record.read_text(encoding='utf-8'))
    if original.get('segmented_repair'):print('already repaired');return
    assert original['duration_seconds']<180,'This repair is only for abnormally short complete-script clips'
    mapping=json.loads((OUT/'product-episodes.json').read_text(encoding='utf-8'))
    assert ep['id'] not in mapping,'already imported: preserve this episode and use an explicit new version'
    text=(CORPUS/ep['script']).read_text(encoding='utf-8');segments=[];current=''
    for paragraph in text.splitlines(keepends=True):
        if len(current)+len(paragraph)>350 and current:segments.append(current);current=''
        current+=paragraph
    if current:segments.append(current)
    assert ''.join(segments)==text
    key=dotenv_values(REPO/'services/backend/.env.speech-eval')['MIMO_API_KEY']
    voice='data:audio/wav;base64,'+base64.b64encode((folder/'synthetic-voice.wav').read_bytes()).decode()
    parts=[];records=[];segment_dir=folder/(ep['id']+'-repair');segment_dir.mkdir(exist_ok=True)
    for i,segment in enumerate(segments):
        audio=segment_dir/f'{i}.wav';meta=segment_dir/f'{i}.json'
        if audio.exists() and meta.exists():
            data=audio.read_bytes();r=json.loads(meta.read_text(encoding='utf-8'));assert r['text_sha256']==sha(segment.encode()) and r['audio_sha256']==sha(data)
        else:
            data,r=synthesize(key,'mimo-v2.5-tts-voiceclone',segment,person['voice']+'完整逐字朗读，不省略内容。',voice)
            audio.write_bytes(data);save(meta,r)
        parts.append(data);records.append(r);print(ep['id'],'segment',i+1,'saved',flush=True)
    data=concat_wav(parts)
    with wave.open(io.BytesIO(data),'rb') as w:duration=w.getnframes()/w.getframerate()
    publish_repair(path,record,data,original|{'duration_seconds':duration,'duration_pass':180<=duration<=300,'segmented_repair':True,'segment_records':records,'manual_listening':'pending','generated_repair_at':time.time()})
    print(ep['id'],'repaired',duration,'seconds',flush=True)

if __name__=='__main__':main()
