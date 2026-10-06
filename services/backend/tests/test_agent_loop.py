"""Consumer integration tests against an actual AI Core HTTP process, no AI adapter stub."""

from pathlib import Path
from dataclasses import dataclass
import json
import os
import socket
import subprocess
import time
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.config import Settings
from app.main import create_app
from app.models import Evidence, AgentState, Consent, utcnow
from app.seed import seed_development_data
from app.worker import ProcessingWorker
from app.stt import Transcript
from conftest import upgrade_to_head

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def ai_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = os.environ.copy()
    env.update(
        AI_AGENT_ENABLED="true",
        AI_PROVIDER="fixture",
        AI_MODEL="fixture-ai-v2",
        AI_MODEL_VERSION="fixture-ai-v2",
        AI_ENVIRONMENT="test",
        REMEMBER_ENVIRONMENT="test",
    )
    # Do not let optional user credentials/provider settings alter the fixture process.
    for key in ("AI_BASE_URL", "AI_API_KEY"):
        env.pop(key, None)
    process = subprocess.Popen(
        [
            str(ROOT / "services/ai-core/.venv/bin/python"),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT / "services/ai-core",
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                if httpx.get(url + "/health", timeout=0.5).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if process.poll() is not None:
                pytest.fail("AI Core process exited before health")
            time.sleep(0.05)
        else:
            pytest.fail("AI Core health timeout")
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class OfflineStt:
    """The only offline provider in this integration test: opaque audio -> known transcript."""

    def transcribe(self, audio, content_type):
        return Transcript(
            text=audio.decode(),
            backend="fixture-stt",
            model_version="fixture-stt-test-v1",
        )


@dataclass
class Loop:
    app: object
    client: TestClient
    seed: object
    worker: ProcessingWorker
    headers: dict
    prefix: str

    def grant(self):
        return self.client.post(
            self.prefix + "/grant",
            headers=self.headers,
            json={
                "recording_consent_id": self.seed.consent_id,
                "cloud_twin_consent": True,
                "subject_single_speaker": True,
            },
        )

    def upload(self, text, key="first", self_speaker=True, process=True):
        response = self.client.post(
            "/api/v1/episodes",
            headers=self.headers,
            data={
                "subject_id": self.seed.subject_id,
                "recording_consent_id": self.seed.consent_id,
                "audio_ref": "offline-fixture.wav",
                "idempotency_key": key,
                "source": "ANDROID_MIC",
                "recorded_at": "2026-10-03T00:00:00Z",
                "metadata": json.dumps({"agent_subject_single_speaker": self_speaker}),
            },
            files={"file": ("offline-fixture.wav", text.encode(), "audio/wav")},
        )
        assert response.status_code == 201, response.text
        eid = response.json()["episode_id"]
        if process:
            for _ in range(3):
                assert self.worker.run_once() == eid
        return eid

    def post(self, path, body):
        return self.client.post(self.prefix + path, headers=self.headers, json=body)

    def get(self, path):
        return self.client.get(self.prefix + path, headers=self.headers)


@pytest.fixture
def loop(tmp_path, ai_url):
    config = Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        database_url=f"sqlite:///{tmp_path / 'loop.db'}",
        object_store_backend="memory",
        ai_backend="http",
        ai_core_url=ai_url,
        agent_enabled=True,
    )
    upgrade_to_head(config.database_url)
    app = create_app(config)
    with app.state.database.session() as session:
        seed = seed_development_data(
            session, subject_name="测试本人", actor_name="测试本人"
        )
    with TestClient(app) as client:
        yield Loop(
            app,
            client,
            seed,
            ProcessingWorker(
                app.state.database,
                app.state.object_store,
                OfflineStt(),
                app.state.ai_client,
                agent=app.state.agent_client,
            ),
            {"Authorization": "Bearer " + seed.actor_token},
            "/experimental/agent/v1/subjects/" + seed.subject_id,
        )


def test_record_memory_persona_twin_lock_calibrate_and_capture_cycle(loop):
    assert loop.grant().status_code == 200
    eid = loop.upload("工作日下班后我喜欢一个人待着。")
    result = loop.client.get(f"/api/v1/episodes/{eid}/result", headers=loop.headers)
    assert result.status_code == 200
    assert result.json()["memory_items"][0]["model_version"].startswith("fixture-ai-")
    model = loop.get("/model").json()
    assert model["revision"] == 1 and model["traits"]
    question = "工作日下班后喜欢怎么度过？"
    answer = loop.post("/twin", {"question": question}).json()
    assert answer["response_type"] == "ORIGINAL"
    assert answer["answer"] == answer["evidence"][0]["excerpt"]
    locked = loop.post("/calibrations", {"question": question})
    assert locked.status_code == 201, locked.text
    lock = locked.json()
    assert lock["state"] == "LOCKED" and lock["comparison"] is None
    assert "human_answer" not in lock
    response = loop.post(
        f"/calibrations/{lock['calibration_id']}/submit",
        {
            "human_answer": "我现在喜欢先和家人聊聊天，再自己待一会儿。",
            "expected_revision": 1,
        },
    )
    assert response.status_code == 200, response.text
    completed = response.json()
    assert completed["state"] == "COMPLETED" and completed["resulting_revision"] == 2
    assert (
        completed["locked_answer"] == lock["locked_answer"]
        and completed["lock_digest"] == lock["lock_digest"]
    )
    assert len(completed["comparison"]["dimension_diffs"]) == 5
    again = loop.post(
        f"/calibrations/{lock['calibration_id']}/submit",
        {
            "human_answer": "我现在喜欢先和家人聊聊天，再自己待一会儿。",
            "expected_revision": 1,
        },
    )
    assert again.status_code == 200
    assert loop.get("/model").json()["revision"] == 2
    assert any(m["source_type"] == "CALIBRATION" for m in loop.get("/evidence").json())
    assert loop.get("/plan").json()["question"]
    loop.upload("周末我喜欢和家人一起吃饭。", key="next")
    updated = loop.get("/model").json()
    assert updated["revision"] == 3
    assert any(t["context"] == "周末" for t in updated["traits"])


def test_subject_actor_isolation_and_unknown_question(loop):
    loop.grant()
    loop.upload("工作日下班后我喜欢一个人待着。")
    unknown = loop.post("/twin", {"question": "出生日期是什么？"}).json()
    assert unknown["response_type"] == "INSUFFICIENT" and not unknown["evidence"]
    with loop.app.state.database.session() as session:
        other = seed_development_data(
            session, subject_name="另一个人", actor_name="另一个人"
        )
    assert (
        loop.client.get(
            loop.prefix + "/model",
            headers={"Authorization": "Bearer " + other.actor_token},
        ).status_code
        == 404
    )
    other_prefix = "/experimental/agent/v1/subjects/" + other.subject_id
    assert (
        loop.client.get(other_prefix + "/model", headers=loop.headers).status_code
        == 404
    )
    assert loop.client.get(loop.prefix + "/model").status_code == 401


def test_reapply_completed_calibration_previews_and_appends_revision(loop):
    from app.agent_service import AgentService

    loop.grant()
    eid = loop.upload("工作日下班后我喜欢一个人待着。")
    locked = loop.post("/calibrations", {"question": "下班后喜欢做什么？"}).json()
    submitted = loop.post(f"/calibrations/{locked['calibration_id']}/submit",
        {"human_answer": "我喜欢先和家人聊天。", "expected_revision": 1}).json()
    assert submitted["state"] == "COMPLETED"
    original_result = loop.client.get(f"/api/v1/episodes/{eid}/result", headers=loop.headers).json()
    with loop.app.state.database.session() as session:
        service = AgentService(session, loop.app.state.agent_client)
        state = service.require(loop.seed.subject_id, loop.seed.actor_id)
        preview = service.reapply_calibration(state, locked["calibration_id"], 2)
        assert preview.revision == 3 and state.revision == 2
        assert loop.get("/model").json()["revision"] == 2
        applied = service.reapply_calibration(state, locked["calibration_id"], 2, apply=True)
        assert applied.revision == 3 and state.revision == 3
    assert loop.get(f"/calibrations/{locked['calibration_id']}").json() == submitted
    assert loop.client.get(f"/api/v1/episodes/{eid}/result", headers=loop.headers).json() == original_result


@pytest.mark.parametrize("mode", ["stale", "incomplete", "foreign", "revoked", "withdrawn", "newer"])
def test_reapply_requires_current_authorization_and_completed_calibration(loop, mode):
    from app.agent_service import AgentConflict, AgentNotFound, AgentService
    from app.errors import ConsentInvalid

    loop.grant()
    eid = loop.upload("工作日下班后我喜欢一个人待着。")
    locked = loop.post("/calibrations", {"question": "下班后喜欢做什么？"}).json()
    if mode != "incomplete":
        response = loop.post(f"/calibrations/{locked['calibration_id']}/submit",
            {"human_answer": "我喜欢先和家人聊天。", "expected_revision": 1})
        assert response.status_code == 200, response.text
    if mode == "newer":
        latest = loop.post("/calibrations", {"question": "下班后喜欢做什么？"}).json()
        response = loop.post(f"/calibrations/{latest['calibration_id']}/submit",
            {"human_answer": "我喜欢自己待着。", "expected_revision": 2})
        assert response.status_code == 200, response.text
    with loop.app.state.database.session() as session:
        service = AgentService(session, loop.app.state.agent_client)
        state = service.require(loop.seed.subject_id, loop.seed.actor_id)
        expected = state.revision
        calibration_id = locked["calibration_id"]
        error = AgentConflict
        if mode == "stale":
            expected -= 1
        elif mode == "foreign":
            calibration_id = "cal_another_subject"
            error = AgentNotFound
        elif mode == "revoked":
            service.revoke(state)
            error = ConsentInvalid
        elif mode == "withdrawn":
            service.withdraw_episode(state, eid)
            expected = state.revision
            error = ConsentInvalid
        with pytest.raises(error):
            service.reapply_calibration(state, calibration_id, expected, apply=True)


def test_no_persona_without_single_speaker_declaration(loop):
    loop.grant()
    loop.upload("我喜欢热闹。", self_speaker=False)
    assert loop.get("/model").json()["traits"] == []
    assert loop.get("/evidence").json() == []


def test_revoked_grant_and_withdrawn_episode_invalidate_derived_data(loop):
    loop.grant()
    eid = loop.upload("工作日下班后我喜欢一个人待着。")
    lock = loop.post("/calibrations", {"question": "下班后喜欢做什么？"}).json()
    withdrawn = loop.client.delete(
        loop.prefix + f"/episodes/{eid}/use", headers=loop.headers
    )
    assert withdrawn.status_code == 200 and not withdrawn.json()["traits"]
    assert loop.get(f"/calibrations/{lock['calibration_id']}").status_code == 403
    assert (
        loop.post("/twin", {"question": "下班后喜欢做什么？"}).json()["response_type"]
        == "INSUFFICIENT"
    )
    assert (
        loop.client.get(
            f"/api/v1/episodes/{eid}/result", headers=loop.headers
        ).status_code
        == 200
    )
    assert (
        loop.client.delete(loop.prefix + "/grant", headers=loop.headers).status_code
        == 204
    )
    assert loop.get("/model").status_code == 403
    assert loop.post("/twin", {"question": "下班后喜欢什么？"}).status_code == 403


def test_calibration_failure_preserves_lock_and_revision_conflicts(loop):
    loop.grant()
    loop.upload("我喜欢热闹。")
    locked = loop.post("/calibrations", {"question": "喜欢热闹吗？"}).json()
    cid = locked["calibration_id"]
    assert (
        loop.post(
            f"/calibrations/{cid}/submit",
            {"human_answer": "我喜欢安静。", "expected_revision": 0},
        ).status_code
        == 409
    )
    assert loop.get(f"/calibrations/{cid}").json()["state"] == "LOCKED"
    from app.errors import AiUnavailable

    class Unavailable:
        def compare(self, payload):
            raise AiUnavailable("provider unavailable")

    original = loop.app.state.agent_client
    loop.app.state.agent_client = Unavailable()
    assert (
        loop.post(
            f"/calibrations/{cid}/submit",
            {"human_answer": "我喜欢安静。", "expected_revision": 1},
        ).status_code
        == 503
    )
    loop.app.state.agent_client = original
    assert loop.get("/model").json()["revision"] == 1
    assert (
        loop.get(f"/calibrations/{cid}").json()["locked_answer"]
        == locked["locked_answer"]
    )


def test_memory_ids_are_stable_and_global_even_if_provider_reuses_ids(loop):
    loop.grant()
    first = loop.upload("我喜欢热闹。", key="a")
    second = loop.upload("我喜欢热闹。", key="b")
    a = loop.client.get(f"/api/v1/episodes/{first}/result", headers=loop.headers).json()
    b = loop.client.get(
        f"/api/v1/episodes/{second}/result", headers=loop.headers
    ).json()
    assert a["memory_items"][0]["evidence_ids"] != b["memory_items"][0]["evidence_ids"]
    with loop.app.state.database.session() as session:
        evidence = session.scalars(select(Evidence)).all()
        assert len({e.evidence_id for e in evidence}) == 2


def test_lock_rejects_human_answer_in_the_initial_request(loop):
    loop.grant()
    response = loop.post(
        "/calibrations",
        {"question": "我喜欢什么？", "human_answer": "不能泄露给初次预测"},
    )
    assert response.status_code == 422
    assert loop.get("/model").json()["revision"] == 0


def test_reported_third_party_opinion_never_becomes_subject_persona(loop):
    loop.grant()
    loop.upload("女儿说：我妈妈喜欢热闹。")
    assert loop.get("/model").json()["traits"] == []
    answer = loop.post("/twin", {"question": "妈妈喜欢热闹吗？"}).json()
    assert answer["response_type"] == "INSUFFICIENT"


def test_consent_revoked_during_twin_call_blocks_return_of_private_answer(loop):
    loop.grant()
    loop.upload("我喜欢热闹。")
    original = loop.app.state.agent_client

    class RevokeDuringCall:
        def twin(self, payload):
            answer = original.twin(payload)
            from app.agent_service import AgentService

            with loop.app.state.database.session() as session:
                state = session.get(
                    AgentState,
                    AgentService.key(loop.seed.subject_id, loop.seed.actor_id),
                )
                state.active = False
                state.generation = "revoked-during-call"
                session.commit()
            return answer

    loop.app.state.agent_client = RevokeDuringCall()
    response = loop.post("/twin", {"question": "喜欢热闹吗？"})
    assert response.status_code == 403
    assert "excerpt" not in response.json()


def test_compare_revocation_does_not_start_persona_worker(loop):
    loop.grant()
    loop.upload("我喜欢热闹。")
    locked = loop.post("/calibrations", {"question": "喜欢热闹吗？"}).json()
    original = loop.app.state.agent_client

    class RevokeDuringCompare:
        persona_called = False

        def compare(self, payload):
            result = original.compare(payload)
            from app.agent_service import AgentService

            with loop.app.state.database.session() as session:
                state = session.get(
                    AgentState,
                    AgentService.key(loop.seed.subject_id, loop.seed.actor_id),
                )
                state.active = False
                state.generation = "revoked-during-compare"
                session.commit()
            return result

        def persona(self, payload):
            self.persona_called = True
            return original.persona(payload)

    changed = RevokeDuringCompare()
    loop.app.state.agent_client = changed
    response = loop.post(
        f"/calibrations/{locked['calibration_id']}/submit",
        {"human_answer": "我喜欢安静。", "expected_revision": 1},
    )
    assert response.status_code == 403
    assert not changed.persona_called
    with loop.app.state.database.session() as session:
        from app.agent_service import AgentService

        assert (
            session.get(
                AgentState, AgentService.key(loop.seed.subject_id, loop.seed.actor_id)
            ).revision
            == 1
        )


def test_revision_compare_and_swap_never_overwrites_another_update(loop):
    loop.grant()
    loop.upload("我喜欢热闹。")
    from app.agent_service import AgentService, AgentConflict

    with (
        loop.app.state.database.session() as first,
        loop.app.state.database.session() as second,
    ):
        a = AgentService(first, loop.app.state.agent_client)
        b = AgentService(second, loop.app.state.agent_client)
        state_a = a.require(loop.seed.subject_id, loop.seed.actor_id)
        state_b = b.require(loop.seed.subject_id, loop.seed.actor_id)
        old_a = a.snapshot(state_a)
        old_b = b.snapshot(state_b)
        a.commit_snapshot(
            state_a, old_a.model_copy(update={"revision": 2}), a.materials(state_a)
        )
        first.commit()
        with pytest.raises(AgentConflict):
            b.commit_snapshot(
                state_b, old_b.model_copy(update={"revision": 2}), b.materials(state_b)
            )
        second.rollback()
    assert loop.get("/model").json()["revision"] == 2


def test_withdrawal_invalidates_calibration_material_and_derived_traits(loop):
    loop.grant()
    eid = loop.upload("我喜欢热闹。")
    lock = loop.post("/calibrations", {"question": "喜欢热闹吗？"}).json()
    assert (
        loop.post(
            f"/calibrations/{lock['calibration_id']}/submit",
            {"human_answer": "我现在喜欢安静。", "expected_revision": 1},
        ).status_code
        == 200
    )
    assert any(m["source_type"] == "CALIBRATION" for m in loop.get("/evidence").json())
    assert (
        loop.client.delete(
            loop.prefix + f"/episodes/{eid}/use", headers=loop.headers
        ).status_code
        == 200
    )
    assert not loop.get("/evidence").json()
    assert not loop.get("/model").json()["traits"]


def test_recording_consent_is_checked_before_forwarding_audio(loop):
    loop.grant()
    eid = loop.upload("我喜欢热闹。", process=False)

    class NeverCalled:
        def transcribe(self, audio, content_type):
            pytest.fail("revoked recording must not leave the worker")

    loop.worker.stt = NeverCalled()
    with loop.app.state.database.session() as session:
        consent = session.get(Consent, loop.seed.consent_id)
        consent.status = "revoked"
        consent.revoked_at = utcnow()
        session.commit()
    assert loop.worker.run_once() is None
    status = loop.client.get(f"/api/v1/episodes/{eid}", headers=loop.headers).json()
    assert status["status"] == "failed" and status["error_code"] == "CONSENT_INVALID"


def test_503_http_response_is_retried_by_existing_job_then_recovers(loop, monkeypatch):
    loop.grant()
    eid = loop.upload("我喜欢热闹。", process=False)
    assert loop.worker.run_once() == eid
    original = httpx.post
    failed = False

    def temporary(url, **kwargs):
        nonlocal failed
        if url.endswith("/process") and not failed:
            failed = True
            return httpx.Response(503, json={"error_code": "AI_UNAVAILABLE"})
        return original(url, **kwargs)

    monkeypatch.setattr(httpx, "post", temporary)
    loop.worker.backoff_seconds = 0
    assert loop.worker.run_once() is None
    status = loop.client.get(f"/api/v1/episodes/{eid}", headers=loop.headers).json()
    assert status["status"] == "extracting"
    assert loop.worker.run_once() == eid
    assert loop.worker.run_once() == eid
    assert loop.get("/model").json()["revision"] == 1


def test_evidence_resolver_is_subject_scoped_and_withdrawal_closes_it(loop):
    loop.grant()
    eid = loop.upload("我喜欢热闹。")
    source = loop.get("/evidence").json()[0]
    response = loop.get("/evidence/" + source["evidence_id"])
    assert response.status_code == 200 and response.json()["excerpt"] == "我喜欢热闹。"
    assert loop.get("/evidence/nonexistent").status_code == 404
    with loop.app.state.database.session() as session:
        other = seed_development_data(session, subject_name="b", actor_name="b")
    assert (
        loop.client.get(
            loop.prefix + "/evidence/" + source["evidence_id"],
            headers={"Authorization": "Bearer " + other.actor_token},
        ).status_code
        == 404
    )
    assert (
        loop.client.delete(
            loop.prefix + f"/episodes/{eid}/use", headers=loop.headers
        ).status_code
        == 200
    )
    assert loop.get("/evidence/" + source["evidence_id"]).status_code == 404


@pytest.mark.parametrize('has_span', [False, True])
def test_full_original_is_available_without_memory_evidence_coverage(loop, has_span):
    from sqlalchemy import delete
    from app.models import Episode, MemoryItem
    loop.grant()
    text = '周末我喜欢散步。我们团队有六人，来自物理、设计和计算机专业。'
    eid = loop.upload(text)
    with loop.app.state.database.session() as session:
        evidence = session.scalar(select(Evidence).where(Evidence.episode_id == eid))
        if has_span:
            excerpt = '周末我喜欢散步。'
            evidence.excerpt = excerpt
            evidence.span_start, evidence.span_end = 0, len(excerpt)
            evidence.source_ref = f'episode:{eid}#span:0-{len(excerpt)}'
        else:
            session.execute(delete(Evidence).where(Evidence.episode_id == eid))
        before = [(m.memory_item_id, m.content, m.evidence_ids) for m in session.scalars(
            select(MemoryItem).where(MemoryItem.episode_id == eid))]
        session.commit()
    sources = loop.get('/evidence').json()
    original = next(m for m in sources if m['excerpt'] == text)
    assert original['source_ref'] == f'episode:{eid}#span:0-{len(text)}'
    assert original['evidence_id'] in {m['evidence_id'] for m in loop.get('/evidence').json()}
    assert loop.post('/twin', {'question':'同行的人数和学科构成？'}).status_code == 200
    with loop.app.state.database.session() as session:
        assert session.get(Episode, eid).transcript == text
        assert [(m.memory_item_id, m.content, m.evidence_ids) for m in session.scalars(
            select(MemoryItem).where(MemoryItem.episode_id == eid))] == before
    loop.client.delete(loop.prefix + f'/episodes/{eid}/use', headers=loop.headers)
    assert not loop.get('/evidence').json()
