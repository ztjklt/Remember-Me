from fastapi.testclient import TestClient

from app.ai_core import HttpAiCoreClient
from app.config import Settings
from app.main import create_app
from app.stt import HttpSttProvider


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


def test_a_deployed_environment_starts_on_its_real_providers(settings: Settings, database_url: str):
    """Issue #41's "the second environment can start", with the fakes gone.

    Staging is where a placeholder provider is refused, so an environment that can
    only be brought up with one cannot be brought up at all — and the fake is the
    default, which makes that the likely case rather than the unlikely one. Here
    the configuration names the real transports, and the process builds, answers
    liveness, and reports ready without a placeholder anywhere in it.
    """
    deployed = settings.model_copy(
        update={
            "environment": "staging",
            "stt_backend": "http",
            "ai_backend": "http",
            # The migrations the `database_url` fixture applies are what `/ready`
            # reaches for; the point here is the configuration, not the schema.
            "database_url": database_url,
        }
    )
    app = create_app(deployed)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200

    assert isinstance(app.state.stt_provider, HttpSttProvider)
    assert isinstance(app.state.ai_client, HttpAiCoreClient)