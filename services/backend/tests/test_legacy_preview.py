"""Recipient previews enforce independent consent, scope and snapshot freeze."""

from app.models import Actor, MemoryItem as MemoryRow
from app.seed import seed_development_data
from app.tokens import generate_actor_token, hash_actor_token
from test_core_twin import _ready_episode


def test_recipient_preview_is_scoped_frozen_and_revocable(client, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    owner_auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    episode = _ready_episode(client, session, seeded, owner_auth)
    recipient_token = generate_actor_token()
    other_token = generate_actor_token()
    session.add_all([
        Actor(actor_id="recipient_one", display_name="Recipient", token_hash=hash_actor_token(recipient_token)),
        Actor(actor_id="unrelated_actor", display_name="Other", token_hash=hash_actor_token(other_token)),
    ])
    session.commit()
    recipient_auth = {"Authorization": f"Bearer {recipient_token}"}
    other_auth = {"Authorization": f"Bearer {other_token}"}
    grant_path = f"/api/v1/subjects/{seeded.subject_id}/handover/grants"
    recipient_path = f"/api/v1/subjects/{seeded.subject_id}/legacy-preview/memories"
    assert client.get(recipient_path, headers=recipient_auth).status_code == 404

    handover = client.post(
        "/api/v1/consents", headers=owner_auth,
        json={"subject_id": seeded.subject_id, "scope": "DIGITAL_HANDOVER"},
    )
    assert handover.status_code == 201
    consent_id = handover.json()["consent_id"]
    request = {
        "recipient_actor_id": "recipient_one",
        "handover_consent_id": consent_id,
        "allowed_domains": ["Preferences"],
    }
    assert client.post(
        grant_path, headers=other_auth, json=request,
    ).status_code == 404  # another Actor does not own a ready Episode
    draft = client.post(grant_path, headers=owner_auth, json=request)
    assert draft.status_code == 201, draft.text
    grant_id = draft.json()["grant_id"]
    assert draft.json()["status"] == "DRAFT"
    assert client.get(recipient_path, headers=recipient_auth).status_code == 404
    activate = f"{grant_path}/{grant_id}/activate-preview"
    assert client.post(
        activate, headers=other_auth, json={"confirmation": "ACTIVATE_PREVIEW"},
    ).status_code == 404
    assert client.post(
        activate, headers=owner_auth, json={"confirmation": "wrong"},
    ).status_code == 422
    active = client.post(
        activate, headers=owner_auth, json={"confirmation": "ACTIVATE_PREVIEW"},
    )
    assert active.status_code == 200, active.text
    assert active.json()["status"] == "PREVIEW_ACTIVE"
    assert active.json()["snapshot_count"] == 1
    assert client.get(recipient_path, headers=recipient_auth).json()["items"][0]["content"] == "我喜欢咖啡。"
    assert client.get(recipient_path, headers=other_auth).status_code == 404

    # New Memory does not join the already frozen preview.
    session.add(MemoryRow(
        memory_item_id="mi_after_snapshot", episode_id=episode.episode_id,
        ordinal=1, memory_type="PREFERENCE", content="我喜欢茶。",
        source_type="SUBJECT", evidence_ids=["ev_ios_1"], confidence=0.9,
        model_version="real-model-1", prompt_version="memory-extractor-v2",
        schema_version="integration-contract-v0.1",
    ))
    session.commit()
    assert len(client.get(recipient_path, headers=recipient_auth).json()["items"]) == 1

    original_id = client.get(
        f"/api/v1/subjects/{seeded.subject_id}/memories", headers=owner_auth,
    ).json()["items"][0]["memory_item_id"]
    correction = f"/api/v1/subjects/{seeded.subject_id}/memories/{original_id}/correction"
    assert client.put(
        correction, headers=owner_auth, json={"proposed_content": "我不喜欢咖啡。"},
    ).status_code == 200
    assert client.get(recipient_path, headers=recipient_auth).json()["items"] == []
    assert client.delete(correction, headers=owner_auth).status_code == 204
    assert len(client.get(recipient_path, headers=recipient_auth).json()["items"]) == 1

    revoke = f"{grant_path}/{grant_id}/revoke"
    assert client.post(revoke, headers=other_auth).status_code == 404
    assert client.post(revoke, headers=owner_auth).json()["status"] == "REVOKED"
    assert client.get(recipient_path, headers=recipient_auth).status_code == 404
    assert client.post(
        activate, headers=owner_auth, json={"confirmation": "ACTIVATE_PREVIEW"},
    ).status_code == 409


def test_revoking_handover_consent_disables_active_preview(client, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    owner_auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    _ready_episode(client, session, seeded, owner_auth)
    token = generate_actor_token()
    session.add(Actor(actor_id="recipient_two", display_name="Recipient", token_hash=hash_actor_token(token)))
    session.commit()
    recipient_auth = {"Authorization": f"Bearer {token}"}
    consent_id = client.post(
        "/api/v1/consents", headers=owner_auth,
        json={"subject_id": seeded.subject_id, "scope": "DIGITAL_HANDOVER"},
    ).json()["consent_id"]
    path = f"/api/v1/subjects/{seeded.subject_id}/handover/grants"
    grant = client.post(path, headers=owner_auth, json={
        "recipient_actor_id": "recipient_two", "handover_consent_id": consent_id,
        "allowed_domains": ["Preferences"],
    }).json()
    client.post(
        f"{path}/{grant['grant_id']}/activate-preview", headers=owner_auth,
        json={"confirmation": "ACTIVATE_PREVIEW"},
    )
    recipient_path = f"/api/v1/subjects/{seeded.subject_id}/legacy-preview/memories"
    assert client.get(recipient_path, headers=recipient_auth).status_code == 200
    client.post(f"/api/v1/consents/{consent_id}/revoke", headers=owner_auth)
    assert client.get(recipient_path, headers=recipient_auth).status_code == 404
