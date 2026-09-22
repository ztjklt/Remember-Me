from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_is_liveness_only(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_needs_no_dependency(settings: Settings):
    """Liveness must answer even when the configured dependencies are unreachable."""
    unreachable = settings.model_copy(
        update={"database_url": "sqlite:////nonexistent-remember-me-directory/db.sqlite"}
    )

    with TestClient(create_app(unreachable)) as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_ready_reports_every_component(client: TestClient):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "components": {"database": "ok", "object_store": "ok"},
    }


def test_ready_fails_closed_when_the_database_is_unreachable(settings: Settings):
    unreachable = settings.model_copy(
        update={"database_url": "sqlite:////nonexistent-remember-me-directory/db.sqlite"}
    )

    with TestClient(create_app(unreachable)) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["components"]["database"] == "unavailable"
    assert body["components"]["object_store"] == "ok"