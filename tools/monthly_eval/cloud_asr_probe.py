"""One actual audio-only relay probe. No retries, model guessing or script input."""
import argparse
import io
import json
import sys
import time
import wave
from speech_pipeline import REPO, OUT, save
from cloud_asr_samples import load_sample


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True, choices=['codestral-2508', 'mistral-code-fim-latest'])
    parser.add_argument('--seconds', type=int, choices=[8, 20], default=8)
    args = parser.parse_args()
    backend = REPO / 'services/backend'
    sys.path.insert(0, str(backend))
    from app.config import Settings
    from app.relay_asr import RelaySttProvider, configured
    settings = Settings(_env_file=backend / '.env', relay_asr_model=args.model)
    if not configured(settings):
        raise SystemExit('Missing actual relay endpoint/ASR key; no request sent.')
    # The shared pacer must resolve to the same directory as the running backend.
    from pathlib import Path
    path = Path(settings.relay_asr_state_dir)
    settings.relay_asr_state_dir = str(path if path.is_absolute() else backend / path)
    manifest = json.loads((REPO / 'evaluations/monthly-integration-v1/manifest.json').read_text(encoding='utf-8'))
    _, _, raw, _ = load_sample(manifest['people'][0])
    target = OUT / 'cloud-asr-probes' / (str(time.time_ns()) + '-' + args.model)
    target.mkdir(parents=True)
    with wave.open(io.BytesIO(raw), 'rb') as source:
        segment = source.readframes(args.seconds * source.getframerate())
        with wave.open(str(target / 'actual-audio.wav'), 'wb') as output:
            output.setparams(source.getparams())
            output.writeframes(segment)
    audio = (target / 'actual-audio.wav').read_bytes()
    transcript = RelaySttProvider(settings).transcribe(audio, 'audio/wav')
    save(target / 'result.json', {'raw_asr': transcript.text, 'call': transcript.metadata,
        'human_listening': False, 'semantic_review': 'pending', 'source': 'synthetic audio bytes only'})
    print('Cloud transcript received; quality unverified. Evidence:', target)


if __name__ == '__main__':
    main()
