"""Revalidate saved answers on all reading and audio paths."""
from .access import Hidden, visible_episodes, source_basis, require_cloud
from .models import TwinAnswer
from .persona_models import PersonaAnswerContext


def get_current_answer(session, subject_id, actor_id, answer_id):
    visible_episodes(session,subject_id,actor_id)
    row=session.get(TwinAnswer,answer_id,populate_existing=True)
    if (row is None or row.subject_id!=subject_id or row.actor_id!=actor_id or
        row.invalidated_at is not None or row.source_basis!=source_basis(session,subject_id)):
        raise Hidden('回答已变化，请重新提问。')
    meta=session.get(PersonaAnswerContext,answer_id)
    if meta: require_cloud(session,subject_id,actor_id,meta.cloud_consent_id)
    return row
