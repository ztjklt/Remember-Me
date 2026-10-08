"""Local signal observations; never a psychological or sound-source diagnosis."""
from array import array
import math
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


class PCMObserver:
    version = "pcm-observation-v1"

    def observe(self, audio: bytes) -> dict:
        # Imported/recorded audio is decoded locally, with bounded time and output.
        # Unknown fixture/provider formats degrade independently of text processing.
        recognized = audio.startswith((b"RIFF", b"OggS", b"fLaC", b"ID3")) or audio[4:8] == b"ftyp"
        decoder = shutil.which("ffmpeg")
        if not decoder or not recognized:
            return {"status": "unavailable", "model_version": self.version,
                    "reason": "decoder_unavailable" if not decoder else "unsupported_audio"}
        try:
            # M4A may put its index after media packets. A seekable input is
            # required; decoding it from a pipe can silently return no samples.
            with TemporaryDirectory(prefix="remember-signal-") as folder:
                source = Path(folder) / "source.audio"
                source.write_bytes(audio)
                result = subprocess.run([decoder, "-nostdin", "-v", "error", "-i", str(source), "-t", "30",
                                         "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"],
                                        capture_output=True, timeout=8, check=True)
        except (subprocess.SubprocessError, OSError):
            return {"status": "unavailable", "model_version": self.version, "reason": "decode_failed"}
        samples = array("h")
        samples.frombytes(result.stdout[:960000 - 960000 % 2])
        if sys.byteorder != "little":
            samples.byteswap()
        if not samples:
            return {"status": "unavailable", "model_version": self.version, "reason": "empty_audio"}
        rms = math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768
        frames = [samples[i:i + 320] for i in range(0, len(samples), 320)]
        silent = sum(math.sqrt(sum(x * x for x in frame) / len(frame)) / 32768 < .01 for frame in frames)
        return {"status": "available", "model_version": self.version,
                "analyzed_seconds": round(len(samples) / 16000, 3),
                "rms_dbfs": round(20 * math.log10(max(rms, 1e-8)), 2),
                "silence_fraction": round(silent / len(frames), 4),
                "clipped_fraction": round(sum(abs(x) >= 32760 for x in samples) / len(samples), 6),
                "interpretation": "signal_only"}
