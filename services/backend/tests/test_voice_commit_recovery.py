"""A lost commit acknowledgement must not erase durable voice audio."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import VoiceAsset, VoiceProfile
from app.voice_models import SyntheticVoiceProfile
from test_synthetic_voice import prepare, answer, wav_bytes
from test_twin_voice import TinyVoice


def enroll_request(client, kind, root, headers, consent):
    if kind == 'synthetic':
        return client.post(root+'/voice/profile/synthetic', headers=headers,
            json={'preset':'a01', 'voice_consent_id':consent})
    return client.post(root+'/voice/profile', headers=headers,
        data={'voice_consent_id':consent, 'transcript':'这是我的声音', 'own_voice_confirmed':'true'},
        files={'sample':('own.m4a', b'OWN-VOICE', 'audio/mp4')})


def ready(app, client, session, tmp_path, kind):
    _, _, headers, _, _, cloud, consent, root, _ = prepare(app, client, session, tmp_path)
    app.state.voice_client = TinyVoice()
    enrolled = enroll_request(client, kind, root, headers, consent)
    assert enrolled.status_code == 200, enrolled.text
    answer_id = answer(client, root, headers, cloud)
    return headers, consent, root, answer_id, enrolled.json()['profile_id']


def fail_voice_commit(monkeypatch, database, failure, *, recovery_unavailable=False):
    original_commit = Session.commit
    original_session = database.session
    failed = False

    def commit(session):
        nonlocal failed
        writing = any(isinstance(row, (VoiceAsset, VoiceProfile, SyntheticVoiceProfile))
                      for row in session.new)
        if not writing:
            return original_commit(session)
        if failure == 'after':
            original_commit(session)
        else:
            session.flush()
        failed = True
        raise RuntimeError('injected voice commit failure')

    def fresh_session():
        if failed and recovery_unavailable:
            raise RuntimeError('confirmation unavailable')
        return original_session()

    monkeypatch.setattr(Session, 'commit', commit)
    monkeypatch.setattr(database, 'session', fresh_session)


@pytest.mark.parametrize('failure', ['before', 'after'])
@pytest.mark.parametrize('recovery_unavailable', [False, True])
def test_speech_commit_failure_preserves_only_confirmed_or_uncertain_audio(
        app, client, session, tmp_path, monkeypatch, failure, recovery_unavailable):
    headers, _, root, answer_id, _ = ready(app, client, session, tmp_path, 'synthetic')
    path = root+'/twin/answers/'+answer_id+'/speech'
    store = app.state.object_store
    before = set(store._objects)
    with monkeypatch.context() as patch:
        fail_voice_commit(patch, app.state.database, failure,
                          recovery_unavailable=recovery_unavailable)
        with pytest.raises(RuntimeError, match='injected voice commit failure'):
            client.post(path, headers=headers)
    session.expire_all()
    saved = session.scalar(select(VoiceAsset))
    assert (saved is not None) == (failure == 'after')
    if failure == 'after' or recovery_unavailable:
        assert len(set(store._objects)-before) == 1
    else:
        assert set(store._objects) == before
    if saved:
        assert store.get(saved.object_key) == wav_bytes()
        retry = client.post(path, headers=headers)
        assert retry.status_code == 200, retry.text
        assert retry.json()['asset_id'] == saved.asset_id
        playback = client.get(root+'/voice/assets/'+saved.asset_id+'/audio', headers=headers)
        assert playback.status_code == 200 and playback.content == wav_bytes()


@pytest.mark.parametrize('kind', ['synthetic', 'own'])
@pytest.mark.parametrize('failure', ['before', 'after'])
@pytest.mark.parametrize('recovery_unavailable', [False, True])
def test_profile_replacement_commit_failure_preserves_the_durable_profile_files(
        app, client, session, tmp_path, monkeypatch, kind, failure, recovery_unavailable):
    headers, consent, root, answer_id, old_profile_id = ready(app, client, session, tmp_path, kind)
    speech = client.post(root+'/twin/answers/'+answer_id+'/speech', headers=headers)
    assert speech.status_code == 200, speech.text
    store = app.state.object_store
    before = dict(store._objects)
    old_profile = session.get(VoiceProfile, old_profile_id)
    old_sample = old_profile.sample_object_key
    old_asset = session.get(VoiceAsset, speech.json()['asset_id'])
    old_audio = old_asset.object_key
    with monkeypatch.context() as patch:
        fail_voice_commit(patch, app.state.database, failure,
                          recovery_unavailable=recovery_unavailable)
        with pytest.raises(RuntimeError, match='injected voice commit failure'):
            enroll_request(client, kind, root, headers, consent)
    session.expire_all()
    current = session.scalar(select(VoiceProfile).where(VoiceProfile.revoked_at.is_(None)))
    assert current is not None
    assert (current.profile_id != old_profile_id) == (failure == 'after')
    assert store.get(current.sample_object_key) == (wav_bytes() if kind == 'synthetic' else b'OWN-VOICE')
    if failure == 'before' or recovery_unavailable:
        assert store.get(old_sample) == before[old_sample][0]
        assert store.get(old_audio) == before[old_audio][0]
    else:
        assert not store.exists(old_sample) and not store.exists(old_audio)
    if failure == 'before' and not recovery_unavailable:
        assert store._objects == before
    elif recovery_unavailable:
        assert len(set(store._objects)-set(before)) == 1
    result = client.get(root+'/voice/profile', headers=headers)
    assert result.status_code == 200 and result.json()['profile_id'] == current.profile_id


@pytest.mark.parametrize('kind', ['synthetic', 'own'])
def test_failed_replacement_upload_keeps_previous_sample_and_speech(
        app, client, session, tmp_path, monkeypatch, kind):
    headers, consent, root, answer_id, profile_id = ready(app, client, session, tmp_path, kind)
    speech = client.post(root+'/twin/answers/'+answer_id+'/speech', headers=headers)
    assert speech.status_code == 200, speech.text
    store = app.state.object_store
    before = dict(store._objects)
    original_put = store.put
    def fail_put(key, data, mime):
        original_put(key, data, mime)
        raise RuntimeError('injected partial voice upload failure')
    with monkeypatch.context() as patch:
        patch.setattr(store, 'put', fail_put)
        with pytest.raises(RuntimeError, match='injected partial voice upload failure'):
            enroll_request(client, kind, root, headers, consent)
    session.expire_all()
    assert session.get(VoiceProfile, profile_id).revoked_at is None
    assert store._objects == before
    playback = client.get(root+'/voice/assets/'+speech.json()['asset_id']+'/audio', headers=headers)
    assert playback.status_code == 200


@pytest.mark.parametrize('kind', ['synthetic', 'own'])
def test_successful_profile_replacement_removes_retired_audio(
        app, client, session, tmp_path, kind):
    headers, consent, root, answer_id, profile_id = ready(app, client, session, tmp_path, kind)
    speech = client.post(root+'/twin/answers/'+answer_id+'/speech', headers=headers)
    assert speech.status_code == 200, speech.text
    old_sample = session.get(VoiceProfile, profile_id).sample_object_key
    old_audio = session.get(VoiceAsset, speech.json()['asset_id']).object_key
    replaced = enroll_request(client, kind, root, headers, consent)
    assert replaced.status_code == 200, replaced.text
    assert not app.state.object_store.exists(old_sample)
    assert not app.state.object_store.exists(old_audio)
    session.expire_all()
    assert session.get(VoiceProfile, profile_id).revoked_at is not None
    current = session.get(VoiceProfile, replaced.json()['profile_id'])
    assert app.state.object_store.exists(current.sample_object_key)
