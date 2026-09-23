import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)

# Uvicorn's plain-text access log is replaced by the structured middleware log.
_SUPERSEDED_LOGGERS = ("uvicorn.access",)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the active trace id attached."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        trace_id = trace_id_var.get()
        if trace_id is not None:
            payload["trace_id"] = trace_id

        payload.update(getattr(record, "extra_fields", {}))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())

    for name in _SUPERSEDED_LOGGERS:
        superseded = logging.getLogger(name)
        superseded.handlers[:] = []
        superseded.propagate = False