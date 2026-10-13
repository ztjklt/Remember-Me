"""Request-local opaque correlation only; never a user identifier or payload."""
from contextvars import ContextVar

quote_trace_id = ContextVar('quote_trace_id', default=None)
