"""Where an AI Core result becomes rows.

The evidence and memory items of one Episode are replaced rather than appended:
the extract stage is their only pipeline writer, an Episode has exactly one result, and a
retried stage that wrote rows before failing would otherwise collide on primary
key or leave two versions of the same result behind.
"""

from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..contracts import AICoreOutput
from ..models import Episode, Evidence, MemoryItem, MemoryRevision, MemoryAudit


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def store_result(self, episode: Episode, output: AICoreOutput) -> None:
        self.clear_result(episode.episode_id)
        revision = self.session.scalar(select(MemoryRevision).where(MemoryRevision.episode_id == episode.episode_id))

        for source in output.evidence:
            self.session.add(
                Evidence(
                    evidence_id=source.evidence_id,
                    episode_id=episode.episode_id,
                    source_type=str(source.source_type),
                    source_ref=source.source_ref,
                    excerpt=source.excerpt,
                    span_start=source.span_start,
                    span_end=source.span_end,
                    confidence=source.confidence,
                )
            )

        for ordinal, item in enumerate(output.memory_items):
            self.session.add(
                MemoryItem(
                    memory_item_id=f"mi_{uuid4().hex[:16]}",
                    episode_id=episode.episode_id,
                    ordinal=ordinal,
                    review_state='pending' if revision and revision.status == 'pending' else 'active',
                    memory_type=str(item.memory_type),
                    content=item.content,
                    source_type=str(item.source_type),
                    # The model's own claim about what it rested on, stored as
                    # given. Resolving it is a read-time question: evidence can
                    # come from an earlier Episode as well as this one.
                    evidence_ids=list(item.evidence_ids),
                    confidence=item.confidence,
                    model_version=item.model_version,
                    prompt_version=item.prompt_version,
                    schema_version=item.schema_version,
                    effective_at=item.effective_at,
                    item_metadata=item.metadata,
                )
            )

        episode.model_version = output.model_version
        episode.model_proposals = {
            "graph_updates": [item.model_dump(mode="json", exclude_none=True) for item in output.graph_updates],
            "persona_updates": [item.model_dump(mode="json", exclude_none=True) for item in output.persona_updates],
        }

    def clear_result(self, episode_id: str) -> None:
        self.session.execute(
            delete(MemoryItem).where(MemoryItem.episode_id == episode_id)
        )
        self.session.execute(delete(Evidence).where(Evidence.episode_id == episode_id))

    def items_for(self, episode_id: str) -> list[MemoryItem]:
        items = list(
            self.session.scalars(
                select(MemoryItem)
                .where(MemoryItem.episode_id == episode_id, MemoryItem.deleted_at.is_(None))
                .order_by(MemoryItem.ordinal)
            )
        )
        # Preserve the original processing-result contract for unedited legacy
        # captures. After a correction/deletion it must not republish a sibling
        # summary whose source has been withdrawn by that edit.
        edited = self.session.scalar(select(MemoryAudit.audit_id).join(MemoryItem).where(
            MemoryItem.episode_id == episode_id).limit(1))
        if edited:
            from ..materials import effective_materials
            episode = self.session.get(Episode, episode_id)
            effective = {c['memory_item_id'] for c in effective_materials(self.session,
                episode.subject_id, {episode_id}, enforce_budget=False, include_gaps=False)}
            items = [item for item in items if item.memory_item_id in effective]
        return items
