"""Retrieval over effective original evidence, never unfiltered raw transcripts.

Encoding runs outside publication locks. The caller must recheck the complete
source/permission basis under publication_lock before storing vectors/ranking.
Only canonical excerpts are cached; private owner aggregates never enter a
reader's vector documents. Returned context keeps complete evidence and IDs.
"""
from dataclasses import dataclass
import hashlib
import math
import re
from sqlalchemy import select
from .models import EvidenceChunkEmbedding
from .retrieval import EmbeddingUnavailable, _cosine
from .materials import ContextTooLarge


def lexical(question, document):
    def tokens(text):
        result = set()
        for part in re.findall(r'[\u3400-\u9fff]+|[a-z0-9]+', text.casefold()):
            if part.isascii() or len(part) == 1:
                result.add(part)
            else:
                result.update(part[i:i+2] for i in range(len(part)-1))
        return result
    q = tokens(question)
    return len(q & tokens(document)) / len(q) if q else 0.0


def checked_vector(value):
    try:
        vector = [float(v) for v in value]
        if not vector or not all(math.isfinite(v) for v in vector) or not any(vector):
            raise ValueError('Invalid vector')
        return vector
    except (ValueError, TypeError, OverflowError) as exc:
        raise EmbeddingUnavailable('检索模型返回了无效向量。') from exc


@dataclass
class RetrievalPlan:
    subject_id: str
    version: str
    question: str
    query_vector: list
    chunks: dict
    updates: list
    sources: dict
    understanding_scores: dict


def prepare(session, subject_id, question, candidates, encoder):
    sources = {e['evidence_id']: e for c in candidates for e in c['evidence'] if e.get('excerpt')}
    if not sources:
        return RetrievalPlan(subject_id, encoder.version, question, [], {}, [], {}, {})
    chunks = {}
    for eid, source in sources.items():
        text = source['excerpt']
        digest = hashlib.sha256((source['source_type']+'\0'+text).encode()).hexdigest()
        # Windows affect vector recall only. The original complete excerpt is
        # returned to the answer worker, never a fragment cut out of a negation.
        for start in range(0, len(text), 380):
            end = min(len(text), start+480)
            cid = hashlib.sha256(f'{subject_id}:{eid}:{start}:{end}:{digest}'.encode()).hexdigest()
            chunks[cid] = dict(chunk_id=cid, subject_id=subject_id, evidence_id=eid,
                span_start=start, span_end=end, content_hash=digest,
                model_version=encoder.version, text=text[start:end])
            if end == len(text): break
    if len(chunks) > 20000:
        raise ContextTooLarge('当前可用资料的检索片段过多，请先缩小范围。')
    cached = {r.chunk_id:r for r in session.scalars(select(EvidenceChunkEmbedding).where(
        EvidenceChunkEmbedding.subject_id == subject_id, EvidenceChunkEmbedding.model_version == encoder.version,
        EvidenceChunkEmbedding.chunk_id.in_(chunks)))}
    # Release the read transaction as well; revocation cannot wait on encoding.
    session.commit()
    query_vector = checked_vector(encoder.encode([question])[0])
    pending = [c for cid,c in chunks.items() if cid not in cached or
        cached[cid].content_hash != c['content_hash'] or len(cached[cid].vector) != len(query_vector)]
    updates = []
    for offset in range(0, len(pending), 16):
        batch = pending[offset:offset+16]
        vectors = encoder.encode([c['text'] for c in batch])
        if len(vectors) != len(batch): raise EmbeddingUnavailable('检索片段向量数量不一致。')
        for chunk, value in zip(batch, vectors, strict=True):
            vector = checked_vector(value)
            if len(vector) != len(query_vector): raise EmbeddingUnavailable('检索向量维度不一致。')
            updates.append({k:v for k,v in chunk.items() if k!='text'} | {'vector':vector})
    # Approved understanding can help recall its supporting originals. These
    # temporary vectors are not cached or shared across owners/readers.
    rules = {}
    for candidate in candidates:
        for rule in candidate.get('traits', []):
            rules.setdefault(rule, set()).update(e['evidence_id'] for e in candidate['evidence'])
    rule_scores = {}
    for offset in range(0, len(rules), 16):
        batch = list(rules)[offset:offset+16]
        values = encoder.encode(batch)
        if len(values) != len(batch): raise EmbeddingUnavailable('人物理解检索向量数量不一致。')
        for rule, value in zip(batch, values, strict=True):
            vector = checked_vector(value)
            if len(vector)!=len(query_vector): raise EmbeddingUnavailable('人物理解检索维度不一致。')
            score = .85*max(0., _cosine(query_vector, vector))+.15*lexical(question,rule)
            for eid in rules[rule]:rule_scores[eid]=max(score,rule_scores.get(eid,0.))
    return RetrievalPlan(subject_id, encoder.version, question, query_vector, chunks, updates, sources, rule_scores)


