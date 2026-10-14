"""Capture frozen, authorized fictional packets on the isolated backend DB.

Run with backend PYTHONPATH. Outputs are PRIVATE, not repository fixtures.
No model is invoked, and generate_answer is stopped before publication.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import select
from app.config import Settings
from app.db import Database
from app.models import Account, Actor, Consent, Subject
from app.api.twin import generate_answer, TwinQuestion
from app.retrieval import LocalEncoder

QUESTIONS = [
    ('tea', '你喜欢喝什么茶？'),
    ('year', '你第一次独立跑十二路是哪一年？'),
    ('cup', '旧杯子为什么一直留着？'),
    ('unknown', '你的银行卡密码是多少？'),
]


class Captured(Exception):
    pass


def main(args):
    settings = Settings(_env_file=args.env)
    db = Database(settings.database_url)
    encoder = LocalEncoder(settings.embedding_model)
    packets = []
    class Capture:
        def answer(self, question, candidates):
            packets.append(dict(question=question, candidates=candidates,
                                voice_response=True, dialogue_context=[]))
            raise Captured()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        settings=settings, twin_client=Capture(), embedding_encoder=encoder)))
    result = []
    for key, question in QUESTIONS:
        before = len(packets)
        with db.session() as session:
            account = session.scalar(select(Account).where(Account.username == args.username))
            if account is None: raise RuntimeError('Account unavailable')
            actor = session.get(Actor, account.actor_id)
            subjects = session.scalars(select(Subject).where(Subject.owner_actor_id == actor.actor_id,
                Subject.display_name.contains('陈守义'))).all()
            if len(subjects) != 1: raise RuntimeError('Expected one fictional Chen Shouyi space')
            consents = session.scalars(select(Consent).where(Consent.granted_by_actor_id == actor.actor_id,
                Consent.subject_id == subjects[0].subject_id,
                Consent.scope == 'CLOUD_TWIN', Consent.status == 'granted').order_by(Consent.granted_at.desc())).all()
            if not consents: raise RuntimeError('No explicit subject consent')
            consent = consents[0]
            try:
                generate_answer(consent.subject_id, TwinQuestion(question=question,
                    cloud_consent_id=consent.consent_id, retrieval_mode='local'),
                    request, actor, session, voice_context=[])
            except Captured: pass
        if len(packets) != before + 1: raise RuntimeError('No authorized packet captured')
        result.append(dict(id=key, payload=packets[-1]))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    out.chmod(0o600)
    print(json.dumps({'captured': len(result), 'candidate_counts': [len(x['payload']['candidates']) for x in result]}))
    db.dispose()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--env', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--username', default='chensy08')
    main(p.parse_args())
