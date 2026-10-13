"""A real Episode is the only source of Twin evidence; Voice has a separate gate."""

from sqlalchemy import select
import pytest

from app.models import CalibrationRun, Episode, Evidence, MemoryEmbedding, TwinAnswer, VoiceAsset, VoiceProfile
from app.seed import seed_development_data
from app.worker import ProcessingWorker


class TinyEncoder:
    version = "test-local-vector-v1"

    def encode(self, texts):
        return [[float("散步" in text), float("喜欢" in text), 1.0] for text in texts]


class QuoteTwin:
    def answer(self, question, candidates):
        evidence = candidates[0]["evidence"][0]
        return {"answer": evidence["excerpt"], "response_type": "ORIGINAL",
                "evidence_ids": [evidence["evidence_id"]], "confidence": 0.9,
                "model_version": "deepseek-flash-test"}


class BadTwin:
    def answer(self, question, candidates):
        return {"answer": "我从没说过的话", "response_type": "ORIGINAL",
                "evidence_ids": ["ev_forged"], "confidence": 1,
                "model_version": "deepseek-flash-test"}


class TinyVoice:
    def validate(self, sample):
        return {"duration_seconds": 8, "model_version": "qwen3-tts-test"}

    def synthesize(self, text, sample, transcript):
        return b"WAVE" + text.encode(), "qwen3-tts-test"


def _record(client, app, subject_id, recording_consent_id, headers):
    uploaded = client.post("/api/v1/episodes", headers=headers,
        data={"subject_id": subject_id, "recording_consent_id": recording_consent_id,
              "idempotency_key": "twin-real-episode", "source": "IOS_MIC",
              "recorded_at": "2026-09-26T09:00:00Z", "audio_ref": "own-voice.m4a"},
        files={"file": ("voice.m4a", b"OWN-AUDIO", "audio/mp4")})
    assert uploaded.status_code == 201, uploaded.text
    episode_id = uploaded.json()["episode_id"]
    worker = ProcessingWorker(app.state.database, app.state.object_store,
                              app.state.stt_provider, app.state.ai_client, backoff_seconds=0)
    worker.run_once()
    assert client.patch(f"/api/v1/episodes/{episode_id}/transcript-review", headers=headers,
                        json={"transcript": "我喜欢散步"}).status_code == 200
    worker.run_once()
    worker.run_once()
    with app.state.database.session() as session:
        for source in session.scalars(select(Evidence).where(Evidence.episode_id == episode_id)):
            source.source_type = "SUBJECT"
            source.excerpt = "我喜欢散步"
            source.span_start = 0
            source.span_end = len(source.excerpt)
        session.commit()
    return episode_id


def test_evidence_answer_is_scoped_and_invalidated_after_correction(app, client, session):
    own = seed_development_data(session, subject_name="Own", actor_name="Own")
    other = seed_development_data(session, subject_name="Other", actor_name="Other")
    headers = {"Authorization": "Bearer " + own.actor_token}
    _record(client, app, own.subject_id, own.consent_id, headers)
    app.state.embedding_encoder = TinyEncoder()
    app.state.twin_client = QuoteTwin()
    app.state.settings.ai_backend = "http"
    consent = client.post("/api/v1/consents", headers=headers,
                          json={"subject_id": own.subject_id, "scope": "CLOUD_TWIN"}).json()["consent_id"]
    path = f"/api/v1/subjects/{own.subject_id}/twin/answers"
    assert client.post(path, headers=headers,
                       json={"question": "喜欢什么？", "cloud_consent_id": "bad"}).status_code == 404
    assert client.post(f"/api/v1/subjects/{other.subject_id}/twin/answers", headers=headers,
                       json={"question": "喜欢什么？", "cloud_consent_id": consent}).status_code == 404
    result = client.post(path, headers=headers,
                         json={"question": "喜欢什么？", "cloud_consent_id": consent})
    assert result.status_code == 200, result.text
    answer = result.json()
    assert answer["response_type"] == "ORIGINAL"
    assert answer["answer"] == answer["evidence"][0]["excerpt"]
    assert answer["model_version"] == "deepseek-flash-test"
    # Question answering now uses complete effective text; the independent
    # local search endpoint still creates and invalidates its vector cache.
    assert client.get(f'/api/v1/subjects/{own.subject_id}/memory-search',
                      params={'q':'散步'}, headers=headers).status_code == 200
    assert session.scalar(select(MemoryEmbedding).where(MemoryEmbedding.subject_id == own.subject_id))
    app.state.twin_client = BadTwin()
    assert client.post(path, headers=headers,
                       json={"question": "喜欢什么？", "cloud_consent_id": consent}).status_code == 503
    memory = client.get(f"/api/v1/subjects/{own.subject_id}/memories", headers=headers).json()["items"][0]
    corrected = client.patch(f"/api/v1/subjects/{own.subject_id}/memories/{memory['memory_item_id']}",
                             headers=headers, json={"content": "我更喜欢游泳"})
    assert corrected.status_code == 200
    session.expire_all()
    assert session.get(TwinAnswer, answer["answer_id"]).invalidated_at is not None
    assert session.get(MemoryEmbedding, memory["memory_item_id"]) is None
    assert client.get(f"/api/v1/subjects/{own.subject_id}/twin/answers/{answer['answer_id']}",
                      headers=headers).json()["stale"] is True


