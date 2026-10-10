"""Script normalization must not masquerade as factual correction or review."""
from sqlalchemy import select
from app.models import Episode, Job
from test_agent_workbench import setup_pair


def test_simplification_preserves_negation_dates_and_misrecognized_name():
    from app.chinese_text import simplified_transcript
    assert simplified_transcript('陳蘭說：我不喜歡甜茶，也許1987年去過，但還沒確定。') == '陈兰说：我不喜欢甜茶，也许1987年去过，但还没确定。'


def test_legacy_waiting_transcript_is_simplified_for_review_without_changing_raw(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    row=session.get(Episode,ep)
    row.transcript=row.stt_transcript='我不喜歡太甜的茶，陳蘭還沒決定。'
    row.transcript_reviewed_at=None;row.transcript_reviewed_by=None;row.status='transcribing'
    job=session.scalar(select(Job).where(Job.episode_id==ep));job.state='waiting';job.stage='extract'
    session.commit()
    review=client.get(f'/api/v1/episodes/{ep}/transcript-review',headers=oh).json()
    story=client.get(f'/api/v1/workbench/subjects/{owner.subject_id}/stories',headers=oh).json()['items'][0]
    assert review['state']=='reviewing' and review['transcript']=='我不喜欢太甜的茶，陈兰还没决定。'
    assert story['transcript']==review['transcript']
    assert story['machine_transcript']=='我不喜歡太甜的茶，陳蘭還沒決定。'
    session.expire_all()
    assert session.get(Episode,ep).transcript_reviewed_at is None
    assert session.get(Episode,ep).stt_transcript==story['machine_transcript']


def test_worker_retains_original_script_separately(app,client,session):
    from app.stt import Transcript
    from app.worker import ProcessingWorker
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    class ChineseSTT:
        def transcribe(self,audio,content_type):
            return Transcript('我不喜歡太甜的茶。','http','test-zh')
    worker=ProcessingWorker(app.state.database,app.state.object_store,ChineseSTT(),app.state.ai_client)
    row=session.get(Episode,ep)
    row.transcript=None
    worker._transcribe(row)
    assert row.transcript=='我不喜欢太甜的茶。'
    assert row.stt_transcript=='我不喜歡太甜的茶。'
