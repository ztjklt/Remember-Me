"""Real capture/review boundary; only model transport is substituted."""
import hashlib
import json
import pytest
from sqlalchemy import select, func
from app.models import Episode, Job, MemoryItem, Consent
from app.stt import Transcript
from test_worker import seeded, auth, CAPTURE_FIELDS, AUDIO, build_worker

RAW = "以前修电击，有时认私理。也许1986年开始，我没有说过喜欢冒险。"
DRAFT = RAW.replace("电击", "电机").replace("认私理", "认死理")


def corrected():
    edits = []
    for before, after in [("电击", "电机"), ("认私理", "认死理")]:
        start = RAW.index(before)
        edits.append(dict(before=before, after=after, start=start, end=start+len(before),
                          category="word", action="auto", reason="语境明确的近音词"))
    return dict(draft=DRAFT, edits=edits, model_version="test-model", prompt_version="asr-proofread-v1",
                input_sha256=hashlib.sha256(RAW.encode()).hexdigest())


class STT:
    calls = 0
    def transcribe(self, audio, content_type):
        self.calls += 1
        return Transcript(RAW, "http", "test-asr")


class Corrector:
    calls = 0
    def __init__(self, policy): self.policy_id = policy
    def correct(self, text):
        assert text == RAW
        self.calls += 1
        return corrected()


def upload(client, app, seeded, auth, *, allowed=True, metadata=None):
    from app.transcript_correction import correction_policy
    app.state.settings.ai_backend = "http"
    app.state.settings.transcript_correction_enabled = True
    policy = correction_policy(app.state.settings)
    values = dict(metadata or {})
    if allowed: values["transcript_correction_policy"] = policy
    response = client.post("/api/v1/episodes", headers=auth, data={
        **CAPTURE_FIELDS, "subject_id":seeded.subject_id, "recording_consent_id":seeded.consent_id,
        "metadata":json.dumps(values)}, files={"file":("test.wav", AUDIO, "audio/wav")})
    assert response.status_code == 201, response.text
    return response.json()["episode_id"], policy


def test_auto_corrected_draft_waits_for_review_and_preserves_raw(app, client, session, seeded, auth):
    ep, policy = upload(client, app, seeded, auth)
    reviewer = Corrector(policy)
    worker = build_worker(app, stt=STT(), transcript_corrector=reviewer)
    worker.run_once()
    review = client.get(f"/api/v1/episodes/{ep}/transcript-review", headers=auth).json()
    assert review["transcript"] == DRAFT and review["machine_transcript"] == RAW
    assert review["automatic_correction"]["status"] == "completed"
    assert len(review["automatic_correction"]["edits"]) == 2
    assert session.scalar(select(func.count()).select_from(MemoryItem)) == 0
    assert session.get(Episode, ep).transcript_reviewed_at is None
    assert worker.run_once() is None
    assert reviewer.calls == 1
    assert client.patch(f"/api/v1/episodes/{ep}/transcript-review", headers=auth,
                        json={"transcript":DRAFT}).status_code == 200
    session.expire_all()
    assert session.get(Episode, ep).stt_transcript == RAW
    assert session.scalar(select(Job).where(Job.episode_id == ep)).state == "queued"


def test_old_client_cannot_inject_a_correction_or_authorization_receipt(app, client, session, seeded, auth):
    ep, policy = upload(client, app, seeded, auth, allowed=False, metadata={
        "transcript_correction_receipt":{"policy":"fake", "actor_id":seeded.actor_id},
        "automatic_correction":{"status":"completed", "draft":"假的经历"}})
    reviewer = Corrector(policy)
    build_worker(app, stt=STT(), transcript_corrector=reviewer).run_once()
    row = session.get(Episode, ep)
    assert reviewer.calls == 0 and row.transcript == RAW
    assert "automatic_correction" not in row.capture_metadata
    assert "transcript_correction_receipt" not in row.capture_metadata


