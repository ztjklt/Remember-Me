"""Prove proposed Graphiti projection cannot promote foreign/stale graph facts."""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.graph_projection import GraphitiProjection, ProjectionMemory


MEMORY = ProjectionMemory(
    subject_id="subject-a", memory_id="memory-1", episode_id="episode-1",
    statement="我现在更喜欢安静。", source_type="AI_INFERENCE",
    evidence_ids=("evidence-1",), occurred_at=datetime(2026, 10, 9, tzinfo=timezone.utc),
    model_version="model-v1", prompt_version="extract-v3", schema_version="0.2.0", confidence=0.7,
)


def projection(client=None, revision=1, memories=(MEMORY,)):
    return GraphitiProjection(client or AsyncMock(), subject_id="subject-a",
                             revision=revision, memories=memories, json_episode_type="json")


def test_index_preserves_source_type_and_reference_time_without_promoting_inference():
    client = AsyncMock()
    adapter = projection(client)
    asyncio.run(adapter.index())
    call = client.add_episode.call_args.kwargs
    assert call["group_id"] == adapter.group_id
    assert call["reference_time"] == MEMORY.occurred_at
    assert '"source_type": "AI_INFERENCE"' in call["episode_body"]
    assert '"episode-1"' in call["episode_body"]
    assert '"evidence-1"' in call["episode_body"]
    assert '"model-v1"' in call["episode_body"]
    assert call["update_communities"] is False


def test_graph_search_returns_only_current_memory_ids_not_generated_text():
    client = AsyncMock()
    adapter = projection(client)
    identifier = next(iter(adapter._by_uuid))
    client.search.return_value = [
        SimpleNamespace(group_id="other-subject", episodes=[identifier], fact="foreign"),
        SimpleNamespace(group_id=adapter.group_id, episodes=["stale-id"], fact="stale"),
        SimpleNamespace(group_id=adapter.group_id, episodes=[identifier, "foreign-id"], fact="mixed"),
        SimpleNamespace(group_id=adapter.group_id, episodes=[identifier], fact="invented quotation"),
        SimpleNamespace(group_id=adapter.group_id, episodes=[identifier], fact="duplicate"),
    ]
    assert asyncio.run(adapter.candidates("喜欢什么？")) == ["memory-1"]
    client.search.assert_awaited_once_with("喜欢什么？", group_ids=[adapter.group_id], num_results=8)


def test_revision_change_blocks_previous_projection_even_for_same_subject():
    old, new = projection(), projection(revision=2)
    assert old.group_id != new.group_id
    assert set(old._by_uuid).isdisjoint(new._by_uuid)
    assert projection().group_id == old.group_id


@pytest.mark.parametrize("memory", [
    replace(MEMORY, subject_id="other"), replace(MEMORY, evidence_ids=()),
    replace(MEMORY, occurred_at=datetime(2026, 10, 9)), replace(MEMORY, source_type="unknown"),
    replace(MEMORY, confidence=float("nan")), replace(MEMORY, model_version=""),
])
def test_invalid_memory_never_reaches_graph_provider(memory):
    with pytest.raises(ValueError):
        projection(memories=(memory,))


def test_cleanup_is_scoped_and_failure_remains_observable():
    client = AsyncMock()
    adapter = projection(client)
    asyncio.run(adapter.remove())
    client.remove_episode.assert_awaited_once_with(next(iter(adapter._by_uuid)))
    client.remove_episode.side_effect = RuntimeError("graph unavailable")
    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(adapter.remove())
