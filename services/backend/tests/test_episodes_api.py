"""The capture boundary over HTTP.

The centre of this file is the pair of tests that state Issue #1's definition of
done as requests: an upload creates exactly one Episode, and re-uploading the
same audio returns that Episode instead of a second one. Around them are the
cases that decide whether the boundary is safe to point a client at — a capture
with no consent, a voice consent offered as a recording consent, audio that is
not audio, and a key reused for different bytes.

Two things are scoped to the Actor rather than to the request: an Episode is
readable only by the Actor that captured it, and the consent that authorizes a
capture has to be one the caller granted. A cross-Actor attempt is answered
exactly as an id nobody holds would be, so the API cannot be asked whether
another Actor's recording is there.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Actor, Episode, Job, JobStage, JobState, as_utc
from app.repositories.episodes import EpisodeRepository
from app.seed import seed_development_data
from app.storage.base import checksum_of
from app.tokens import generate_actor_token, hash_actor_token

AUDIO = b"RIFF\x00\x00\x00\x00WAVEfmt "
OTHER_AUDIO = b"RIFF\x00\x00\x00\x00WAVEfmy"

# A value that means "leave this field out of the request", so a missing field
# can be distinguished from an empty one.
OMIT = object()

CAPTURE_FIELDS: dict[str, object] = {
    "source": "ANDROID_MIC",
    "recorded_at": "2026-09-21T09:30:00+00:00",
    "audio_ref": "walk-in-the-park.m4a",
    "idempotency_key": "capture-0001",
}


@pytest.fixture
def seeded(session):
    return seed_development_data(session, subject_name="Ada", actor_name="Ada")


@pytest.fixture
def auth(seeded) -> dict[str, str]:
    return {"Authorization": f"Bearer {seeded.actor_token}"}


@pytest.fixture
def other(session) -> dict[str, str]:
    """A second Actor's credentials, and nothing else of its own.

    Built here rather than by seeding again, because the rule under test is about
    *which Actor* captured an Episode, with the subject held constant. A second
    seeded Subject would let the tests pass for the wrong reason.
    """
    token = generate_actor_token()
    actor = Actor(
        actor_id=f"actor_{uuid4().hex[:16]}",
        display_name="Bob",
        token_hash=hash_actor_token(token),
    )
    session.add(actor)
    session.commit()
    return {"actor_id": actor.actor_id, "headers": {"Authorization": f"Bearer {token}"}}


def capture(
    client: TestClient,
    auth: dict[str, str],
    seeded,  # noqa: ANN001 - SeedResult
    *,
    audio: bytes = AUDIO,
    filename: str = "walk-in-the-park.m4a",
    content_type: str = "audio/mp4",
    **overrides: object,
):
    """POST a capture. Keyword overrides edit the form; OMIT removes a field."""
    form: dict[str, object] = {
        "subject_id": seeded.subject_id,
        "recording_consent_id": seeded.consent_id,
        **CAPTURE_FIELDS,
    }
    for name, value in overrides.items():
        if value is OMIT:
            form.pop(name, None)
        else:
            form[name] = value

    return client.post(
        "/api/v1/episodes",
        headers=auth,
        data={name: str(value) for name, value in form.items()},
        files={"file": (filename, audio, content_type)},
    )


def count(session, model) -> int:  # noqa: ANN001 - SQLAlchemy model
    return session.scalar(select(func.count()).select_from(model))


def test_an_upload_creates_exactly_one_episode(client, session, seeded, auth):
    response = capture(client, auth, seeded)

    assert response.status_code == 201, response.text
    body = response.json()
    # Exactly the contract's episodeCreated, no more: the schema forbids extra
    # fields, and job_id in particular must never appear.
    assert set(body) == {"episode_id", "upload_status"}
    assert body["upload_status"] == "uploaded"

    episode = session.get(Episode, body["episode_id"])
    assert episode is not None
    assert episode.subject_id == seeded.subject_id
    assert episode.actor_id == seeded.actor_id
    assert episode.recording_consent_id == seeded.consent_id
    assert episode.idempotency_key == "capture-0001"
    assert episode.source == "ANDROID_MIC"
    assert episode.status == "uploaded"
    assert episode.audio_ref == "walk-in-the-park.m4a"
    assert episode.audio_size_bytes == len(AUDIO)
    assert episode.audio_content_type == "audio/mp4"
    assert episode.audio_checksum == checksum_of(AUDIO)
    assert as_utc(episode.recorded_at) == datetime(2026, 9, 21, 9, 30, tzinfo=timezone.utc)

    # The client's filename is a label, not a path: it must not shape the key.
    assert "walk-in-the-park" not in episode.audio_object_key
    assert client.app.state.object_store.get(episode.audio_object_key) == AUDIO

    assert count(session, Episode) == 1


def test_the_episode_is_persisted_before_any_processing_runs(client, session, seeded, auth):
    episode_id = capture(client, auth, seeded).json()["episode_id"]
    episode = session.get(Episode, episode_id)

    # No transcript, no result: the row exists and nothing has processed it.
    assert episode.transcript is None
    assert episode.stt_backend is None
    assert episode.model_version is None
    assert episode.error_code is None

    job = session.scalars(select(Job).where(Job.episode_id == episode_id)).one()
    assert job.state == str(JobState.QUEUED)
    assert job.stage == str(JobStage.TRANSCRIBE)
    assert job.attempts == 0


def test_the_trace_id_of_a_capture_spans_the_request(client, session, seeded, auth):
    response = capture(client, auth, seeded)
    episode = session.get(Episode, response.json()["episode_id"])

    assert episode.trace_id == response.headers["X-Request-ID"]

    status = client.get(f"/api/v1/episodes/{episode.episode_id}", headers=auth)
    assert status.json()["trace_id"] == episode.trace_id


def test_re_uploading_the_same_audio_returns_the_same_episode(client, session, seeded, auth):
    """Issue #1's definition of done: a retried capture does not duplicate."""
    first = capture(client, auth, seeded)
    second = capture(client, auth, seeded)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert count(session, Episode) == 1
    assert count(session, Job) == 1