def test_voice_enrollment_speech_cache_and_revocation(app, client, session):
    own = seed_development_data(session, subject_name="Own", actor_name="Own")
    headers = {"Authorization": "Bearer " + own.actor_token}
    _record(client, app, own.subject_id, own.consent_id, headers)
    app.state.embedding_encoder = TinyEncoder()
    app.state.twin_client = QuoteTwin()
    app.state.voice_client = TinyVoice()
    app.state.settings.ai_backend = "http"
    cloud = client.post("/api/v1/consents", headers=headers,
                        json={"subject_id": own.subject_id, "scope": "CLOUD_TWIN"}).json()["consent_id"]
    answer = client.post(f"/api/v1/subjects/{own.subject_id}/twin/answers", headers=headers,
                         json={"question": "喜欢什么？", "cloud_consent_id": cloud}).json()
    profile_path = f"/api/v1/subjects/{own.subject_id}/voice/profile"
    sample = {"sample": ("mine.m4a", b"ONLY-MY-VOICE", "audio/mp4")}
    assert client.post(profile_path, headers=headers,
                       data={"voice_consent_id": own.consent_id, "transcript": "是我", "own_voice_confirmed": "true"},
                       files=sample).status_code == 403
    voice = client.post("/api/v1/consents", headers=headers,
                        json={"subject_id": own.subject_id, "scope": "VOICE"}).json()["consent_id"]
    assert client.post(profile_path, headers=headers,
                       data={"voice_consent_id": voice, "transcript": "是我", "own_voice_confirmed": "false"},
                       files=sample).status_code == 404
    enrolled = client.post(profile_path, headers=headers,
                           data={"voice_consent_id": voice, "transcript": "是我", "own_voice_confirmed": "true"},
                           files=sample)
    assert enrolled.status_code == 200, enrolled.text
    speech_path = f"/api/v1/subjects/{own.subject_id}/twin/answers/{answer['answer_id']}/speech"
    first = client.post(speech_path, headers=headers)
    assert first.status_code == 200, first.text
    second = client.post(speech_path, headers=headers)
    assert first.json()["asset_id"] == second.json()["asset_id"]
    asset_id = first.json()["asset_id"]
    audio_path = f"/api/v1/subjects/{own.subject_id}/voice/assets/{asset_id}/audio"
    assert client.get(audio_path, headers=headers).content.startswith(b"WAVE")
    assert client.post(f"/api/v1/consents/{voice}/revoke", headers=headers).status_code == 200
    session.expire_all()
    retired = session.scalar(select(VoiceProfile).where(VoiceProfile.subject_id == own.subject_id))
    assert retired.revoked_at
    assert retired.sample_object_key == retired.sample_transcript == retired.model_version == ""
    assert session.scalar(select(VoiceAsset).where(VoiceAsset.asset_id == asset_id)) is None
    assert client.get(audio_path, headers=headers).status_code == 404
    assert client.post(speech_path, headers=headers).status_code == 404


def test_spoken_query_is_transient(app, client, session):
    own = seed_development_data(session, subject_name="Own", actor_name="Own")
    headers = {"Authorization": "Bearer " + own.actor_token}
    app.state.settings.stt_backend = "http"
    path = f"/api/v1/subjects/{own.subject_id}/twin/transcribe-query"
    result = client.post(path, headers=headers, content=b"SPOKEN-QUESTION")
    assert result.status_code == 200
    assert result.json()["text"].startswith("[fake-stt]")
    assert session.query(Episode).count() == 0


