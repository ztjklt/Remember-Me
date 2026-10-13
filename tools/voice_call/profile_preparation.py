"""Profile actual authorized context preparation, without a model call or answer publication.

Run on an isolated DB with its private env. The packet remains private on the host.
"""
import argparse, cProfile, json, os, pstats, time
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import select
from app.config import Settings
from app.db import Database
from app.models import Account, Actor, Consent
from app.api.twin import generate_answer, TwinQuestion
from app.retrieval import LocalEncoder


class Captured(Exception):
    pass


def main(args):
    settings=Settings(_env_file=args.env)
    db=Database(settings.database_url)
    encoder=LocalEncoder(settings.embedding_model)
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    packets=[]
    class Capture:
        def answer(self,question,candidates):
            packets.append(dict(question=question,candidates=candidates,voice_response=True,dialogue_context=[]))
            raise Captured()
    request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        settings=settings,twin_client=Capture(),embedding_encoder=encoder)))
    rows=[]
    for index in range(3):
        profile=cProfile.Profile();start=time.perf_counter()
        with db.session() as session:
            account=session.scalar(select(Account).where(Account.username==args.username))
            actor=session.get(Actor,account.actor_id)
            consent=session.scalar(select(Consent).where(Consent.granted_by_actor_id==actor.actor_id,
                Consent.scope=='CLOUD_TWIN',Consent.status=='granted'))
            profile.enable()
            try:
                generate_answer(consent.subject_id,TwinQuestion(question=args.question,
                    cloud_consent_id=consent.consent_id,retrieval_mode='local'),request,actor,session,
                    voice_context=[])
            except Captured:pass
            finally:profile.disable()
        rows.append(dict(index=index,preparation_ms=round((time.perf_counter()-start)*1000)))
        with (out/f'profile-{index}.txt').open('w') as stream:
            pstats.Stats(profile,stream=stream).sort_stats('cumtime').print_stats(45)
    packet=out/'authorized-packet.json';packet.write_text(json.dumps(packets[-1],ensure_ascii=False));packet.chmod(0o600)
    (out/'preparation.json').write_text(json.dumps(rows,indent=2))
    print(json.dumps(rows));db.dispose()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--env',required=True);p.add_argument('--output',required=True)
    p.add_argument('--username',default='chensy08');p.add_argument('--question',default='你喜欢喝什么茶？')
    main(p.parse_args())
