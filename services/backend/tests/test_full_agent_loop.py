"""HTTP capture -> durable model -> calibration -> another guided capture.

Semantic proposal fixtures isolate persistence/orchestration from model quality.
The live-model evaluation script covers the separate model-quality boundary.
"""
import json
from copy import deepcopy
from io import BytesIO
import math
import struct
import wave

from sqlalchemy import select

from app.ai_core import FakeAiCoreClient
from app.audio_observation import PCMObserver
from app.models import CaptureQuestion, Episode, Evidence, MemoryItem, PersonTrait
from app.repositories.person_model import PersonModelRepository
from app.retrieval import retrieve
from app.seed import seed_development_data
from app.worker import ProcessingWorker
from test_twin_voice import QuoteTwin, TinyEncoder


class SemanticProposals(FakeAiCoreClient):
    def __init__(self):
        self.action = "ADD"
        self.fail = False
        self.context = None
        self.domain = "PREFERENCES"

    def process(self, payload):
        from app.errors import AiUnavailable
        if self.fail:
            raise AiUnavailable("reflection unavailable")
        self.context = deepcopy(payload.subject_context)
        result = super().process(payload)
        for evidence in result.evidence:
            evidence.span_start = 0
            evidence.span_end = len(payload.transcript)
            evidence.source_ref = f"episode:{payload.episode_id}#span:0-{len(payload.transcript)}"
        for memory in result.memory_items:
            memory.content = payload.transcript
            memory.memory_type = "PREFERENCE"
            memory.confidence = .55
            target = next(iter(self.context["current_traits"]), None)
            if self.action != "ADD":
                assert target
            memory.metadata = {"domain": self.domain, "reflection": {
                "input_statement": memory.content, "action": self.action, "context": None,
                "target": target if self.action != "ADD" else None},
                "facets": [{"category": "filter", "label": "回忆视角", "quote": payload.transcript,
                            "evidence_ids": memory.evidence_ids}]}
        return result


def capture(client, app, own, headers, key, text, metadata=None, expect_ready=True):
    data = {"subject_id": own.subject_id, "recording_consent_id": own.consent_id,
            "idempotency_key": key, "source": "IOS_MIC", "recorded_at": "2026-10-08T09:00:00Z", "audio_ref": key + ".m4a"}
    if metadata:
        data["metadata"] = json.dumps(metadata)
    response = client.post("/api/v1/episodes", headers=headers, data=data,
                           files={"file": (key + ".m4a", b"SYNTHETIC-LOOP-" + key.encode(), "audio/mp4")})
    assert response.status_code == 201, response.text
    identifier = response.json()["episode_id"]
    worker = ProcessingWorker(app.state.database, app.state.object_store, app.state.stt_provider,
                              app.state.ai_client, max_attempts=1, backoff_seconds=0)
    worker.run_once()
    assert client.patch(f"/api/v1/episodes/{identifier}/transcript-review", headers=headers,
                        json={"transcript": text}).status_code == 200
    worker.run_once(); worker.run_once()
    assert client.get(f"/api/v1/episodes/{identifier}", headers=headers).json()["status"] == ("ready" if expect_ready else "failed")
    return identifier


def own_data(session):
    own = seed_development_data(session, subject_name="Own", actor_name="Own")
    return own, {"Authorization": "Bearer " + own.actor_token}


