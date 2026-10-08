"""Effective reviewed source text; summaries never silently define the evidence universe.

Adapted from qingtian-4's original-material resolver (8627f03), with canonical
review, story grants and deletion rules. Generated span IDs are stable references,
not new memories. Caller holds a short snapshot transaction, never a model call.
"""
import hashlib
import re
from sqlalchemy import select
from .errors import AppError
from .models import Episode, MemoryItem, Evidence, MemoryRevision
from .language_support import is_owner_supplement


class ContextTooLarge(AppError):
    code = 'CONTEXT_TOO_LARGE'
    http_status = 413


def effective_materials(session, subject_id, episode_ids):
    episodes = list(session.scalars(select(Episode).where(Episode.subject_id == subject_id,
        Episode.episode_id.in_(episode_ids), Episode.status == 'ready',
        Episode.episode_id.not_in(select(MemoryRevision.episode_id).where(MemoryRevision.status!='confirmed')),
        Episode.transcript_reviewed_at.is_not(None)).order_by(Episode.recorded_at, Episode.episode_id)))
    # Check before any truncation, including text later masked by a correction.
    if sum(len(e.transcript or '') for e in episodes) > 24000:
        raise ContextTooLarge('当前有效材料超过24000字符，请缩小故事范围；没有截断原文。')
    candidates = []
    changes = {r.target_memory_id: r for r in session.scalars(select(MemoryRevision).where(
        MemoryRevision.subject_id == subject_id, MemoryRevision.status == 'confirmed',
        MemoryRevision.kind == 'change'))}
    for ep in episodes:
        text = ep.transcript or ''
        memories = list(session.scalars(select(MemoryItem).where(MemoryItem.episode_id == ep.episode_id).order_by(MemoryItem.ordinal)))
        blocked, suppress = [], False
        for memory in memories:
            if memory.deleted_at or memory.review_state != 'active' or (memory.source_type == 'CALIBRATION' and not is_owner_supplement(memory)):
                spans = [session.get(Evidence, id) for id in memory.evidence_ids]
                if not spans or any(s is None or s.span_start is None or s.span_end is None or
                    text[s.span_start:s.span_end] != s.excerpt for s in spans):
                    suppress = True
                else:
                    blocked.extend((s.span_start, s.span_end) for s in spans)
        def allowed(start, end):
            return not suppress and not any(start < b and end > a for a, b in blocked)
        covered = []
        for memory in memories:
            if memory.deleted_at or memory.review_state != 'active':
                continue
            evidence = []
            memory_covered = []
            for id in memory.evidence_ids:
                source = session.get(Evidence, id)
                if source is None or source.episode_id != ep.episode_id or not source.excerpt:
                    continue
                # Explicit human correction evidence remains valid while the old
                # episode's raw text is suppressed. It is never labelled ORIGINAL.
                if source.source_type == 'CALIBRATION':
                    evidence.append(dict(evidence_id=id, excerpt=source.excerpt,
                        source_type=source.source_type, episode_id=ep.episode_id))
                elif (source.span_start is not None and source.span_end is not None
                      and allowed(source.span_start, source.span_end)
                      and text[source.span_start:source.span_end] == source.excerpt):
                    evidence.append(dict(evidence_id=id, excerpt=source.excerpt,
                        source_type=source.source_type, episode_id=ep.episode_id))
                    memory_covered.append((source.span_start, source.span_end))
            # A summary may combine facts from all original references. Removing
            # one reference cannot validate the unchanged combined statement.
            # Keep safe raw gaps below, but withhold the unrepairable summary.
            if evidence and len(evidence) == len(memory.evidence_ids):
                covered.extend(memory_covered)
                meta = memory.item_metadata or {}
                temporal = ''
                if memory.memory_item_id in changes:
                    temporal = '（历史记载，后来已有变化，不代表当前状态）'
                if meta.get('relation_kind') == 'change':
                    temporal += '（变化后的记载；时间：' + str(meta.get('time_context') or '未确定') + '）'
                candidates.append(dict(memory_item_id=memory.memory_item_id, episode_id=ep.episode_id,
                    statement=memory.content + temporal, domain=meta.get('domain'), traits=[], graph_facts=[],
                    source_type=memory.source_type, evidence=evidence, score=1.0))
        # Sentence-sized original excerpts preserve unextracted facts, source
        # offsets and the narrator's wording. No generated summary is quoted.
        gaps = []
        for match in re.finditer(r'[^。！？\n]+[。！？\n]*', text):
            intervals = [match.span()]
            for a,b in covered:
                intervals = [(x,y) for start,end in intervals
                    for x,y in ((start,min(end,a)),(max(start,b),end)) if x<y]
            gaps.extend(intervals)
        for start,end in gaps:
            if not allowed(start,end):
                continue
            excerpt = text[start:end]
            if not re.search(r'\w',excerpt):
                continue
            id = 'src_' + hashlib.sha256(f'{ep.episode_id}:{start}:{end}:{excerpt}'.encode()).hexdigest()[:40]
            source = session.get(Evidence, id)
            if source is None:
                source = Evidence(evidence_id=id, episode_id=ep.episode_id, source_type='SUBJECT',
                    source_ref=f'episode:{ep.episode_id}#span:{start}-{end}', excerpt=excerpt,
                    span_start=start, span_end=end, confidence=None)
                session.add(source)
            candidates.append(dict(memory_item_id='episode:'+ep.episode_id, episode_id=ep.episode_id,
                statement=excerpt, domain=None, traits=[], graph_facts=[], source_type='SUBJECT',
                evidence=[dict(evidence_id=id, excerpt=excerpt, source_type='SUBJECT', episode_id=ep.episode_id)], score=1.0))
    if sum(map(len,{e['excerpt'] for c in candidates for e in c['evidence']})) > 24000:
        raise ContextTooLarge('有效证据（含重叠片段）超过24000字符，请缩小故事范围；没有截断。')
    session.flush()
    return candidates
