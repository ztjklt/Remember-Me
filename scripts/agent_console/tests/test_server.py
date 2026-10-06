import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from agent_console.server import attach_console


@pytest.fixture
def console(tmp_path):
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"actor_token": "local-test-token", "subject_id": "subject-test",
        "recording_consent_id": "consent-test", "private_extra": "must-stay-local"}))
    with TestClient(attach_console(FastAPI(), session, "fixture"), base_url="http://localhost") as client:
        yield client


def test_local_session_projects_only_client_credentials_and_disables_caching(console):
    response = console.get("/debug/agent/session")
    assert response.status_code == 200
    assert response.json() == {"mode": "fixture", "actor_token": "local-test-token",
        "subject_id": "subject-test", "recording_consent_id": "consent-test"}
    assert "must-stay-local" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


@pytest.mark.parametrize("headers", [{"Host": "attacker.test"}, {"Origin": "https://attacker.test"}])
def test_foreign_hosts_and_origins_cannot_read_demo_session(console, headers):
    response = console.get("/debug/agent/session", headers=headers)
    assert response.status_code == 403
    assert "local-test-token" not in response.text


def test_static_console_and_missing_credentials_are_explicit(console, tmp_path):
    page = console.get("/debug/agent/")
    assert page.status_code == 200 and "记忆原文" in page.text
    assert "local-test-token" not in page.text
    with TestClient(attach_console(FastAPI(), tmp_path / "missing.json", "configured"), base_url="http://localhost") as client:
        response = client.get("/debug/agent/session")
        assert response.status_code == 404
        assert str(tmp_path) not in response.text
