"""Error taxonomy.

Every error that crosses the HTTP boundary carries a stable error_code. The codes
below are Backend-owned: the integration contract types error_code and
error_message as free strings, so adding a code is not a contract change, while
renaming a code the client branches on is a compatibility concern.

`retryable` is part of the taxonomy rather than a decision the worker makes per
call site: it says whether the same work might succeed later. A provider that is
unreachable is worth retrying; audio that is corrupt is not, and retrying it
would only delay the failure a client is waiting for.
"""

# Emitted for a malformed request rather than for a rejected operation, so it is
# also a constant: FastAPI raises RequestValidationError before any handler of
# ours runs.
REQUEST_INVALID = "REQUEST_INVALID"


class AppError(Exception):
    """Base class for errors that map to a stable code and an HTTP status."""

    code = "INTERNAL"
    http_status = 500
    retryable = False

    def __init__(self, message: str = "") -> None:
        self.message = message or self.code
        super().__init__(self.message)


class AuthRequired(AppError):
    """The request carried no usable actor credential."""

    code = "AUTH_REQUIRED"
    http_status = 401


class AuthInvalid(AppError):
    """The actor credential was presented but is not recognized."""

    code = "AUTH_INVALID"
    http_status = 401


class RequestInvalid(AppError):
    """The request is well-formed HTTP but is not an acceptable capture.

    Used at the boundary where it asks for more than the contract does — an
    upload without a consent reference or an idempotency key, for instance. The
    contract permits those fields to be absent; this service does not.
    """

    code = REQUEST_INVALID
    http_status = 422


class ActorNotFound(AppError):
    code = "ACTOR_NOT_FOUND"
    http_status = 404


class SubjectNotFound(AppError):
    code = "SUBJECT_NOT_FOUND"
    http_status = 404


class ConsentRequired(AppError):
    """A sensitive operation arrived without a consent reference."""

    code = "CONSENT_REQUIRED"
    http_status = 403


class ConsentInvalid(AppError):
    """A consent reference was supplied but does not authorize the operation."""

    code = "CONSENT_INVALID"
    http_status = 403


class ConsentNotFound(AppError):
    """No such consent record. Distinct from CONSENT_INVALID, which means it exists
    but does not authorize the operation being attempted."""

    code = "CONSENT_NOT_FOUND"
    http_status = 404


class AudioInvalid(AppError):
    """The uploaded audio is empty, or its content type is not audio."""

    code = "AUDIO_INVALID"
    http_status = 400


class AudioTooLarge(AppError):
    code = "AUDIO_TOO_LARGE"
    http_status = 413


class AudioUnavailable(AppError):
    """The audio an Episode points at could not be read from object storage.

    Retryable: an object store can be briefly inconsistent or briefly down, and
    the Episode is not lost either way. If it stays unavailable the job runs out
    of attempts and the Episode ends as failed with this code, which names the
    real problem instead of blaming the transcript.
    """

    code = "AUDIO_UNAVAILABLE"
    http_status = 503
    retryable = True


class StorageUnavailable(AppError):
    """Object storage refused the upload.

    Raised before the Episode is committed, so a failed upload leaves no Episode
    behind: the alternative — an Episode whose audio never arrived — would be a
    record that claims to hold something it does not have.
    """

    code = "STORAGE_UNAVAILABLE"
    http_status = 503
    retryable = True


class EpisodeNotFound(AppError):
    code = "EPISODE_NOT_FOUND"
    http_status = 404


class EpisodeNotReady(AppError):
    """The result was requested before the Episode finished processing.

    Distinct from EPISODE_NOT_FOUND so a client polling for a result can tell
    "not yet" from "never".
    """

    code = "EPISODE_NOT_READY"
    http_status = 409


class IdempotencyConflict(AppError):
    """The idempotency key was reused for different audio.

    The first request's Episode is the one that exists; this one is a client bug
    rather than a retry, and answering with the stored Episode would silently
    attach the wrong recording to the key.
    """

    code = "IDEMPOTENCY_CONFLICT"
    http_status = 409


class SttUnavailable(AppError):
    """No speech-to-text provider could be reached. Retrying may work."""

    code = "STT_UNAVAILABLE"
    http_status = 503
    retryable = True


class SttFailed(AppError):
    """The provider ran and could not produce a transcript for this audio."""

    code = "STT_FAILED"
    http_status = 502


class SttTimeout(AppError):
    """The speech-to-text provider did not answer in time. Retrying may work.

    Its own code rather than STT_UNAVAILABLE because the two call for different
    things: a provider that is unreachable is a provider to check, while one that
    is reachable but slower than the budget is a budget to raise.
    """

    code = "STT_TIMEOUT"
    http_status = 504
    retryable = True


class SttEmptyTranscript(AppError):
    """The provider returned an empty transcript: there is nothing to extract."""

    code = "STT_EMPTY_TRANSCRIPT"
    http_status = 422


class AiUnavailable(AppError):
    """AI Core could not be reached. Retrying may work."""

    code = "AI_UNAVAILABLE"
    http_status = 503
    retryable = True


class AiFailed(AppError):
    """AI Core ran and refused the request."""

    code = "AI_FAILED"
    http_status = 502


class AiTimeout(AppError):
    """AI Core did not answer in time. Retrying may work."""

    code = "AI_TIMEOUT"
    http_status = 504
    retryable = True


class AiSchemaInvalid(AppError):
    """AI Core answered with something that is not a valid aiCoreOutput.

    Not retryable: the same request would produce the same malformed answer, and
    writing it would put an unshapeable memory into the record.
    """

    code = "AI_SCHEMA_INVALID"
    http_status = 502