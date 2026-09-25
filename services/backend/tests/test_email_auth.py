from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import auth as auth_api
from app.models import Account, Actor, EmailChallenge, Episode, LoginSession, utcnow
from app.seed import seed_development_data


def login(client: TestClient, app, email: str) -> dict:
    started = client.post("/api/v1/auth/email/start", json={"email": email})
    assert started.status_code == 200
    code = app.state.mailer.messages[-1][1]
    verified = client.post("/api/v1/auth/email/verify", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text
    return verified.json()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_email_login_is_scoped_and_refresh_rotates(client, app, session):
    first = login(client, app, "First@Example.com")
    second = login(client, app, "second@example.com")
    assert first["subject_id"] != second["subject_id"]
    assert client.get("/api/v1/session", headers=auth(first["access_token"])).status_code == 200

    forbidden = client.post("/api/v1/consents", headers=auth(second["access_token"]), json={
        "subject_id": first["subject_id"], "scope": "RECORDING"
    })
    assert forbidden.status_code == 404
    own = client.post("/api/v1/consents", headers=auth(first["access_token"]), json={
        "subject_id": first["subject_id"], "scope": "RECORDING"
    })
    assert own.status_code == 201

    renewed = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert renewed.status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    assert client.get("/api/v1/session", headers=auth(first["access_token"])).status_code == 401
    current = renewed.json()
    assert client.post("/api/v1/auth/logout", headers=auth(current["access_token"])).status_code == 200
    assert client.get("/api/v1/session", headers=auth(current["access_token"])).status_code == 401


def test_email_code_is_single_use_and_refresh_expires(client, app, session):
    email = "single-use@example.com"
    assert client.post("/api/v1/auth/email/start", json={"email": email}).status_code == 200
    code = app.state.mailer.messages[-1][1]
    issued = client.post("/api/v1/auth/email/verify", json={"email": email, "code": code})
    assert issued.status_code == 200
    assert client.post("/api/v1/auth/email/verify", json={
        "email": email, "code": code
    }).status_code == 401
    record = session.scalar(select(LoginSession).where(
        LoginSession.actor_id == issued.json()["actor_id"]
    ))
    record.refresh_expires_at = utcnow() - timedelta(seconds=1)
    session.commit()
    assert client.post("/api/v1/auth/refresh", json={
        "refresh_token": issued.json()["refresh_token"]
    }).status_code == 401


def test_code_attempts_expiry_and_session_expiry(client, app, session):
    client.post("/api/v1/auth/email/start", json={"email": "test@example.com"})
    code = app.state.mailer.messages[-1][1]
    for _ in range(5):
        assert client.post("/api/v1/auth/email/verify", json={
            "email": "test@example.com", "code": "999999" if code != "999999" else "000000"
        }).status_code == 401
    assert client.post("/api/v1/auth/email/verify", json={
        "email": "test@example.com", "code": code
    }).status_code == 401
    session.expire_all()
    challenge = session.get(EmailChallenge, "test@example.com")
    challenge.last_sent_at = utcnow() - timedelta(minutes=2)
    session.commit()
    logged = login(client, app, "test@example.com")
    record = session.scalar(select(LoginSession).where(LoginSession.actor_id == logged["actor_id"]))
    record.access_expires_at = utcnow() - timedelta(seconds=1)
    session.commit()
    assert client.get("/api/v1/session", headers=auth(logged["access_token"])).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={
        "refresh_token": logged["refresh_token"]
    }).status_code == 200


def test_code_hash_fits_declared_column(client, app, session):
    assert client.post("/api/v1/auth/email/start", json={
        "email": "length@example.com"
    }).status_code == 200
    challenge = session.get(EmailChallenge, "length@example.com")
    assert len(challenge.code_hash) <= EmailChallenge.__table__.c.code_hash.type.length
    assert ":" in challenge.code_hash


