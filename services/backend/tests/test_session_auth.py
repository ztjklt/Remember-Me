from fastapi.testclient import TestClient

from app.seed import seed_development_data
from app.tokens import hash_actor_token


def test_a_valid_token_resolves_to_its_actor(client: TestClient, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")

    response = client.get(
        "/api/v1/session",
        headers={"Authorization": f"Bearer {seeded.actor_token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"actor_id": seeded.actor_id, "display_name": "Ada"}


def test_every_response_carries_a_request_id(client: TestClient):
    response = client.get("/api/v1/session")

    assert response.headers["X-Request-ID"]


def test_a_missing_credential_is_rejected(client: TestClient):
    response = client.get("/api/v1/session")

    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_REQUIRED"


def test_a_non_bearer_scheme_is_rejected(client: TestClient, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")

    response = client.get(
        "/api/v1/session",
        headers={"Authorization": f"Token {seeded.actor_token}"},
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_REQUIRED"


def test_an_unknown_token_is_rejected(client: TestClient):
    response = client.get(
        "/api/v1/session", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_INVALID"


def test_the_token_is_stored_only_as_a_digest(session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")

    from app.repositories.actors import ActorRepository

    actor = ActorRepository(session).require(seeded.actor_id)

    assert actor.token_hash == hash_actor_token(seeded.actor_token)
    assert actor.token_hash != seeded.actor_token


def test_a_deleted_actor_is_reported_as_not_found(session):
    from app.errors import ActorNotFound
    from app.repositories.actors import ActorRepository

    repository = ActorRepository(session)

    try:
        repository.require("actor_that_does_not_exist")
    except ActorNotFound as error:
        assert error.code == "ACTOR_NOT_FOUND"
    else:  # pragma: no cover - the call must raise
        raise AssertionError("require() should have raised ActorNotFound")