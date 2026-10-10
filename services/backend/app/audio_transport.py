"""Bounded media conversion only; no speech model and no original file writes."""
import subprocess
import tempfile
from pathlib import Path

from .errors import SttFailed

MAX_WIRE_BYTES = 25 * 1024 * 1024

def compact_audio(raw: bytes) -> bytes:
    try:
        with tempfile.TemporaryDirectory(prefix='remember-asr-') as directory:
            source = Path(directory) / 'source.audio'
            target = Path(directory) / 'wire.mp3'
            source.write_bytes(raw)
            subprocess.run([
                'ffmpeg', '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                '-format_whitelist', 'wav,mp3,mov,matroska,webm,ogg,flac,aac',
                '-i', str(source), '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '24000',
                '-b:a', '48k', '-fs', str(MAX_WIRE_BYTES), '-f', 'mp3', str(target)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=120)
            # -fs bounds the temporary file while FFmpeg runs. A file at the
            # cap may be truncated and MUST NOT be sent as a complete recording.
            if not target.exists() or not 0 < target.stat().st_size < MAX_WIRE_BYTES:
                raise SttFailed('云端转写音频压缩结果为空或达到大小上限，原音保留。')
            return target.read_bytes()
    except (OSError, subprocess.SubprocessError) as error:
        raise SttFailed('云端转写音频压缩失败，请检查 FFmpeg；原音保留，未发送音频。') from error