def publish_and_select(session, plan, candidates, *, related_groups=(), limit=8):
    """Caller has checked source_basis and authorization under publication_lock."""
    if not plan.sources: return []
    if session.bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    for row in plan.updates:
        statement = insert(EvidenceChunkEmbedding).values(**row)
        session.execute(statement.on_conflict_do_update(index_elements=['chunk_id'],
            set_={k:statement.excluded[k] for k in row if k!='chunk_id'}))
    session.flush()
    permitted = select(EvidenceChunkEmbedding).where(
        EvidenceChunkEmbedding.subject_id==plan.subject_id,
        EvidenceChunkEmbedding.model_version==plan.version,
        EvidenceChunkEmbedding.chunk_id.in_(plan.chunks))
    if session.bind.dialect.name == 'postgresql':
        from sqlalchemy import bindparam, cast
        from .vector_type import PGVector
        # Deployment uses an isolated search_path without public. Resolve the
        # extension's operator explicitly and cast the driver's string bind.
        distance = EvidenceChunkEmbedding.vector.op('OPERATOR(public.<=>)')(
            cast(bindparam('query_vector', plan.query_vector, type_=PGVector()), PGVector()))
        rows = session.execute(permitted.with_only_columns(EvidenceChunkEmbedding.chunk_id, distance.label('distance'))
            .order_by(distance, EvidenceChunkEmbedding.chunk_id).limit(64)).all()
        similarities = {cid:max(0., 1.-float(distance)) for cid,distance in rows}
    else:
        similarities = {r.chunk_id:max(0.,_cosine(plan.query_vector,r.vector)) for r in session.scalars(permitted)}
    scores = dict(plan.understanding_scores)
    # Retain strong literal matches even outside the semantic top-64 pool.
    for cid,chunk in plan.chunks.items():
        word_score = lexical(plan.question, chunk['text'])
        if cid not in similarities and word_score < .4:continue
        score = .85*similarities.get(cid,0.)+.15*word_score
        if word_score >= .7:score=max(score,.5*word_score)
        eid = chunk['evidence_id'];scores[eid]=max(score,scores.get(eid,0.))
    ranked = sorted(scores, key=lambda eid:(-scores[eid], eid))
    if not ranked:return []
    floor = max(.35,scores[ranked[0]]-.18)
    seeds = {eid for eid in ranked[:limit] if scores[eid]>=floor}
    if not seeds:return []
    # Include the complete authorized recording contexts for the selected seeds,
    # so antecedents, reasons, reported speech and negatives stay attached.
    episodes = {plan.sources[eid]['episode_id'] for eid in seeds}
    selected = {eid for eid,e in plan.sources.items() if e['episode_id'] in episodes}
    for _ in range(len(related_groups)+1):
        expanded = set(selected)
        for group in related_groups:
            if set(group)&selected: expanded.update(set(group)&plan.sources.keys())
        related_episodes = {plan.sources[eid]['episode_id'] for eid in expanded}
        expanded.update(eid for eid,e in plan.sources.items() if e['episode_id'] in related_episodes)
        if expanded==selected:break
        selected=expanded
    result = [dict(c, score=round(max(scores.get(e['evidence_id'],0.) for e in c['evidence']),4))
        for c in candidates if any(e['evidence_id'] in selected for e in c['evidence'])]
    context = {e['evidence_id']:e['excerpt'] for c in result for e in c['evidence']}
    if sum(map(len,context.values()))>24000 or sum(map(len,{t for c in result for t in c['traits']}))>24000:
        raise ContextTooLarge('相关原文与必要上下文过长，请把问题问得更具体；没有截断原文。')
    return result


def search_items(candidates):
    """Keep the existing search payload; raw gaps use their existing opaque IDs."""
    grouped = {}
    for candidate in candidates:
        key = candidate['memory_item_id']
        if key not in grouped:
            grouped[key] = dict(candidate)
        else:
            row = grouped[key]
            row['score'] = max(row['score'],candidate['score'])
            seen = {e['evidence_id'] for e in row['evidence']}
            row['evidence'] = row['evidence']+[e for e in candidate['evidence'] if e['evidence_id'] not in seen]
            row['statement'] = ' '.join(e['excerpt'] for e in row['evidence'])
    return sorted(grouped.values(),key=lambda c:(-c['score'],c['memory_item_id']))
