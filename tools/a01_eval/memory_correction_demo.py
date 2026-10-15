"""Replay explicit fictional-script corrections through the API on a DB backup.

This is a local service experiment, not phone/login or human listening acceptance.
The original runtime DB, audio, ASR and accounts are never written.
"""
import json
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'services/backend'))
from app.config import Settings
from app.main import create_app
from app.models import Actor,Subject,Episode,MemoryItem
from app.security import current_actor
from app.materials import effective_materials

FIXES={
    'mi_5a84b104871c4c86':'讲述者听了半天，发现不是电机坏了，而是一颗小螺丝松了。',
    'mi_ee57d7deebd047f0':'讲述者承认自己有时候太认死理，别人劝换个办法还不爱听；现在回想，这样不一定都是对的。',
    'mi_bfe4b8029343408f':'讲述者找不到钥匙时，曾向桂芳发脾气，指责她动了自己的东西；这段讲述没有说明究竟是谁动了钥匙，不能确定桂芳是否被错怪。',
    'mi_20c90a8cee0b4031':'讲述者对桂芳说，她和自己共同生活了快五十年，没有享到多少清福。',
    'mi_8a0322d51dfd4d96':'讲述者希望桂芳不要什么事都揽着，该歇就歇。',
    'mi_d4f0e356002a4e98':'讲述者希望保留那个蓝色搪瓷杯，因为用了好多年，已经用顺手了。',
}


def main():
    source=ROOT/'services/backend/var/a01-20261012/runtime/remember.db'
    out=ROOT/'services/backend/var/memory-quality-20261015'/('replay-'+uuid4().hex[:8])
    out.mkdir(parents=True)
    target=out/'remember.db'
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as original, sqlite3.connect(target) as backup:
        original.backup(backup)
    app=create_app(Settings(_env_file=None,environment='test',enable_workbench=True,
        database_url='sqlite:///'+target.as_posix(),object_store_backend='memory',log_level='ERROR'))
    with app.state.database.session() as session:
        first=session.get(MemoryItem,next(iter(FIXES)))
        subject=session.get(Subject,session.get(Episode,first.episode_id).subject_id)
        sid,aid=subject.subject_id,subject.owner_actor_id
        actor=session.get(Actor,aid); session.expunge(actor)
        episodes=list(session.scalars(select(Episode).where(Episode.subject_id==sid)))
        original_text={ep.episode_id:ep.transcript for ep in episodes}
        original_asr={ep.episode_id:ep.stt_transcript for ep in episodes}
        ids=set(original_text)
    # Only this in-process, isolated test app binds the known owner. API owner
    # authorization, audit, source masking and invalidation still execute.
    app.dependency_overrides[current_actor]=lambda: actor
    def snapshot():
        with app.state.database.session() as session:
            candidates=effective_materials(session,sid,ids,enforce_budget=False)
            session.commit()
            return candidates
    report=dict(input='fictional_A01_snapshot',identity='isolated_known_owner_dependency',
        correction_basis='original authored script; NOT human audio verification',
        before=snapshot(),corrections=[])
    with TestClient(app) as client:
        for mid,content in FIXES.items():
            with app.state.database.session() as session:old=session.get(MemoryItem,mid).content
            response=client.patch(f'/api/v1/subjects/{sid}/memories/{mid}',json={'content':content})
            assert response.status_code==200,(mid,response.status_code)
            report['corrections'].append(dict(id=mid,before=old,after=content,status=response.status_code))
        report['after']=snapshot()
        report['person_model_after']=client.get(f'/api/v1/subjects/{sid}/person-model').json()
        report['stories_after']=client.get(f'/api/v1/workbench/subjects/{sid}/stories').json()
    with app.state.database.session() as session:
        report['original_transcripts_preserved']=all(session.get(Episode,e).transcript==t for e,t in original_text.items())
        report['original_asr_preserved']=all(session.get(Episode,e).stt_transcript==t for e,t in original_asr.items())
    result_text=json.dumps(report['after'],ensure_ascii=False)
    report['old_error_absent']={word:word not in result_text for word in ['误怪桂芳','电击','认私理','轻浮','该谢','搪瓷被']}
    report['unrelated_fact_preserved']='机械厂' in result_text and '广州' in result_text
    assert report['original_transcripts_preserved'] and report['original_asr_preserved']
    assert all(report['old_error_absent'].values()),report['old_error_absent']
    assert report['unrelated_fact_preserved']
    (out/'replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (out.parent/'latest-replay.txt').write_text(str(out),encoding='utf-8')
    print(json.dumps({'directory':str(out),'corrections':len(FIXES),
        'checks':report['old_error_absent'],'original_asr_preserved':report['original_asr_preserved'],
        'unrelated_fact_preserved':report['unrelated_fact_preserved']},ensure_ascii=False))


if __name__=='__main__':main()