def test_the_same_key_with_different_audio_is_a_conflict(client, session, seeded, auth):
    first = capture(client, auth, seeded)
    conflict = capture(client, auth, seeded, audio=OTHER_AUDIO)

    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "IDEMPOTENCY_CONFLICT"
    assert count(session, Episode) == 1

    # The stored audio is still the first upload's, untouched by the attempt.
    episode = session.get(Episode, first.json()["episode_id"])
    assert client.app.state.object_store.get(episode.audio_object_key) == AUDIO


def test_a_different_key_with_the_same_audio_is_a_second_episode(client, session, seeded, auth):
    first = capture(client, auth, seeded)
    second = capture(client, auth, seeded, idempotency_key="capture-0002")

    assert second.status_code == 201
    assert second.json()["episode_id"] != first.json()["episode_id"]
    assert count(session, Episode) == 2


def test_an_upload_without_a_consent_reference_is_refused(client, session, seeded, auth):
    response = capture(client, auth, seeded, recording_consent_id=OMIT)

    assert response.status_code == 422
    assert response.json()["error_code"] == "REQUEST_INVALID"
    assert count(session, Episode) == 0


def test_an_upload_without_an_idempotency_key_is_refused(client, session, seeded, auth):
    response = capture(client, auth, seeded, idempotency_key=OMIT)

    assert response.status_code == 422
    assert response.json()["error_code"] == "REQUEST_INVALID"
    assert count(session, Episode) == 0


def test_a_voice_grant_does_not_authorize_an_upload(client, session, seeded, auth):
    """Issue #9's rule, at Issue #1's boundary: the scopes are separate grants."""
    voice = client.post(
        "/api/v1/consents",
        headers=auth,
        json={"subject_id": seeded.subject_id, "scope": "VOICE"},
    ).json()

    response = capture(client, auth, seeded, recording_consent_id=voice["consent_id"])

    assert response.status_code == 403
    assert response.json()["error_code"] == "CONSENT_INVALID"
    assert count(session, Episode) == 0