def test_support_conflict_clarification_and_rebuild_survive_restart(app, client, session):
    own, headers = own_data(session)
    ai = SemanticProposals(); app.state.ai_client = ai
    base = f"/api/v1/subjects/{own.subject_id}"
    capture(client, app, own, headers, "first", "我喜欢咖啡。")
    model = client.get(base + "/person-model", headers=headers).json()
    first = next(d["traits"][0] for d in model["domains"] if d["traits"])
    ai.action = "SUPPORT"
    capture(client, app, own, headers, "support", "我还是喜欢咖啡。")
    current = next(d["traits"][0] for d in client.get(base + "/person-model", headers=headers).json()["domains"] if d["traits"])
    assert current["trait_id"] == first["trait_id"]
    assert len(current["memory_item_ids"]) == len(current["evidence_ids"]) == 2
    ai.action = "CONFLICT"
    capture(client, app, own, headers, "conflict", "我不喜欢咖啡。")
    questions = client.get(base + "/questions", headers=headers).json()["items"]
    assert questions[0]["reason"] == "contradiction"
    ai.action = "CHANGE"
    capture(client, app, own, headers, "clarify", "以前喜欢咖啡，现在只喜欢茶。", {"question_id": questions[0]["question_id"]})
    # Reopen a DB session and replay the durable source records, as after restart.
    with app.state.database.session() as reopened:
        PersonModelRepository(reopened).rebuild(own.subject_id)
        reopened.commit()
    after = client.get(base + "/person-model", headers=headers).json()
    traits = next(d["traits"] for d in after["domains"] if d["domain"] == "PREFERENCES")
    assert [t["statement"] for t in traits if t["status"] == "active"] == ["以前喜欢咖啡，现在只喜欢茶。"]
    assert sum(t["status"] == "superseded" for t in traits) == 2
    assert all(t.get("valid_to") for t in traits if t["status"] == "superseded")
    assert not any(q["reason"] == "contradiction" for q in client.get(base + "/questions", headers=headers).json()["items"])
    # Current Twin retrieval excludes retired preferences; history remains accessible.
    with app.state.database.session() as reopened:
        current = retrieve(reopened, own.subject_id, "现在喜欢什么？", TinyEncoder())
        assert current and all("只喜欢茶" in row["statement"] for row in current)
        historical = retrieve(reopened, own.subject_id, "过去喜欢什么？", TinyEncoder())
        assert len(historical) > len(current)


def test_correction_delete_retire_auxiliary_metadata_and_stale_merge_links(app, client, session):
    own, headers = own_data(session)
    ai = SemanticProposals(); app.state.ai_client = ai
    capture(client, app, own, headers, "source", "我喜欢咖啡。")
    ai.action = "SUPPORT"
    capture(client, app, own, headers, "support", "我喜欢喝咖啡。")
    base = f"/api/v1/subjects/{own.subject_id}"
    memories = client.get(base + "/memories", headers=headers).json()["items"]
    source = next(m for m in memories if m["content"] == "我喜欢咖啡。")
    assert client.patch(base + "/memories/" + source["memory_item_id"], headers=headers,
                        json={"content": "是茶，不是咖啡。"}).status_code == 200
    items = client.get(f'/api/v1/episodes/{source["episode_id"]}/result', headers=headers).json()["memory_items"]
    assert "facets" not in items[0]["metadata"]
    traits = next(d["traits"] for d in client.get(base + "/person-model", headers=headers).json()["domains"] if d["domain"] == "PREFERENCES")
    assert len(traits) == 2  # Old snapshot no longer matches, never silently merges into corrected statement.
    assert client.delete(base + "/memories/" + source["memory_item_id"], headers=headers).status_code == 200
    traits = next(d["traits"] for d in client.get(base + "/person-model", headers=headers).json()["domains"] if d["domain"] == "PREFERENCES")
    assert len(traits) == 1 and len(traits[0]["evidence_ids"]) == 1


def test_reflection_failure_retries_same_confirmed_episode_and_creates_no_partial_model(app, client, session):
    own, headers = own_data(session)
    ai = SemanticProposals(); ai.fail = True; app.state.ai_client = ai
    identifier = capture(client, app, own, headers, "retry", "我喜欢咖啡。", expect_ready=False)
    with app.state.database.session() as current:
        assert not list(current.scalars(select(PersonTrait).where(PersonTrait.subject_id == own.subject_id)))
        assert not list(current.scalars(select(MemoryItem).where(MemoryItem.episode_id == identifier)))
    ai.fail = False
    assert client.post(f"/api/v1/episodes/{identifier}/retry", headers=headers).status_code == 200
    worker = ProcessingWorker(app.state.database, app.state.object_store, app.state.stt_provider, ai, backoff_seconds=0)
    worker.run_once(); worker.run_once()
    assert client.get(f"/api/v1/episodes/{identifier}", headers=headers).json()["status"] == "ready"
    with app.state.database.session() as current:
        assert current.query(Episode).filter_by(subject_id=own.subject_id).count() == 1
        assert current.query(MemoryItem).filter_by(episode_id=identifier).count() == 1


