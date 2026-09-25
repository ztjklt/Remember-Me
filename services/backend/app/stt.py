"""Speech-to-text boundary.

The provider is not frozen (ADR-0001 D9), so nothing outside this module names a
vendor: the worker asks for a transcript and gets one, and which service produced
it is recorded on the Episode as `stt_backend` and `stt_model_version` rather than
assumed.

Two adapters ship. `http` is the deployment one and speaks a deliberately small
wire contract of this module's own, so a provider can be attached without any
other part of the service changing:

    POST {stt_url}{stt_path}
    Content-Type: <the audio's content type>
    <the raw audio bytes>
    ->
    200 {"text": "...", "model_version": "..."}   # model_version optional

A non-2xx answer keeps the same meaning it has at the AI Core boundary: 503 and
504 are the provider's own transient conditions and return to the job's retry
budget, while anything else ends the stage, because the same audio would be
refused again.

`model_version` is optional because a provider that does not report one is still
a provider; what it must not do is have "unreported" written into the record as
if it were a version, so the absence gets a name of its own.

**Where the fake may run.** `build_stt_provider` refuses the fake outside
development and test, which is what stops a validation-environment deployment
from quietly filling the record with placeholder transcripts. The refusal has an
explicit override — `REMEMBER_ALLOW_FAKE_PROVIDERS=true` — for the one case that
needs it: bringing up an environment end to end before its real provider exists.
The rule is shared with the AI Core boundary in app/providers.py, so the two
cannot disagree about it.
"""

from dataclasses import dataclass
from typing import Protocol

import httpx

from .config import Settings
from .errors import SttFailed, SttTimeout, SttUnavailable
from .providers import refuse_fake_unless_permitted
from .storage.base import checksum_of

FAKE_BACKEND = "fake"
FAKE_MODEL_VERSION = "fake-stt-v1"
HTTP_BACKEND = "http"

# What is recorded when a provider answered without naming the model that produced
# the transcript. A version that says "unknown" is honest; an empty string would
# read as a version that is there.
UNREPORTED_MODEL_VERSION = "unreported"

# Long enough to identify the cause, short enough that a provider returning an
# HTML error page cannot push a novel into the Episode's error_message column.
_ERROR_EXCERPT = 300


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


class HttpSttProvider:
    """Speech-to-text over HTTP, the deployment transport.

    One attempt per call, like the object store and AI Core: a retry is the job's
    decision, made with the attempt count and the backoff in view.

    The audio is the request body rather than a multipart part. A multipart form
    would put the provider's field naming into this service, and every provider
    names it differently; the body plus the content type is the part of the
    request every provider agrees on.
    """

    backend = HTTP_BACKEND

    def __init__(self, base_url: str, path: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.path = path
        self.timeout_seconds = timeout_seconds

    def transcribe(self, audio: bytes, content_type: str) -> Transcript:
        url = f"{self.base_url}/{self.path.lstrip('/')}"
        try:
            response = httpx.post(
                url,
                content=audio,
                headers={"Content-Type": content_type},
                timeout=httpx.Timeout(self.timeout_seconds),
            )
        except httpx.TimeoutException as error:
            raise SttTimeout(
                f"The speech-to-text provider did not answer within "
                f"{self.timeout_seconds}s"
            ) from error
        except httpx.TransportError as error:
            raise SttUnavailable(
                f"The speech-to-text provider is unreachable at {url}: {error}"
            ) from error

        if response.status_code >= 400:
            message = (
                f"The speech-to-text provider answered {response.status_code}: "
                f"{response.text[:_ERROR_EXCERPT]}"
            )
            # The same boundary AI Core keeps. A provider that answers 503 is one
            # that is not serving yet — a model server still loading, or a load
            # balancer with nothing healthy behind it — and it clears on its own,
            # so it is a retry rather than the end of the Episode. 504 is the same
            # judgement as a client-side timeout, reached the other way round.
            if response.status_code == 503:
                raise SttUnavailable(message)
            if response.status_code == 504:
                raise SttTimeout(message)
            raise SttFailed(message)

        try:
            body = response.json()
        except ValueError as error:
            raise SttFailed(
                f"The speech-to-text provider answered with something that is not "
                f"JSON: {response.text[:_ERROR_EXCERPT]}"
            ) from error

        if not isinstance(body, dict) or not isinstance(body.get("text"), str):
            raise SttFailed(
                "The speech-to-text provider answered without a 'text' string: "
                f"{str(body)[:_ERROR_EXCERPT]}"
            )

        model_version = body.get("model_version")
        return Transcript(
            text=body["text"],
            backend=self.backend,
            model_version=model_version
            if isinstance(model_version, str) and model_version
            else UNREPORTED_MODEL_VERSION,
        )


def build_stt_provider(settings: Settings) -> SttProvider:
    if settings.stt_backend == FAKE_BACKEND:
        refuse_fake_unless_permitted(settings, "speech-to-text")
        return FakeSttProvider()
    if settings.stt_backend == HTTP_BACKEND:
        return HttpSttProvider(
            settings.stt_url,
            settings.stt_path,
            settings.stt_timeout_seconds,
        )
    raise ValueError(f"Unsupported STT backend: {settings.stt_backend!r}")