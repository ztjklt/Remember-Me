"""Create actual short synthetic audio for API state-loop regression, not monthly QA."""
import base64
import json
from dotenv import dotenv_values
from speech_pipeline import REPO, OUT, synthesize, save, sha

root = OUT / 'state-loop'
root.mkdir(exist_ok=True)
key = dotenv_values(REPO / 'services/backend/.env.speech-eval')['MIMO_API_KEY']
voice = 'data:audio/wav;base64,' + base64.b64encode((OUT / 'bus_driver/synthetic-voice.wav').read_bytes()).decode()
corpus = json.loads((REPO / 'evaluations/agent-loop-smoke-v1/scripts.json').read_text(encoding='utf-8'))
for clip in corpus['clips']:
    if clip['id'] == 'calibration':
        continue  # Generated only after the Twin answer has been locked.
    path = root / (clip['id'] + '.wav')
    meta = path.with_suffix('.json')
    if path.exists() and meta.exists():
        data = json.loads(meta.read_text(encoding='utf-8'))
        assert data['audio_sha256'] == sha(path.read_bytes()) and data['text_sha256'] == sha(clip['text'].encode())
        continue
    data, report = synthesize(key, 'mimo-v2.5-tts-voiceclone', clip['text'],
        '虚构男性声音，普通话，清晰自然完整朗读，不添加内容。', voice)
    path.write_bytes(data)
    save(meta, report | {'synthetic':True,'benchmark':'state-loop-smoke','listening_quality':'not_checked'})
    print(clip['id'], round(report['duration_seconds'],2), 'seconds; actual TTS saved', flush=True)