class Compare:
    def compare(self, question, locked, human):
        names = ("DECISION", "REASONING", "VALUE_PRIORITY", "EMOTIONAL_REACTION", "EXPRESSION")
        return {"summary": "本人明确表达了新的选择，继续核对语境。", "model_version": "comparison-test-v1",
                "dimensions": [{"dimension": name, "alignment": "DIFFERENT" if name == "VALUE_PRIORITY" else "NOT_OBSERVED",
                                "note": "本人明确变化" if name == "VALUE_PRIORITY" else "证据不足",
                                "human_excerpt": human if name == "VALUE_PRIORITY" else None} for name in names],
                "suggested_question": "现在选茶时，你最看重什么？"}


def test_locked_calibration_automatically_plans_next_capture_without_learning_its_diagnostic(app, client, session):
    own, headers = own_data(session)
    ai = SemanticProposals(); app.state.ai_client = ai
    capture(client, app, own, headers, "first", "我喜欢咖啡。")
    app.state.settings.ai_backend = "http"
    app.state.embedding_encoder = TinyEncoder(); app.state.twin_client = QuoteTwin(); app.state.calibration_client = Compare()
    cloud = client.post("/api/v1/consents", headers=headers, json={"subject_id": own.subject_id, "scope": "CLOUD_TWIN"}).json()["consent_id"]
    base = f"/api/v1/subjects/{own.subject_id}"
    twin = client.post(base + "/twin/answers", headers=headers, json={"question": "喜欢喝什么？", "cloud_consent_id": cloud}).json()
    locked = client.post(base + "/calibrations", headers=headers,
                         json={"twin_answer_id": twin["answer_id"], "cloud_consent_id": cloud}).json()
    ai.action = "CHANGE"
    human = capture(client, app, own, headers, "human", "以前喜欢咖啡，现在喜欢茶。", {"calibration_id": locked["calibration_id"]})
    assert ai.context["calibration_question"] == twin["question"]
    result = client.post(base + f'/calibrations/{locked["calibration_id"]}/complete', headers=headers,
                         json={"cloud_consent_id": cloud})
    assert result.status_code == 200, result.text
    assert result.json()["locked_answer"] == locked["locked_answer"]
    assert len(result.json()["dimensions"]) == 5
    questions = client.get(base + "/questions", headers=headers).json()["items"]
    followup = next(q for q in questions if q["reason"] == "calibration_gap")
    assert followup["text"] == "现在选茶时，你最看重什么？"
    with app.state.database.session() as current:
        assert all(m.content != result.json()["summary"] for m in current.scalars(select(MemoryItem)))
    # Replay returns the same result and doesn't append another question.
    again = client.post(base + f'/calibrations/{locked["calibration_id"]}/complete', headers=headers, json={"cloud_consent_id": cloud})
    assert again.json() == result.json()
    assert client.get(base + "/questions", headers=headers).json()["items"] == questions
    ai.action = "ADD"
    ai.domain = "VALUES_BELIEFS"
    capture(client, app, own, headers, "follow-up", "选茶时最看重温和。", {"question_id": followup["question_id"]})
    session.expire_all()
    assert session.get(CaptureQuestion, followup["question_id"]).status == "answered"


def test_pcm_observations_describe_real_signal_and_unknown_formats_degrade():
    stream = BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        values = [int(8000 * math.sin(2 * math.pi * 440 * n / 16000)) if n < 8000 else 0 for n in range(16000)]
        wav.writeframes(struct.pack("<" + "h" * len(values), *values))
    observed = PCMObserver().observe(stream.getvalue())
    assert observed["status"] == "available"
    assert observed["analyzed_seconds"] == 1
    assert -.01 < observed["silence_fraction"] - .5 < .01
    assert -20 < observed["rms_dbfs"] < -15
    assert observed["interpretation"] == "signal_only"
    assert PCMObserver().observe(b"synthetic-not-audio")["status"] == "unavailable"


