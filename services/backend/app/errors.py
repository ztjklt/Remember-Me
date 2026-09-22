"""Error taxonomy.

Every error that crosses the HTTP boundary carries a stable error_code. The codes
below are Backend-owned: the integration contract types error_code and
error_message as free strings, so adding a code is not a contract change, while
renaming a code the client branches on is a compatibility concern.

The ingest, STT, and AI Core codes in ADR-0001 D11 arrive with Issue #1. This
module currently implements the identity, consent, and HTTP-layer codes that
Issue #8's and Issue #9's boundaries need.
"""

# Emitted for a malformed request rather than for a rejected operation, so it is
# a constant rather than an exception class: FastAPI raises RequestValidationError
# before any handler of ours runs.
REQUEST_INVALID = "REQUEST_INVALID"


class AppError(Exception):
    """Base class for errors that map to a stable code and an HTTP status."""

    code = "INTERNAL"
    http_status = 500

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