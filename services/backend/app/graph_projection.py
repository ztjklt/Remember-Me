"""Phase 2 Graphiti adapter preparation; deliberately not wired into live APIs.

Graphiti is a rebuildable retrieval projection. Only active, authorized Memory
IDs may return to Backend; generated graph text never becomes SUBJECT evidence.
Backend must check consent before indexing/search and commit revision changes
before a correction/deletion is visible. This adapter does not replace that gate.
"""

from __future__ import annotations

import hashlib
import json
from math import isfinite
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5


class GraphitiClient(Protocol):
    async def add_episode(self, **kwargs: Any) -> Any: ...
    async def search(self, query: str, *, group_ids: list[str], num_results: int) -> list[Any]: ...
    async def remove_episode(self, episode_uuid: str) -> None: ...


@dataclass(frozen=True)
class ProjectionMemory:
    subject_id: str
    memory_id: str
    episode_id: str
    statement: str
    source_type: str
    evidence_ids: tuple[str, ...]
    occurred_at: datetime
    model_version: str
    prompt_version: str
    schema_version: str
    confidence: float


class GraphitiProjection:
    def __init__(self, client: GraphitiClient, *, subject_id: str,
                 revision: int, memories: tuple[ProjectionMemory, ...],
                 json_episode_type: Any) -> None:
        if not subject_id.strip() or revision < 1:
            raise ValueError("A subject and committed positive model revision are required")
        for item in memories:
            if (item.subject_id != subject_id or not item.memory_id.strip()
                    or not item.episode_id.strip() or not item.statement.strip()
                    or not item.evidence_ids or any(not eid.strip() for eid in item.evidence_ids)
                    or not all(value.strip() for value in (item.model_version, item.prompt_version, item.schema_version))
                    or not isfinite(item.confidence) or not 0 <= item.confidence <= 1
                    or item.source_type not in {"SUBJECT", "THIRD_PARTY", "AI_INFERENCE", "OBJECTIVE", "CALIBRATION"}
                    or item.occurred_at.tzinfo is None or item.occurred_at.utcoffset() is None):
                raise ValueError("Projection memories must be scoped, evidence-linked and dated")
        if len({item.memory_id for item in memories}) != len(memories):
            raise ValueError("Duplicate memory IDs are not allowed")
        self.client = client
        self.subject_id = subject_id
        self.revision = revision
        # Revision-specific groups make obsolete projections unreachable from
        # current queries, even while asynchronous removal is still pending.
        scope = json.dumps([subject_id, revision], separators=(",", ":"))
        self.group_id = "rm_" + hashlib.sha256(scope.encode()).hexdigest()
        self.memories = memories
        self.json_episode_type = json_episode_type
        self._by_uuid = {self._uuid(item.memory_id): item.memory_id for item in memories}

    def _uuid(self, memory_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, self.group_id + "/" + memory_id))

    async def index(self) -> None:
        for item in self.memories:
            await self.client.add_episode(
                name=item.memory_id,
                uuid=self._uuid(item.memory_id),
                group_id=self.group_id,
                source=self.json_episode_type,
                source_description="Remember Me derived Memory projection; not an original quotation",
                reference_time=item.occurred_at,
                episode_body=json.dumps({
                    "memory_id": item.memory_id, "episode_id": item.episode_id,
                    "statement": item.statement, "source_type": item.source_type,
                    "evidence_ids": item.evidence_ids,
                    "model_version": item.model_version, "prompt_version": item.prompt_version,
                    "schema_version": item.schema_version, "confidence": item.confidence,
                }, ensure_ascii=False),
                update_communities=False,
            )

    async def candidates(self, query: str, *, limit: int = 8) -> list[str]:
        if not query.strip() or not 1 <= limit <= 8:
            raise ValueError("A non-empty query and limit between 1 and 8 are required")
        edges = await self.client.search(query, group_ids=[self.group_id], num_results=limit)
        result: list[str] = []
        for edge in edges:
            if getattr(edge, "group_id", None) != self.group_id:
                continue
            episodes = getattr(edge, "episodes", None)
            if (not isinstance(episodes, (list, tuple)) or not episodes
                    or any(not isinstance(identifier, str) or identifier not in self._by_uuid
                           for identifier in episodes)):
                continue
            for identifier in episodes:
                memory_id = self._by_uuid[identifier]
                if memory_id not in result:
                    result.append(memory_id)
        return result[:limit]

    async def remove(self) -> None:
        # Removal is explicit. Never swallow cleanup failures or claim that
        # source deletion is complete merely because retrieval was invalidated.
        for identifier in self._by_uuid:
            await self.client.remove_episode(identifier)
