"""Speech-to-text boundary.

The provider is not frozen (ADR-0001 D9), so nothing outside this module names a
vendor: the worker asks for a transcript and gets one, and which service produced
it is recorded on the Episode as `stt_backend` and `stt_model_version` rather than
assumed.

`build_stt_provider` refuses the fake outside development and test. That check is
the reason the fake can be deterministic and this module can stay small: a
validation-environment deployment that forgot to configure a real provider fails
at startup instead of quietly filling the record with placeholder transcripts.
"""

from dataclasses import dataclass
from typing import Protocol

from .config import Settings
from .storage.base import checksum_of

FAKE_BACKEND = "fake"
FAKE_MODEL_VERSION = "fake-stt-v1"


@dataclass(frozen=True)
class Transcript:
    """One transcript, with the provenance of whatever produced it."""

    text: str
    backend: str
    model_version: str


class SttProvider(Protocol):
    """Boundary every speech-to-text provider sits behind."""

    def transcribe(self, audio: bytes, content_type: str) -> Transcript: ...


class FakeSttProvider:
    """Deterministic placeholder transcription: no speech recognition happens.

    The text is a pure function of the audio's checksum, so it is stable across
    runs and differs between recordings, and it says what it is. A placeholder
    that read like plausible speech would be indistinguishable from a real
    transcript once it reached the memory table.
    """

    backend = FAKE_BACKEND
    model_version = FAKE_MODEL_VERSION

    def transcribe(self, audio: bytes, content_type: str) -> Transcript:
        digest = checksum_of(audio)
        text = (
            f"[fake-stt] no speech recognition ran on this audio "
            f"({len(audio)} bytes, {content_type}, sha256 {digest[:12]})"
        )
        return Transcript(
            text=text, backend=self.backend, model_version=self.model_version
        )


def build_stt_provider(settings: Settings) -> SttProvider:
    if settings.stt_backend == FAKE_BACKEND:
        if settings.environment not in ("development", "test"):
            raise ValueError(
                "The fake speech-to-text provider is only allowed in development "
                "and test; configure a real provider for "
                f"{settings.environment!r}"
            )
        return FakeSttProvider()
    raise ValueError(f"Unsupported STT backend: {settings.stt_backend!r}")