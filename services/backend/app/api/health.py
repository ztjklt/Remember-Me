import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..db import Database
from ..storage.base import ObjectStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness. Deliberately touches no dependency."""
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request) -> Any:
    """Readiness. Fails closed when a required dependency is unreachable."""
    components: dict[str, str] = {}

    components["database"] = _check_database(request.app.state.database)
    components["object_store"] = _check_object_store(request.app.state.object_store)

    unhealthy = sorted(name for name, state in components.items() if state != "ok")
    body = {
        "status": "unavailable" if unhealthy else "ready",
        "components": components,
    }
    if unhealthy:
        return JSONResponse(status_code=503, content=body)
    return body


def _check_database(database: Database) -> str:
    try:
        with database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - readiness reports any failure as unavailable
        logger.warning(
            "readiness.database.unavailable",
            extra={"extra_fields": {"error": str(exc)}},
        )
        return "unavailable"
    return "ok"


def _check_object_store(store: ObjectStore) -> str:
    try:
        store.healthcheck()
    except Exception as exc:  # noqa: BLE001 - readiness reports any failure as unavailable
        logger.warning(
            "readiness.object_store.unavailable",
            extra={"extra_fields": {"error": str(exc)}},
        )
        return "unavailable"
    return "ok"