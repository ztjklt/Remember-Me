"""The consent boundary over HTTP.

The centre of this file is `test_recording_consent_cannot_authorize_a_voice_operation`:
it is Issue #9's definition of done, expressed as a request rather than as a note
in a document.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.seed import seed_development_data


@pytest.fixture
def seeded(session):
    return seed_development_data(session, subject_name="Ada", actor_name="Ada")


@pytest.fixture
def auth(seeded) -> dict[str, str]:
    return {"Authorization": f"Bearer {seeded.actor_token}"}


def grant(client: TestClient, auth, subject_id: str, scope: str, **extra) -> dict:
    response = client.post(
        "/api/v1/consents",
        headers=auth,
        json={"subject_id": subject_id, "scope": scope, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def authorize(client: TestClient, auth, subject_id: str, scope: str, consent_id) -> Response:
    return client.post(
        "/api/v1/consents/authorize",
        headers=auth,
        json={"subject_id": subject_id, "scope": scope, "consent_id": consent_id},
    )


def test_a_voice_grant_is_recorded_as_its_own_consent(client, session, seeded, auth):
    body = grant(
        client, auth, seeded.subject_id, "VOICE", evidence_ref="clinic-form-2026-09-21"
    )

    assert body["scope"] == "VOICE"
    assert body["status"] == "granted"
    assert body["subject_id"] == seeded.subject_id
    assert body["granted_by_actor_id"] == seeded.actor_id
    assert body["evidence_ref"] == "clinic-form-2026-09-21"
    assert body["consent_id"] != seeded.consent_id

    # The grant is a persisted record, not a response-only object.
    stored = client.get(f"/api/v1/consents/{body['consent_id']}", headers=auth)
    assert stored.status_code == 200
    assert stored.json()["consent_id"] == body["consent_id"]
    assert stored.json()["scope"] == "VOICE"
    assert stored.json()["status"] == "granted"
    assert stored.json()["evidence_ref"] == "clinic-form-2026-09-21"
    assert stored.json()["revoked_at"] is None


def test_a_timestamp_means_the_same_thing_when_it_is_read_back(client, seeded, auth):
    """A stored timestamp must not change meaning between backends.

    SQLite returns naive datetimes and PostgreSQL returns aware ones; the API
    answers UTC either way, so a client never has to know which backend it is
    talking to (ADR-0001 D3).
    """
    created = grant(client, auth, seeded.subject_id, "VOICE")

    stored = client.get(f"/api/v1/consents/{created['consent_id']}", headers=auth).json()
    authorized = authorize(
        client, auth, seeded.subject_id, "VOICE", created["consent_id"]
    ).json()

    for value in (created["granted_at"], stored["granted_at"], authorized["granted_at"]):
        moment = datetime.fromisoformat(value)
        assert moment.tzinfo is not None, value
        assert moment.utcoffset() == timedelta(0), value

    assert (
        datetime.fromisoformat(created["granted_at"])
        == datetime.fromisoformat(stored["granted_at"])
        == datetime.fromisoformat(authorized["granted_at"])
    )


def test_recording_consent_cannot_authorize_a_voice_operation(client, seeded, auth):
    """Issue #9's definition of done.

    The seeded RECORDING consent is active and belongs to the same subject. A VOICE
    operation naming it must be refused.
    """
    response = authorize(client, auth, seeded.subject_id, "VOICE", seeded.consent_id)

    assert response.status_code == 403
    assert response.json()["error_code"] == "CONSENT_INVALID"
    assert response.json()["request_id"]


def test_recording_consent_still_authorizes_recording(client, seeded, auth):
    """The positive control for the test above: the refusal is about scope."""
    response = authorize(client, auth, seeded.subject_id, "RECORDING", seeded.consent_id)

    assert response.status_code == 200
    body = response.json()
    assert body["authorized"] is True
    assert body["consent_id"] == seeded.consent_id
    assert body["scope"] == "RECORDING"


def test_a_voice_grant_authorizes_only_the_voice_scope(client, seeded, auth):
    consent_id = grant(client, auth, seeded.subject_id, "VOICE")["consent_id"]

    assert authorize(client, auth, seeded.subject_id, "VOICE", consent_id).status_code == 200

    response = authorize(client, auth, seeded.subject_id, "RECORDING", consent_id)
    assert response.status_code == 403
    assert response.json()["error_code"] == "CONSENT_INVALID"


def test_an_operation_without_a_consent_reference_is_refused(client, seeded, auth):
    response = authorize(client, auth, seeded.subject_id, "VOICE", None)

    assert response.status_code == 403
    assert response.json()["error_code"] == "CONSENT_REQUIRED"


def test_an_unregistered_scope_cannot_be_expressed(client, seeded, auth):
    """The API refuses to record a scope no verification rule could match."""
    response = client.post(
        "/api/v1/consents",
        headers=auth,
        json={"subject_id": seeded.subject_id, "scope": "SPEAKER_VERIFICATION"},
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "REQUEST_INVALID"
    assert response.json()["request_id"]


def test_a_grant_for_an_unknown_subject_is_rejected(client, auth):
    response = client.post(
        "/api/v1/consents",
        headers=auth,
        json={"subject_id": "subj_that_does_not_exist", "scope": "VOICE"},
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "SUBJECT_NOT_FOUND"


def test_the_granting_actor_comes_from_the_credential_not_the_body(client, session, seeded, auth):
    """A caller cannot attribute a grant to someone else.

    An attempt to name the grantor is refused outright, and no grant is created.
    """
    response = client.post(
        "/api/v1/consents",
        headers=auth,
        json={
            "subject_id": seeded.subject_id,
            "scope": "VOICE",
            "granted_by_actor_id": "actor_someone_else",
        },
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "REQUEST_INVALID"

    listed = client.get(
        f"/api/v1/consents?subject_id={seeded.subject_id}&scope=VOICE", headers=auth
    )
    assert listed.json() == []


def test_consents_are_listed_per_subject_and_can_be_filtered_by_scope(client, session, seeded, auth):
    grant(client, auth, seeded.subject_id, "VOICE")

    everything = client.get(f"/api/v1/consents?subject_id={seeded.subject_id}", headers=auth)
    assert everything.status_code == 200
    assert {consent["scope"] for consent in everything.json()} == {"RECORDING", "VOICE"}

    voice_only = client.get(
        f"/api/v1/consents?subject_id={seeded.subject_id}&scope=VOICE", headers=auth
    )
    assert [consent["scope"] for consent in voice_only.json()] == ["VOICE"]


def test_revoking_a_grant_stops_it_authorizing_and_keeps_the_record(client, seeded, auth):
    consent_id = grant(client, auth, seeded.subject_id, "VOICE")["consent_id"]

    revoked = client.post(f"/api/v1/consents/{consent_id}/revoke", headers=auth)

    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert revoked.json()["revoked_at"] is not None

    assert authorize(client, auth, seeded.subject_id, "VOICE", consent_id).status_code == 403

    # The record remains, and so does the record of who granted it.
    stored = client.get(f"/api/v1/consents/{consent_id}", headers=auth)
    assert stored.status_code == 200
    assert stored.json()["revoked_at"] is not None


def test_an_unknown_consent_is_reported_as_not_found(client, auth):
    response = client.get("/api/v1/consents/consent_that_does_not_exist", headers=auth)

    assert response.status_code == 404
    assert response.json()["error_code"] == "CONSENT_NOT_FOUND"


def test_the_consent_boundary_requires_an_actor(client, seeded):
    for method, path, body in (
        ("post", "/api/v1/consents", {"subject_id": seeded.subject_id, "scope": "VOICE"}),
        ("post", "/api/v1/consents/authorize", {"subject_id": seeded.subject_id, "scope": "VOICE"}),
        ("get", f"/api/v1/consents/{seeded.consent_id}", None),
        ("post", f"/api/v1/consents/{seeded.consent_id}/revoke", None),
    ):
        response = client.request(method.upper(), path, json=body)
        assert response.status_code == 401, f"{method} {path}"
        assert response.json()["error_code"] == "AUTH_REQUIRED"