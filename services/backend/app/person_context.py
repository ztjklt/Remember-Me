"""One live projection for the person page and conditional Twin dialogue."""
from sqlalchemy import select
from .access import is_owner, profile_source_basis, Hidden
from .models import ProfileCandidate, Subject
from .narrative import material_map, fingerprint, event_support
from .profile_updates import valid_snapshot, ProfileChanged
from .profiles import candidate_view


def visible_understandings(session, subject, actor, sources, *, include_pending=False):
    owner=is_owner(session,subject,actor);basis=profile_source_basis(session,subject)
    query=select(ProfileCandidate).where(ProfileCandidate.subject_id==subject)
    if not owner or not include_pending:
        query=query.where(ProfileCandidate.status=='confirmed',ProfileCandidate.source_basis==basis)
    result=[];owner_sources=None
    for row in session.scalars(query):
        refs=list(dict.fromkeys(row.evidence_ids+row.counter_evidence_ids))
        if not refs or not all(e in sources for e in refs): continue
        if row.status=='confirmed':
            try: valid_snapshot(session,subject,actor,row,require_saved=True)
            except (ProfileChanged,Hidden): continue
            if not owner:
                if owner_sources is None:
                    owner_sources=material_map(session,subject,session.get(Subject,subject).owner_actor_id)
                if any(e not in owner_sources or fingerprint(sources[e])!=fingerprint(owner_sources[e]) for e in refs): continue
            if row.source_basis!=profile_source_basis(session,subject): continue
        view=candidate_view(row,basis)
        view.update(evidence=[sources[e] for e in row.evidence_ids],
            counter_evidence=[sources[e] for e in row.counter_evidence_ids],
            independent_events=event_support(session,subject,row.evidence_ids,sources))
        view['label']='本人确认的情境化理解' if view['status']=='confirmed' else '待本人核对的观察'
        if not owner: view.update(scope='shared_confirmed',source_valid=True,reader_recomputed=False)
        result.append(view)
    return result


def persona_understandings(session, subject, actor, sources):
    return [dict(id=v['candidate_id'],statement=v['statement'],context=v['context'],
        evidence_ids=v['evidence_ids'],counter_evidence_ids=v['counter_evidence_ids'])
        for v in visible_understandings(session,subject,actor,sources) if v['status']=='confirmed']
