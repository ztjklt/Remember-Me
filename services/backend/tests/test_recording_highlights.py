from types import SimpleNamespace

from app.recording_highlights import highlight_report, validated_sentences


def episode(text='我爱散步。我不会借钱投资。', **metadata):
    markers = metadata.pop('markers', [{'offset_ms': 35_000, 'origin': 'device'}])
    return SimpleNamespace(transcript=text, duration_ms=60_000, capture_metadata={
        'hardware': {'markers': markers},
        'asr_timeline': [{'start_ms': 0, 'end_ms': 2000, 'text': '我爱散步。'},
                         {'start_ms': 30000, 'end_ms': 40000, 'text': '我不会借钱投资。'}],
        **metadata})


def test_mark_maps_to_exact_reviewed_sentence_and_preserves_negation():
    r = highlight_report(episode())
    assert r['mapped_count'] == 1
    assert r['spans'][0]['excerpt'] == '我不会借钱投资。'
    assert r['spans'][0]['span_start'] == 5
    assert r['spans'][0]['priority_weight'] == 2.0


def test_device_points_and_phone_notes_are_distinct_even_without_sentence_alignment():
    r = highlight_report(episode(asr_timeline=[], markers=[
        {'offset_ms': 1000, 'origin': 'device'},
        {'offset_ms': 2000, 'origin': 'phone'},
        {'offset_ms': 2000, 'origin': 'phone'}]))
    assert r['device_marker_count'] == 1
    assert r['phone_marker_count'] == 1
    assert r['markers'] == [
        {'offset_ms': 1000, 'origin': 'device', 'mapped': False},
        {'offset_ms': 2000, 'origin': 'phone', 'mapped': False}]


def test_signal_without_verified_offset_is_pending_not_an_invented_point():
    e = episode(markers=[])
    e.capture_metadata['hardware']['device_marker_pending'] = True
    r = highlight_report(e)
    assert r['device_marker_pending'] is True
    assert r['device_marker_count'] == 0


def test_changed_or_ambiguous_sentence_does_not_guess_alignment():
    for text in ['我爱散步。我会借钱投资。', '我不会借钱投资。我不会借钱投资。']:
        r = highlight_report(episode(text))
        assert r['mapped_count'] == 0 and r['unmapped_count'] == 1
        assert not r['spans']


def test_deleted_duplicate_cannot_be_assigned_to_one_of_two_original_times():
    e=episode('我爱散步。',asr_timeline=[{'start_ms':0,'end_ms':2000,'text':'我爱散步。'},
        {'start_ms':30000,'end_ms':40000,'text':'我爱散步。'}])
    assert highlight_report(e)['mapped_count']==0


def test_missing_timestamps_and_invalid_or_duplicate_markers():
    r = highlight_report(episode(asr_timeline=[]))
    assert r['state'] == 'timestamps_unavailable'
    r = highlight_report(episode(markers=[{'offset_ms': True}, {'offset_ms': -1},
        {'offset_ms': 100_000}, {'offset_ms': 35000, 'origin': 'device'},
        {'offset_ms': 35000, 'origin': 'device'}]))
    assert r['marker_count'] == 1 and r['mapped_count'] == 1


def test_provider_sentences_are_bounded_ordered_and_not_guessed():
    assert validated_sentences([{'begin_time': 10, 'end_time': 20, 'text': '你好。'}]) == [
        {'start_ms': 10, 'end_ms': 20, 'text': '你好。'}]
    assert validated_sentences([{'begin_time': True, 'end_time': 20, 'text': '你好。'}]) == []
    assert validated_sentences([{'begin_time': 20, 'end_time': 10, 'text': '你好。'}]) == []


def test_upload_to_review_to_extraction_passes_only_server_timeline(client, session, app):
    import json
    from sqlalchemy import select
    from app.models import Episode, MemoryItem
    from app.seed import seed_development_data
    from app.stt import Transcript
    from app.ai_core import FakeAiCoreClient
    from app.worker import ProcessingWorker
    owner = seed_development_data(session, subject_name='测试', actor_name='测试')
    headers = {'Authorization': 'Bearer ' + owner.actor_token}
    result = client.post('/api/v1/episodes', headers=headers, data={
        'subject_id': owner.subject_id, 'recording_consent_id': owner.consent_id,
        'source':'WORK_3200', 'recorded_at':'2026-10-16T01:00:00Z',
        'audio_ref':'test.m4a', 'idempotency_key':'marker-test', 'duration_ms':60000,
        'metadata':json.dumps({'hardware':{'markers':[{'offset_ms':35000,'origin':'device'}]},
            'asr_timeline':[{'start_ms':1,'end_ms':2,'text':'伪造'}], 'highlight_analysis':{'fake':True}})},
        files={'file':('test.wav',b'RIFF\x00\x00\x00\x00WAVEfmt ','audio/wav')})
    assert result.status_code == 201, result.text
    id=result.json()['episode_id']; session.expire_all()
    assert 'asr_timeline' not in session.get(Episode,id).capture_metadata
    class Speech:
        def transcribe(self,*args):
            return Transcript('我爱散步。我不会借钱投资。','test','test',segments=episode().capture_metadata['asr_timeline'])
    class AI(FakeAiCoreClient):
        received = None
        def process(self,payload):
            self.received=payload
            return super().process(payload)
    ai=AI()
    worker=ProcessingWorker(app.state.database,app.state.object_store,Speech(),ai)
    assert worker.run_once()==id
    review=client.get(f'/api/v1/episodes/{id}/transcript-review',headers=headers).json()
    assert review['recording_highlights']['mapped_count']==1
    assert session.scalar(select(MemoryItem)) is None
    assert client.patch(f'/api/v1/episodes/{id}/transcript-review',headers=headers,
        json={'transcript':review['transcript']}).status_code==200
    worker.run_once()
    assert ai.received.subject_context['recording_highlights']['spans'][0]['excerpt']=='我不会借钱投资。'
