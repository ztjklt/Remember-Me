"""Local Chinese semantic index over active, subject-scoped memories."""

from __future__ import annotations

import hashlib
import math
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Episode, Evidence, GraphFact, MemoryEmbedding, MemoryItem, PersonTrait, TwinAnswer, VoiceAsset, MemoryRevision, utcnow


class EmbeddingUnavailable(RuntimeError):
    pass


DEFAULT_EMBEDDING = "BAAI/bge-small-zh-v1.5"
DEFAULT_REVISION = "7999e1d3359715c523056ef9478215996d62a620"


class LocalEncoder:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    @property
    def version(self) -> str:
        return (self.model_name + "@" + DEFAULT_REVISION
                if self.model_name == DEFAULT_EMBEDDING else self.model_name)

    def encode(self, texts: list[str]) -> list[list[float]]:
        try:
            model = _load_model(self.model_name)
            values = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise EmbeddingUnavailable("本机中文检索模型不可用；请安装 retrieval 依赖及模型。") from exc
        return [list(map(float, vector)) for vector in values]


@lru_cache(maxsize=2)
def _load_model(name: str):
    from sentence_transformers import SentenceTransformer
    revision = DEFAULT_REVISION if name == DEFAULT_EMBEDDING else None
    return SentenceTransformer(name, revision=revision, trust_remote_code=False, device="cpu")


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    magnitude = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return dot / magnitude if magnitude else 0.0


def _lexical(question: str, content: str) -> float:
    symbols = {ch for ch in question.casefold() if ch.strip() and not ch.isascii()}
    if not symbols:
        symbols = set(question.casefold().split())
    return len(symbols.intersection(content.casefold())) / len(symbols) if symbols else 0.0


def retrieve(session: Session, subject_id: str, question: str, encoder: LocalEncoder,
             limit: int = 8, *, episode_ids: set[str] | None = None,
             reader: bool = False) -> list[dict]:
    """Refresh stale vectors, then return only evidence from active memories."""
    query = select(MemoryItem, Episode).join(Episode).where(
        Episode.subject_id == subject_id, MemoryItem.deleted_at.is_(None),
        Episode.status == 'ready', MemoryItem.review_state == 'active')
    if episode_ids is not None:
        query = query.where(Episode.episode_id.in_(episode_ids))
    if reader:
        from sqlalchemy import or_
        altered = select(MemoryItem.episode_id).where(or_(MemoryItem.review_state != 'active',
            MemoryItem.deleted_at.is_not(None), MemoryItem.source_type == 'CALIBRATION'))
        query = query.where(Episode.episode_id.not_in(altered))
    rows = session.execute(query).all()
    # Reader derivation starts from visible memories only. Never reuse an owner
    # aggregate: even a trait attached to one public memory may encode a secret.
    traits = [] if reader else list(session.scalars(select(PersonTrait).where(PersonTrait.subject_id == subject_id)))
    facts = [] if reader else list(session.scalars(select(GraphFact).where(GraphFact.subject_id == subject_id)))
    live = {item.memory_item_id for item, _ in rows}
    for stale in ([] if reader else session.scalars(select(MemoryEmbedding).where(MemoryEmbedding.subject_id == subject_id))):
        if stale.memory_item_id not in live:
            session.delete(stale)
    pending = []
    documents = []
    evidence_by_item = {}
    for item, episode in rows:
        evidence = [session.get(Evidence, identifier) for identifier in item.evidence_ids]
        evidence = [source for source in evidence if source is not None and source.episode_id == episode.episode_id]
        evidence_by_item[item.memory_item_id] = evidence
        related_traits = [trait for trait in traits if item.memory_item_id in trait.memory_item_ids]
        related_facts = [fact for fact in facts if item.memory_item_id in fact.memory_item_ids]
        document = "；".join([item.content, (item.item_metadata or {}).get("domain", ""),
                              *[source.excerpt or "" for source in evidence],
                              *[trait.statement for trait in related_traits],
                              *[fact.content for fact in related_facts]])
        documents.append(document)
        digest = hashlib.sha256(document.encode()).hexdigest()
        cached = session.get(MemoryEmbedding, item.memory_item_id)
        if cached is None or cached.content_hash != digest or cached.model_version != encoder.version:
            pending.append((item, document, digest))
    if pending:
        vectors = encoder.encode([document for _, document, _ in pending])
        for (item, _, digest), vector in zip(pending, vectors, strict=True):
            cached = session.get(MemoryEmbedding, item.memory_item_id)
            if cached is None:
                cached = MemoryEmbedding(memory_item_id=item.memory_item_id, subject_id=subject_id,
                                         content_hash=digest, model_version=encoder.version, vector=vector)
                session.add(cached)
            else:
                cached.content_hash, cached.model_version, cached.vector = digest, encoder.version, vector
        session.flush()
    if not rows:
        return []
    query_vector = encoder.encode([question])[0]
    ranked = []
    for (item, episode), document in zip(rows, documents, strict=True):
        cached = session.get(MemoryEmbedding, item.memory_item_id)
        score = 0.85 * max(0.0, _cosine(query_vector, cached.vector)) + 0.15 * _lexical(question, document)
        ranked.append((score, item, episode))
    ranked.sort(key=lambda row: row[0], reverse=True)
    # A top-k alone leaks unrelated memories on a sparse Subject. Keep only
    # candidates reasonably close to the question and to the best match.
    floor = max(0.35, ranked[0][0] - 0.12)
    changes = {r.target_memory_id for r in session.scalars(select(MemoryRevision).where(
        MemoryRevision.subject_id == subject_id, MemoryRevision.status == 'confirmed', MemoryRevision.kind == 'change'))}
    def statement(item):
        metadata = item.item_metadata or {}
        suffix = '（历史记载，后来已有变化，不代表当前状态）' if item.memory_item_id in changes else ''
        if metadata.get('relation_kind') == 'change':
            suffix += '（变化后的记载；时间：' + str(metadata.get('time_context') or '未确定') + '）'
        return item.content + suffix
    return [{
        "memory_item_id": item.memory_item_id,
        "episode_id": episode.episode_id,
        "statement": statement(item),
        "domain": (item.item_metadata or {}).get("domain"),
        "source_type": item.source_type,
        "traits": [f"{trait.statement}（{trait.status}）" for trait in traits
                   if item.memory_item_id in trait.memory_item_ids][:8],
        "graph_facts": [f"{fact.kind}：{fact.content}" for fact in facts
                        if item.memory_item_id in fact.memory_item_ids][:8],
        "evidence": [{"evidence_id": source.evidence_id, "excerpt": source.excerpt,
                      "source_type": source.source_type, "episode_id": episode.episode_id}
                     for source in evidence_by_item[item.memory_item_id]],
        "score": round(score, 4),
    } for score, item, episode in ranked[:limit] if score >= floor]


def invalidate_answers(session: Session, store, subject_id: str) -> None:
    """Retire answer snapshots and remove speech derived from changed memories."""
    answers = list(session.scalars(select(TwinAnswer).where(
        TwinAnswer.subject_id == subject_id, TwinAnswer.invalidated_at.is_(None))))
    for answer in answers:
        answer.invalidated_at = utcnow()
        for asset in list(session.scalars(select(VoiceAsset).where(VoiceAsset.answer_id == answer.answer_id))):
            store.delete(asset.object_key)
            session.delete(asset)