def test_a_revoked_recording_consent_cannot_authorize_an_upload(client, session, seeded, auth):
    client.post(f"/api/v1/consents/{seeded.consent_id}/revoke", headers=auth)

    response = capture(client, auth, seeded)

    assert response.status_code == 403
    assert response.json()["error_code"] == "CONSENT_INVALID"
    assert count(session, Episode) == 0


def test_an_unknown_subject_is_not_found(client, session, seeded, auth):
    response = capture(client, auth, seeded, subject_id="subj_does_not_exist")

    assert response.status_code == 404
    assert response.json()["error_code"] == "SUBJECT_NOT_FOUND"
    assert count(session, Episode) == 0


def test_an_unknown_source_is_refused(client, session, seeded, auth):
    response = capture(client, auth, seeded, source="CARRIER_PIGEON")

    assert response.status_code == 422
    assert response.json()["error_code"] == "REQUEST_INVALID"
    assert count(session, Episode) == 0


def test_a_upload_that_is_not_audio_is_refused(client, session, seeded, auth):
    response = capture(client, auth, seeded, content_type="text/plain")

    assert response.status_code == 400
    assert response.json()["error_code"] == "AUDIO_INVALID"
    assert count(session, Episode) == 0
    # Nothing reached storage either: the store double is empty.
    assert client.app.state.object_store._objects == {}


def test_an_empty_upload_is_refused(client, session, seeded, auth):
    response = capture(client, auth, seeded, audio=b"")

    assert response.status_code == 400
    assert response.json()["error_code"] == "AUDIO_INVALID"
    assert count(session, Episode) == 0


def test_an_upload_over_the_limit_is_refused(client, app, session, seeded, auth):
    # The limit is read from settings per request, so a small one can be imposed
    # for this test alone.
    app.state.settings = app.state.settings.model_copy(update={"max_upload_bytes": 8})

    response = capture(client, auth, seeded, audio=b"x" * 64)

    assert response.status_code == 413
    assert response.json()["error_code"] == "AUDIO_TOO_LARGE"
    assert count(session, Episode) == 0


def test_a_recorded_at_without_an_offset_is_refused(client, session, seeded, auth):
    response = capture(client, auth, seeded, recorded_at="2026-09-21T09:30:00")

    assert response.status_code == 422
    assert response.json()["error_code"] == "REQUEST_INVALID"
    assert "offset" in response.json()["error_message"]
    assert count(session, Episode) == 0


def test_an_actor_id_naming_the_caller_is_accepted(client, session, seeded, auth):
    """The contract defines actor_id on a capture, so sending it cannot be fatal."""
    response = capture(client, auth, seeded, actor_id=seeded.actor_id)

    assert response.status_code == 201
    episode = session.get(Episode, response.json()["episode_id"])
    assert episode.actor_id == seeded.actor_id


def test_an_actor_id_naming_someone_else_is_refused(client, session, seeded, auth):
    response = capture(client, auth, seeded, actor_id="actor_someone_else")

    assert response.status_code == 422
    assert response.json()["error_code"] == "REQUEST_INVALID"
    assert count(session, Episode) == 0


def test_an_unknown_field_is_refused(client, session, seeded, auth):
    response = capture(client, auth, seeded, unexpected="something")

    assert response.status_code == 422
    assert response.json()["error_code"] == "REQUEST_INVALID"
    assert count(session, Episode) == 0


def test_capture_metadata_is_stored_as_given(client, session, seeded, auth):
    response = capture(client, auth, seeded, metadata='{"device": "pixel", "gain": 4}')

    episode = session.get(Episode, response.json()["episode_id"])
    assert episode.capture_metadata == {"device": "pixel", "gain": 4}


