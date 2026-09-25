"""Exercise provisional Phase 2–4 paths after the real local audio service check.

The database and both Actor tokens are disposable and created by the wrapper.
This does not certify real-device, voice-clone, hardware or formal Legacy gates.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/backend"))

from app.models import Episode


def checked(response: httpx.Response, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise ValueError(f"{response.request.url.path}: expected {expected}, got {response.status_code}")
    return response.json()


def run() -> None:
    base = os.environ["PHASE1_BACKEND_URL"].rstrip("/")
    subject = os.environ["PHASE1_SUBJECT_ID"]
    owner = {"Authorization": f"Bearer {os.environ['PHASE1_ACTOR_TOKEN']}"}
    recipient = {"Authorization": f"Bearer {os.environ['IOS_RECIPIENT_TOKEN']}"}
    recipient_id = os.environ["IOS_RECIPIENT_ACTOR_ID"]
    engine = create_engine(os.environ["PHASE1_DATABASE_URL"])
    try:
        with Session(engine) as session:
            episode = session.scalar(
                select(Episode).where(
                    Episode.subject_id == subject, Episode.status == "ready"
                ).order_by(Episode.created_at.desc()).limit(1)
            )
            if episode is None:
                raise ValueError("No ready Episode remains after Phase 1 verification")
            episode_id = episode.episode_id
    finally:
        engine.dispose()

    subject_path = f"{base}/api/v1/subjects/{subject}"
    with httpx.Client(timeout=145) as client:
        memories = checked(client.get(subject_path + "/memories", headers=owner))
        items = [item for item in memories["items"] if item["episode_id"] == episode_id]
        if not items:
            raise ValueError("The verified Episode is absent from cross-Episode Memories")
        item = items[0]
        model = checked(client.get(subject_path + "/person-model", headers=owner))
        if item["memory_item_id"] not in model["source_memory_ids"]:
            raise ValueError("The persisted Memory is absent from the Person Model")
        graph = checked(client.get(subject_path + "/memory-graph", headers=owner))
        memory_node = f"memory:{item['memory_item_id']}"
        if not any(
            edge["source_id"] == memory_node
            and edge["target_id"] == f"episode:{episode_id}"
            and edge["relation"] == "CAPTURED_IN"
            for edge in graph["edges"]
        ):
            raise ValueError("The provenance graph lost the Memory-to-Episode edge")

        twin_consent = checked(client.post(
            base + "/api/v1/consents", headers=owner,
            json={"subject_id": subject, "scope": "CLOUD_TWIN"},
        ), 201)["consent_id"]
        question = item["content"][:1000]
        if len(question) < 2:
            question = "请问这条记忆是什么？"
        twin = checked(client.post(
            subject_path + "/twin/query", headers=owner,
            json={"question": question, "cloud_twin_consent_id": twin_consent},
        ))
        if twin["response_type"] not in {"ORIGINAL", "SIMULATION"}:
            raise ValueError("Twin response lacks an explicit Original/Simulation label")
        if twin["response_type"] == "ORIGINAL" and not twin["evidence"]:
            raise ValueError("An ORIGINAL Twin answer has no cited evidence")

        started = checked(client.post(
            subject_path + "/calibrations", headers=owner,
            json={"question": question, "cloud_twin_consent_id": twin_consent},
        ), 201)
        calibration_id = started["calibration_id"]
        if started["locked_answer"] != twin["answer"]:
            raise ValueError("Calibration did not lock the first Twin answer")
        answer_path = subject_path + f"/calibrations/{calibration_id}"
        completed = checked(client.post(
            answer_path + "/answer", headers=owner,
            json={
                "human_answer": item["content"],
                "gaps": {
                    "decision": False, "reasoning": False,
                    "value_priority": False, "emotional_reaction": False,
                    "expression": False,
                },
            },
        ))
        if completed["human_answer"] != item["content"]:
            raise ValueError("Human calibration answer was not persisted")
        assessed = checked(client.post(answer_path + "/assess", headers=owner))
        comparison = assessed.get("ai_assessment")
        if not comparison or comparison["model_version"].startswith("fixture-"):
            raise ValueError("Calibration did not persist a real, versioned assessment")
        checked(client.get(subject_path + "/capture-plan", headers=owner))

        handover_consent = checked(client.post(
            base + "/api/v1/consents", headers=owner,
            json={"subject_id": subject, "scope": "DIGITAL_HANDOVER"},
        ), 201)["consent_id"]
        grant = checked(client.post(
            subject_path + "/handover/grants", headers=owner,
            json={
                "recipient_actor_id": recipient_id,
                "handover_consent_id": handover_consent,
                "allowed_domains": [item["domain"]],
            },
        ), 201)
        grant_path = subject_path + f"/handover/grants/{grant['grant_id']}"
        if client.get(subject_path + "/legacy-preview/memories", headers=recipient).status_code != 404:
            raise ValueError("A draft grant exposed Memory to the Recipient")
        activated = checked(client.post(
            grant_path + "/activate-preview", headers=owner,
            json={"confirmation": "ACTIVATE_PREVIEW"},
        ))
        if activated["status"] != "PREVIEW_ACTIVE":
            raise ValueError("Preview did not activate")
        visible = checked(client.get(subject_path + "/legacy-preview/memories", headers=recipient))
        if item["memory_item_id"] not in {entry["memory_item_id"] for entry in visible["items"]}:
            raise ValueError("Explicit recipient grant did not expose the selected Memory")
        checked(client.post(grant_path + "/revoke", headers=owner))
        if client.get(subject_path + "/legacy-preview/memories", headers=recipient).status_code != 404:
            raise ValueError("Revocation did not cut off Recipient access")

    print(
        "ios-extended=verified person-model=source-linked graph=provenance "
        "twin=evidence-labelled calibration=real-model capture-plan=ready "
        "legacy-preview=revocable"
    )


if __name__ == "__main__":
    run()