def test_episode_list_and_transcript_are_private_and_transcript_waits_for_stt(
    client, app, session
):
    first = login(client, app, "recorder@example.com")
    second = login(client, app, "stranger@example.com")
    consent = client.post("/api/v1/consents", headers=auth(first["access_token"]), json={
        "subject_id": first["subject_id"], "scope": "RECORDING"
    })
    assert consent.status_code == 201
    created = client.post(
        "/api/v1/episodes", headers=auth(first["access_token"]),
        data={
            "subject_id": first["subject_id"],
            "recording_consent_id": consent.json()["consent_id"],
            "source": "IMPORT", "recorded_at": "2026-09-25T09:30:00+00:00",
            "audio_ref": "hello.wav", "idempotency_key": "account-capture-1",
        },
        files={"file": ("hello.wav", b"RIFF\x00\x00\x00\x00WAVEfmt ", "audio/wav")},
    )
    assert created.status_code == 201, created.text
    episode_id = created.json()["episode_id"]
    path = f"/api/v1/episodes/{episode_id}/transcript"
    assert client.get(path, headers=auth(first["access_token"])).status_code == 409
    own_list = client.get("/api/v1/episodes", headers=auth(first["access_token"]))
    assert own_list.status_code == 200
    assert [item["episode_id"] for item in own_list.json()] == [episode_id]
    assert own_list.json()[0]["has_transcript"] is False
    assert client.get("/api/v1/episodes", headers=auth(second["access_token"])).json() == []
    assert client.get(path, headers=auth(second["access_token"])).status_code == 404
    assert client.get(f"/api/v1/episodes/{episode_id}", headers=auth(second["access_token"])).status_code == 404

    episode = session.get(Episode, episode_id)
    episode.transcript = "我今天去公园散步。"
    episode.stt_backend = "http"
    episode.stt_model_version = "whisper-test"
    episode.status = "extracting"
    session.commit()
    visible = client.get(path, headers=auth(first["access_token"]))
    assert visible.status_code == 200
    assert visible.json()["transcript"] == "我今天去公园散步。"
    assert visible.json()["stt_model_version"] == "whisper-test"
    assert client.get("/api/v1/episodes", headers=auth(first["access_token"])).json()[0]["has_transcript"] is True
    assert client.get(path, headers=auth(second["access_token"])).status_code == 404


def test_claim_failure_rolls_back_identity_swap(client, app, session, monkeypatch):
    seeded = seed_development_data(session, subject_name="Original", actor_name="Original")
    logged = login(client, app, "rollback@example.com")

    def fail_to_issue_tokens(_session, _actor_id):
        raise RuntimeError("simulated token issuance failure")

    monkeypatch.setattr(auth_api, "_tokens", fail_to_issue_tokens)
    with pytest.raises(RuntimeError, match="simulated token issuance failure"):
        client.post("/api/v1/auth/claim", headers=auth(logged["access_token"]), json={
            "legacy_token": seeded.actor_token, "subject_id": seeded.subject_id
        })
    session.expire_all()
    account = session.get(Account, "rollback@example.com")
    assert account.actor_id == logged["actor_id"]
    assert account.subject_id == logged["subject_id"]
    assert session.get(Actor, logged["actor_id"]) is not None
    assert client.get("/api/v1/session", headers=auth(seeded.actor_token)).status_code == 200


def test_local_claim_preserves_old_actor_and_revokes_legacy_token(client, app, session):
    seeded = seed_development_data(session, subject_name="Original", actor_name="Original")
    logged = login(client, app, "owner@example.com")
    claimed = client.post("/api/v1/auth/claim", headers=auth(logged["access_token"]), json={
        "legacy_token": seeded.actor_token, "subject_id": seeded.subject_id
    })
    assert claimed.status_code == 200, claimed.text
    result = claimed.json()
    assert result["actor_id"] == seeded.actor_id
    assert result["subject_id"] == seeded.subject_id
    assert session.get(Account, "owner@example.com").actor_id == seeded.actor_id
    assert client.get("/api/v1/session", headers=auth(seeded.actor_token)).status_code == 401
    assert client.get("/api/v1/session", headers=auth(result["access_token"])).status_code == 200