def test_metadata_that_is_not_json_is_refused(client, session, seeded, auth):
    response = capture(client, auth, seeded, metadata="{not json")

    assert response.status_code == 422
    assert response.json()["error_code"] == "REQUEST_INVALID"
    assert count(session, Episode) == 0


def test_storage_can_be_unavailable_without_leaving_an_episode(client, session, seeded, auth, monkeypatch):
    """A failed store must not leave a record whose audio never arrived."""
    store = client.app.state.object_store
    monkeypatch.setattr(store, "put", _raise_storage_error)

    response = capture(client, auth, seeded)

    assert response.status_code == 503
    assert response.json()["error_code"] == "STORAGE_UNAVAILABLE"
    assert count(session, Episode) == 0
    assert count(session, Job) == 0


def _raise_storage_error(*_args, **_kwargs):  # noqa: ANN202 - test double
    raise RuntimeError("the bucket is gone")


def test_the_status_of_an_uploaded_episode_is_uploaded(client, seeded, auth):
    episode_id = capture(client, auth, seeded).json()["episode_id"]

    response = client.get(f"/api/v1/episodes/{episode_id}", headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["episode_id"] == episode_id
    assert body["status"] == "uploaded"
    # Omitted rather than null: the contract types these as strings, so an
    # explicit null would not be a valid processingStatus.
    assert "error_code" not in body
    assert "error_message" not in body


def test_an_unknown_episode_is_not_found(client, auth):
    response = client.get("/api/v1/episodes/ep_does_not_exist", headers=auth)

    assert response.status_code == 404
    assert response.json()["error_code"] == "EPISODE_NOT_FOUND"


def test_the_result_of_an_unprocessed_episode_is_not_ready(client, seeded, auth):
    episode_id = capture(client, auth, seeded).json()["episode_id"]

    response = client.get(f"/api/v1/episodes/{episode_id}/result", headers=auth)

    assert response.status_code == 409
    assert response.json()["error_code"] == "EPISODE_NOT_READY"


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/episodes"),
        ("GET", "/api/v1/episodes/ep_anything"),
        ("GET", "/api/v1/episodes/ep_anything/result"),
    ],
)
def test_the_episode_endpoints_require_an_actor(client: TestClient, method: str, path: str):
    response = client.request(method, path)

    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_REQUIRED"


# An Episode belongs to the Actor that captured it. Every refusal below is a 404
# rather than a 403, because a distinguishable "exists but is not yours" would let
# one Actor enumerate another Actor's recordings by id.


def test_an_episode_is_readable_only_by_the_actor_that_captured_it(client, seeded, auth, other):
    episode_id = capture(client, auth, seeded).json()["episode_id"]

    assert client.get(f"/api/v1/episodes/{episode_id}", headers=auth).status_code == 200

    response = client.get(f"/api/v1/episodes/{episode_id}", headers=other["headers"])

    assert response.status_code == 404
    assert response.json()["error_code"] == "EPISODE_NOT_FOUND"


def test_another_actors_episode_answers_exactly_like_a_missing_one(client, seeded, auth, other):
    """The two refusals are one answer, so neither can be used as a probe."""
    episode_id = capture(client, auth, seeded).json()["episode_id"]

    missing = client.get("/api/v1/episodes/ep_does_not_exist", headers=other["headers"])
    someone_elses = client.get(f"/api/v1/episodes/{episode_id}", headers=other["headers"])

    assert missing.status_code == someone_elses.status_code == 404
    assert (
        missing.json()["error_code"]
        == someone_elses.json()["error_code"]
        == "EPISODE_NOT_FOUND"
    )


def test_the_result_of_an_episode_is_readable_only_by_its_actor(client, seeded, auth, other):
    episode_id = capture(client, auth, seeded).json()["episode_id"]

    response = client.get(f"/api/v1/episodes/{episode_id}/result", headers=other["headers"])

    # Not EPISODE_NOT_READY: which of the two refusals comes back would itself say
    # that the Episode exists.
    assert response.status_code == 404
    assert response.json()["error_code"] == "EPISODE_NOT_FOUND"


