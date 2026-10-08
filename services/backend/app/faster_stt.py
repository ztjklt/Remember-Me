"""Optional, offline faster-whisper engine behind the existing STT HTTP wire.

The operator supplies a downloaded multilingual CTranslate2 model directory.
No model download, fallback transcription, or speaker-identity claim happens here.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from importlib.metadata import version


class LocalSttError(RuntimeError):
    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class FasterWhisperEngine:
    def __init__(self, model_path: Path, *, device: str = "cpu",
                 compute_type: str = "int8") -> None:
        self.model_path = model_path
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._version: str | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        if not self.model_path.is_dir() or not (self.model_path / "model.bin").is_file():
            raise LocalSttError("A local CTranslate2 model directory is required")
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(str(self.model_path), device=self.device,
                                 compute_type=self.compute_type, local_files_only=True)
            if not model.model.is_multilingual:
                raise LocalSttError("An English-only model cannot transcribe Chinese")
            library_version = version('faster-whisper')
            digest = hashlib.sha256(json.dumps({
                "engine_version": library_version, "device": self.device,
                "compute_type": self.compute_type, "language": "zh",
                "vad_filter": True, "beam_size": 5, "condition_on_previous_text": False,
            }, sort_keys=True).encode())
            # Include weights, tokenizer and config. Provenance describes the
            # loaded snapshot; replacing files requires restarting the sidecar.
            for path in sorted(self.model_path.rglob("*")):
                if path.is_file() and path.suffix in {".bin", ".json", ".txt"}:
                    digest.update(str(path.relative_to(self.model_path)).encode("utf-8"))
                    with path.open("rb") as source:
                        for block in iter(lambda: source.read(1024 * 1024), b""):
                            digest.update(block)
            # Fit the existing 64-character provenance column without a schema
            # migration; 128 fingerprint bits cover both weights and options.
            self._version = f"faster-whisper-{library_version}@{digest.hexdigest()[:32]}"
            self._model = model
        except LocalSttError:
            raise
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise LocalSttError("The local faster-whisper model is unavailable") from exc

    def transcribe(self, audio: bytes) -> dict[str, str]:
        self._load()
        try:
            from av.error import FFmpegError
            segments, _ = self._model.transcribe(
                io.BytesIO(audio), language="zh", beam_size=5, vad_filter=True,
                condition_on_previous_text=False,
            )
            # Inference is lazy; consuming the generator belongs inside this
            # error boundary. The engine does not remove negation or edit quotes.
            text = "".join(segment.text for segment in segments).strip()
        except (ValueError, EOFError, FFmpegError) as exc:
            raise LocalSttError("The audio cannot be decoded", 422) from exc
        except (OSError, RuntimeError) as exc:
            raise LocalSttError("The local transcription engine is unavailable") from exc
        return {"text": text, "model_version": self._version}
