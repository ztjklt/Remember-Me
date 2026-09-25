# Local STT bridge for the iOS branch

The existing Backend sends raw `audio/*` bytes to `POST /transcribe` and expects
JSON `{ "text": "...", "model_version": "..." }`. The official whisper.cpp HTTP
server accepts multipart `POST /inference`, so this small local adapter converts
the wire. Backend and iOS remain provider-neutral.

Run a real whisper.cpp server on loopback with a downloaded multilingual model;
for `.m4a` input, use its `--convert` option and have `ffmpeg` installed. Then:

```bash
cd services/stt-bridge
uv sync
WHISPER_SERVER_URL=http://127.0.0.1:8080 \
WHISPER_MODEL_VERSION=whisper-base-local \
uv run uvicorn app.main:app --host 127.0.0.1 --port 8200
```

Configure Backend with `REMEMBER_STT_BACKEND=http` and
`REMEMBER_STT_URL=http://127.0.0.1:8200`. Run the existing STT endpoint check
with a consented recording before claiming it recognizes real speech. The bridge
rejects empty or non-audio input, never logs audio or transcripts, and must not
be exposed to the public network. The model file and its source are local
environment state, not committed to Git.

Run `uv run pytest -q` for the boundary tests. A synthetic speech test proves
technical recognition only; Phase 1 still requires a real device recording.