def test_a_consent_granted_by_another_actor_cannot_authorize_an_upload(
    client, session, seeded, other
):
    """The capture asks for the caller's own grant, not for any grant."""
    response = capture(client, other["headers"], seeded)

    assert response.status_code == 404
    assert response.json()["error_code"] == "CONSENT_NOT_FOUND"
    assert count(session, Episode) == 0


def test_each_actor_reads_only_the_episodes_it_captured(client, seeded, auth, other):
    """The whole rule, with the subject held constant on both sides."""
    mine = capture(client, auth, seeded).json()["episode_id"]

    theirs_consent = client.post(
        "/api/v1/consents",
        headers=other["headers"],
        json={"subject_id": seeded.subject_id, "scope": "RECORDING"},
    )
    assert theirs_consent.status_code == 404
    assert client.get(f'/api/v1/episodes/{mine}', headers=auth).status_code == 200
    assert client.get(f'/api/v1/episodes/{mine}', headers=other['headers']).status_code == 404


# The audio is written before the Episode is committed, so a request that fails to
# commit has already put an object somewhere. Nothing will ever refer to it, and
# these are the tests that it does not stay there.


def _miss_the_pre_check_once(monkeypatch) -> None:
    """Make the second capture's idempotency pre-check miss what is already there.

    The pre-check is a read, so it can miss a row another request is about to
    commit — that race is exactly what the unique index on (subject, actor,
    idempotency_key) exists to catch. Counting calls reproduces it: the first
    capture's pre-check genuinely finds nothing, the racing one is made to miss,
    and the handler's post-IntegrityError lookup is left alone so it can find the
    winner.
    """
    original = EpisodeRepository.find_by_idempotency
    calls = {"seen": 0}

    def miss_the_second_time(self, **kwargs):  # noqa: ANN003, ANN202 - test double
        calls["seen"] += 1
        return None if calls["seen"] == 2 else original(self, **kwargs)

    monkeypatch.setattr(EpisodeRepository, "find_by_idempotency", miss_the_second_time)


def test_a_lost_idempotency_race_leaves_no_orphaned_audio(
    client, session, seeded, auth, monkeypatch
):
    _miss_the_pre_check_once(monkeypatch)

    winner = capture(client, auth, seeded).json()["episode_id"]
    raced = capture(client, auth, seeded)

    assert raced.status_code == 200, raced.text
    assert raced.json()["episode_id"] == winner
    assert count(session, Episode) == 1

    store = client.app.state.object_store
    stored = session.get(Episode, winner).audio_object_key
    # One object, and it is the one the committed Episode points at. Two would
    # mean the losing request's bytes survived the request that wrote them.
    assert list(store._objects) == [stored]
    assert store.get(stored) == AUDIO


def test_a_raced_upload_of_different_audio_leaves_no_orphaned_audio(
    client, session, seeded, auth, monkeypatch
):
    _miss_the_pre_check_once(monkeypatch)

    winner = capture(client, auth, seeded).json()["episode_id"]
    raced = capture(client, auth, seeded, audio=OTHER_AUDIO)

    assert raced.status_code == 409
    assert raced.json()["error_code"] == "IDEMPOTENCY_CONFLICT"
    assert count(session, Episode) == 1

    store = client.app.state.object_store
    assert list(store._objects) == [session.get(Episode, winner).audio_object_key]


def test_a_capture_that_cannot_commit_leaves_no_orphaned_audio(
    client, session, seeded, auth, monkeypatch
):
    """Any failure between storing the bytes and committing the Episode."""
    store = client.app.state.object_store

    def fail_after_the_bytes_are_stored(self, episode, stored, *, audio_ref):  # noqa: ANN001, ANN202
        raise RuntimeError("the Episode row could not be written")

    monkeypatch.setattr(EpisodeRepository, "attach_audio", fail_after_the_bytes_are_stored)

    with pytest.raises(RuntimeError):
        capture(client, auth, seeded)

    assert store._objects == {}
    assert count(session, Episode) == 0