@pytest.mark.parametrize('edit_during_compare',[False,True])
def test_calibration_locks_twin_before_human_episode_and_stales_on_source_edit(app, client, session,edit_during_compare):
    own = seed_development_data(session, subject_name="Own", actor_name="Own")
    other = seed_development_data(session, subject_name="Other", actor_name="Other")
    headers = {"Authorization": "Bearer " + own.actor_token}
    _record(client, app, own.subject_id, own.consent_id, headers)
    app.state.embedding_encoder = TinyEncoder()
    app.state.twin_client = QuoteTwin()
    app.state.settings.ai_backend = "http"
    cloud = client.post("/api/v1/consents", headers=headers,
                        json={"subject_id": own.subject_id, "scope": "CLOUD_TWIN"}).json()["consent_id"]
    answer = client.post(f"/api/v1/subjects/{own.subject_id}/twin/answers", headers=headers,
                         json={"question": "我喜欢什么？", "cloud_consent_id": cloud}).json()
    path = f"/api/v1/subjects/{own.subject_id}/calibrations"
    locked = client.post(path, headers=headers,
                         json={"twin_answer_id": answer["answer_id"], "cloud_consent_id": cloud})
    assert locked.status_code == 200, locked.text
    run = locked.json()
    assert run["status"] == "awaiting_human"
    assert run["locked_answer"] == answer["answer"]
    assert client.get(f"{path}/{run['calibration_id']}",
                      headers={"Authorization": "Bearer " + other.actor_token}).status_code == 404
    assert client.post(path, headers=headers,
                       json={"twin_answer_id": answer["answer_id"], "cloud_consent_id": cloud}).json()["calibration_id"] == run["calibration_id"]
    complete_path = f"{path}/{run['calibration_id']}/complete"
    assert client.post(complete_path, headers=headers, json={"cloud_consent_id": cloud}).status_code == 409
    import json
    metadata = json.dumps({"calibration_id": run["calibration_id"]})
    wrong = client.post("/api/v1/episodes", headers=headers,
        data={"subject_id": other.subject_id, "recording_consent_id": own.consent_id,
              "idempotency_key": "bad-calibration", "source": "IOS_MIC",
              "recorded_at": "2026-09-27T09:00:00Z", "audio_ref": "answer.m4a", "metadata": metadata},
        files={"file": ("answer.m4a", b"HUMAN", "audio/mp4")})
    assert wrong.status_code != 201
    upload = client.post("/api/v1/episodes", headers=headers,
        data={"subject_id": own.subject_id, "recording_consent_id": own.consent_id,
              "idempotency_key": "human-calibration", "source": "IOS_MIC",
              "recorded_at": "2026-09-27T09:00:00Z", "audio_ref": "answer.m4a", "metadata": metadata},
        files={"file": ("answer.m4a", b"HUMAN", "audio/mp4")})
    assert upload.status_code == 201, upload.text
    human_id = upload.json()["episode_id"]
    assert client.post(complete_path, headers=headers, json={"cloud_consent_id": cloud}).status_code == 409
    worker = ProcessingWorker(app.state.database, app.state.object_store,
                              app.state.stt_provider, app.state.ai_client, backoff_seconds=0)
    worker.run_once()
    assert client.patch(f"/api/v1/episodes/{human_id}/transcript-review", headers=headers,
                        json={"transcript": "我更喜欢游泳，因为我觉得自由"}).status_code == 200
    worker.run_once()
    worker.run_once()

    class Comparison:
        def compare(self, question, locked_answer, human_answer):
            assert question == "我喜欢什么？"
            assert locked_answer == "我喜欢散步"
            assert human_answer == "我更喜欢游泳，因为我觉得自由"
            if edit_during_compare:
                source=session.get(TwinAnswer,answer['answer_id']).memory_item_ids[0]
                assert client.delete(f'/api/v1/subjects/{own.subject_id}/memories/{source}',headers=headers).status_code==200
            return {"summary": "偏好与之前不同，值得继续确认。", "model_version": "deepseek-flash-test",
                    "suggested_question": "游泳为什么让你觉得自由？",
                    "dimensions": [{"dimension": dimension,
                                    "alignment": "DIFFERENT" if dimension == "VALUE_PRIORITY" else "NOT_OBSERVED",
                                    "note": "提到自由" if dimension == "VALUE_PRIORITY" else "没有谈及",
                                    "human_excerpt": "我觉得自由" if dimension == "VALUE_PRIORITY" else None}
                                   for dimension in ("DECISION", "REASONING", "VALUE_PRIORITY",
                                                     "EMOTIONAL_REACTION", "EXPRESSION")]}
    app.state.calibration_client = Comparison()
    result = client.post(complete_path, headers=headers, json={"cloud_consent_id": cloud})
    if edit_during_compare:
        assert result.status_code==409, result.text
        assert client.get(f"{path}/{run['calibration_id']}",headers=headers).json()['status']=='stale'
        return
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "complete"
    assert result.json()["human_episode_id"] == human_id
    assert result.json()["dimensions"][2]["human_excerpt"] == "我觉得自由"
    assert session.get(CalibrationRun, run["calibration_id"]).locked_answer == "我喜欢散步"
    source_memory_id = session.get(TwinAnswer, answer["answer_id"]).memory_item_ids[0]
    assert client.patch(f"/api/v1/subjects/{own.subject_id}/memories/{source_memory_id}",
                        headers=headers, json={"content": "改过的旧事实"}).status_code == 200
    reading = client.get(f"{path}/{run['calibration_id']}", headers=headers).json()
    assert reading["status"] == "stale"
    assert reading["locked_answer"] is None
