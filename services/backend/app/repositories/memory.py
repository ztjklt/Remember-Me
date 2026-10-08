"""Where an AI Core result becomes rows.

The evidence and memory items of one Episode are replaced rather than appended:
the extract stage is their only pipeline writer, an Episode has exactly one result, and a
retried stage that wrote rows before failing would otherwise collide on primary
key or leave two versions of the same result behind.
"""

from uuid import uuid4
from copy import deepcopy

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..contracts import AICoreOutput
from ..models import Episode, Evidence, MemoryItem


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def store_result(self, episode: Episode, output: AICoreOutput) -> None:
        self.clear_result(episode.episode_id)

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

        identifiers = [f"mi_{uuid4().hex[:16]}" for _ in output.memory_items]
        for ordinal, item in enumerate(output.memory_items):
            metadata = deepcopy(item.metadata)
            for link in (metadata or {}).get("temporal_causal", []):
                for endpoint in (link.get("cause", {}), link.get("effect", {})):
                    if "memory_index" in endpoint:
                        index = endpoint.pop("memory_index")
                        if not isinstance(index, int) or not 0 <= index < len(identifiers):
                            from ..errors import AiSchemaInvalid
                            raise AiSchemaInvalid("Causal anchor index is invalid")
                        endpoint["memory_item_id"] = identifiers[index]
            self.session.add(
                MemoryItem(
                    memory_item_id=identifiers[ordinal],
                    episode_id=episode.episode_id,
                    ordinal=ordinal,
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
                    item_metadata=metadata,
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
        return list(
            self.session.scalars(
                select(MemoryItem)
                .where(MemoryItem.episode_id == episode_id, MemoryItem.deleted_at.is_(None))
                .order_by(MemoryItem.ordinal)
            )
        )