def test_answer_cannot_commit_after_source_is_corrected_during_model_call(app, client, session):
    own, headers = own_data(session)
    app.state.ai_client = SemanticProposals()
    capture(client, app, own, headers, "initial", "我喜欢咖啡。")
    app.state.settings.ai_backend = "http"; app.state.embedding_encoder = TinyEncoder()
    base = f"/api/v1/subjects/{own.subject_id}"
    cloud = client.post("/api/v1/consents", headers=headers, json={"subject_id": own.subject_id, "scope": "CLOUD_TWIN"}).json()["consent_id"]
    memory = client.get(base + "/memories", headers=headers).json()["items"][0]
    class RacingTwin(QuoteTwin):
        def answer(self, question, candidates):
            changed = client.patch(base + "/memories/" + memory["memory_item_id"], headers=headers, json={"content": "我喜欢茶"})
            assert changed.status_code == 200
            return super().answer(question, candidates)
    app.state.twin_client = RacingTwin()
    response = client.post(base + "/twin/answers", headers=headers, json={"question": "喜欢什么？", "cloud_consent_id": cloud})
    assert response.status_code == 503
    from app.models import TwinAnswer
    with app.state.database.session() as current:
        assert current.query(TwinAnswer).count() == 0


def test_third_party_paraphrase_never_becomes_subject_trait_or_twin_evidence(app, client, session):
    own, headers = own_data(session)
    app.state.ai_client = SemanticProposals()
    identifier = capture(client, app, own, headers, "third-party", "他说自己喜欢咖啡。")
    with app.state.database.session() as current:
        for source in current.scalars(select(Evidence).where(Evidence.episode_id == identifier)):
            source.source_type = "THIRD_PARTY"
        current.flush()
        PersonModelRepository(current).rebuild(own.subject_id)
        current.commit()
        assert not list(current.scalars(select(PersonTrait).where(PersonTrait.subject_id == own.subject_id)))
        assert retrieve(current, own.subject_id, "喜欢什么？", TinyEncoder()) == []


def test_deleting_only_answer_reopens_domain_without_erasing_answer_history(app, client, session):
    own, headers = own_data(session)
    ai = SemanticProposals(); app.state.ai_client = ai
    capture(client, app, own, headers, "first", "我喜欢咖啡。")
    base = f"/api/v1/subjects/{own.subject_id}"
    question = next(q for q in client.get(base + "/questions", headers=headers).json()["items"] if q["target_domain"] == "IDENTITY")
    ai.domain = "IDENTITY"
    answer = capture(client, app, own, headers, "answer", "我叫小林。", {"question_id": question["question_id"]})
    session.expire_all()
    assert session.get(CaptureQuestion, question["question_id"]).status == "answered"
    memory = next(m for m in client.get(base + "/memories", headers=headers).json()["items"] if m["episode_id"] == answer)
    assert client.delete(base + "/memories/" + memory["memory_item_id"], headers=headers).status_code == 200
    next_questions = client.get(base + "/questions", headers=headers).json()["items"]
    assert any(q["target_domain"] == "IDENTITY" and q["reason"] == "missing_domain" for q in next_questions)
    session.expire_all()
    assert session.get(CaptureQuestion, question["question_id"]).status == "answered"


def test_explicit_past_context_cannot_answer_current_preference(app, client, session):
    own, headers = own_data(session)
    app.state.ai_client = SemanticProposals()
    capture(client, app, own, headers, "past", "以前我喜欢咖啡。")
    with app.state.database.session() as current:
        assert retrieve(current, own.subject_id, "现在喜欢什么？", TinyEncoder()) == []
        assert retrieve(current, own.subject_id, "以前喜欢什么？", TinyEncoder())


def test_explicit_opposite_statement_cannot_accumulate_as_support(app, client, session):
    own, headers = own_data(session)
    ai = SemanticProposals(); app.state.ai_client = ai
    capture(client, app, own, headers, "first", "我喜欢咖啡。")
    ai.action = "SUPPORT"  # Deliberately wrong semantic worker proposal.
    capture(client, app, own, headers, "opposite", "我不喜欢咖啡。")
    with app.state.database.session() as current:
        traits = list(current.scalars(select(PersonTrait).where(PersonTrait.subject_id == own.subject_id)))
        assert len(traits) == 2 and all(t.status == "unresolved" for t in traits)
        assert all(t.counter_evidence_ids for t in traits)
