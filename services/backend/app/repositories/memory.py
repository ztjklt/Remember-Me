"""Where an AI Core result becomes rows.

The evidence and memory items of one Episode are replaced rather than appended:
the model stage is the only writer, an Episode has exactly one result, and a
retried stage that wrote rows before failing would otherwise collide on primary
key or leave two versions of the same result behind.
"""

from uuid import uuid4
from remember_contracts.provenance import canonical_evidence_id
from ..errors import AiSchemaInvalid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..contracts import AICoreOutput
from ..models import Episode, Evidence, MemoryItem


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def store_result(self, episode: Episode, output: AICoreOutput) -> None:
        mapping = {e.evidence_id: canonical_evidence_id(episode.episode_id, e) for e in output.evidence}
        if len(mapping) != len(output.evidence) or len(set(mapping.values())) != len(mapping):
            raise AiSchemaInvalid("Duplicate evidence IDs")
        if any(not set(m.evidence_ids) <= mapping.keys() for m in output.memory_items):
            raise AiSchemaInvalid("Unknown evidence references")
        self.clear_result(episode.episode_id)
        for source in output.evidence:
            self.session.add(
                Evidence(
                    evidence_id=mapping[source.evidence_id],
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
                    memory_type=str(item.memory_type),
                    content=item.content,
                    source_type=str(item.source_type),
                    # Canonical server IDs preserve the model's evidence links
                    # while preventing another Episode from reusing its IDs.
                    evidence_ids=[mapping[eid] for eid in item.evidence_ids],
                    confidence=item.confidence,
                    model_version=item.model_version,
                    prompt_version=item.prompt_version,
                    schema_version=item.schema_version,
                    effective_at=item.effective_at,
                    item_metadata=item.metadata,
                )
            )

        episode.model_version = output.model_version

    def clear_result(self, episode_id: str) -> None:
        self.session.execute(
            delete(MemoryItem).where(MemoryItem.episode_id == episode_id)
        )
        self.session.execute(delete(Evidence).where(Evidence.episode_id == episode_id))

    def items_for(self, episode_id: str) -> list[MemoryItem]:
        return list(
            self.session.scalars(
                select(MemoryItem)
                .where(MemoryItem.episode_id == episode_id)
                .order_by(MemoryItem.ordinal)
            )
        )