def test_model_failure_keeps_raw_reviewable_without_repeating_asr(app, client, session, seeded, auth):
    ep, policy = upload(client, app, seeded, auth)
    class Failure(Corrector):
        def correct(self, text): raise RuntimeError("SECRET PRIVATE UPSTREAM TEXT")
    stt = STT()
    worker = build_worker(app, stt=stt, transcript_corrector=Failure(policy))
    worker.run_once()
    review = client.get(f"/api/v1/episodes/{ep}/transcript-review", headers=auth)
    assert review.json()["transcript"] == RAW
    assert review.json()["automatic_correction"]["status"] == "failed"
    assert "SECRET" not in review.text
    assert worker.run_once() is None and stt.calls == 1


def test_recording_consent_revocation_during_correction_discards_new_draft(app, client, session, seeded, auth):
    ep, policy = upload(client, app, seeded, auth)
    class Revoking(Corrector):
        def correct(self, text):
            from app.models import utcnow
            with app.state.database.session() as other:
                consent = other.get(Consent, seeded.consent_id)
                consent.revoked_at = utcnow()
                other.commit()
            return super().correct(text)
    build_worker(app, stt=STT(), transcript_corrector=Revoking(policy)).run_once()
    row = session.get(Episode, ep)
    assert row.transcript == RAW
    assert row.capture_metadata["automatic_correction"]["status"] == "unavailable"


def test_mismatched_or_untracked_draft_is_not_stored(app, client, session, seeded, auth):
    ep, policy = upload(client, app, seeded, auth)
    class Wrong(Corrector):
        def correct(self, text): return {**corrected(), "draft":"我在1987年喜欢冒险。"}
    build_worker(app, stt=STT(), transcript_corrector=Wrong(policy)).run_once()
    row = session.get(Episode, ep)
    assert row.transcript == RAW
    assert row.capture_metadata["automatic_correction"]["status"] == "failed"


def test_other_account_cannot_read_machine_text_or_model_edits(app, client, session, seeded, auth):
    from app.seed import seed_development_data
    ep, policy = upload(client, app, seeded, auth)
    build_worker(app, stt=STT(), transcript_corrector=Corrector(policy)).run_once()
    other = seed_development_data(session, subject_name="Other", actor_name="Other")
    response = client.get(f"/api/v1/episodes/{ep}/transcript-review",
                          headers={"Authorization":f"Bearer {other.actor_token}"})
    assert response.status_code == 404
    assert RAW not in response.text and DRAFT not in response.text


def test_revoked_before_model_is_called_does_not_export_transcript(app, client, session, seeded, auth):
    from app.models import utcnow
    ep, policy = upload(client, app, seeded, auth)
    consent = session.get(Consent, seeded.consent_id)
    consent.revoked_at = utcnow()
    session.commit()
    reviewer = Corrector(policy)
    build_worker(app, stt=STT(), transcript_corrector=reviewer).run_once()
    assert reviewer.calls == 0


def test_unknown_policy_and_unsupported_capture_are_rejected_before_upload(client, app, seeded, auth):
    app.state.settings.ai_backend = "http"
    app.state.settings.transcript_correction_enabled = True
    for source, policy in [("ANDROID_MIC", "old-policy"), ("RECORDING_DEVICE", "fake")]:
        response = client.post("/api/v1/episodes", headers=auth, data={**CAPTURE_FIELDS,
            "source":source, "subject_id":seeded.subject_id, "recording_consent_id":seeded.consent_id,
            "metadata":json.dumps({"transcript_correction_policy":policy})},
            files={"file":("test.wav", AUDIO, "audio/wav")})
        assert response.status_code == 422


def test_http_correction_has_a_total_deadline_even_for_slow_drip(monkeypatch, settings):
    import asyncio
    import httpx
    import time
    from app.transcript_correction import HttpTranscriptCorrector
    real_client = httpx.AsyncClient
    real_sync_client = httpx.Client
    class Drip(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(100):
                await asyncio.sleep(0.02)
                yield b" "
    async def handle(request):
        return httpx.Response(200, stream=Drip())
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(
        **kw, transport=httpx.MockTransport(handle)))
    class SyncDrip(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(10):
                time.sleep(0.02)
                yield b" "
            yield json.dumps(corrected()).encode()
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_sync_client(
        **kw, transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=SyncDrip()))))
    limited = settings.model_copy(update={"transcript_correction_timeout_seconds":0.06})
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        HttpTranscriptCorrector(limited).correct(RAW)
    assert time.monotonic() - start < 0.5
