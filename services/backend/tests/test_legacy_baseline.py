from datetime import datetime, timezone
from dataclasses import FrozenInstanceError

import pytest

from app.legacy_baseline import FrozenBaseline
from app.models import PERSON_DOMAINS


def snapshot():
    return {"subject_id": "original-subject", "version": 4,
            "domains": [{"domain": name, "traits": []} for name in PERSON_DOMAINS],
            "graph_facts": []}


def freeze(data, **changes):
    options = dict(subject_id="original-subject", authorized_activation=True,
                   frozen_at=datetime(2026, 10, 9, tzinfo=timezone.utc))
    options.update(changes)
    return FrozenBaseline.freeze(data, **options)


def test_world_and_recipient_changes_cannot_rewrite_historical_person():
    original = snapshot()
    original["domains"][0]["traits"] = [{"statement": "我喜欢安静", "evidence_ids": ["ev-1"],
                                        "model_version": "model-v1"}]
    baseline = freeze(original)
    fingerprint = baseline.fingerprint
    original["domains"][0]["traits"][0]["statement"] = "改写"
    view = baseline.with_context(world_context={"year": 2040}, recipient_context={"name": "recipient"})
    view["baseline"]["domains"][0]["traits"][0]["statement"] = "家属改写"
    assert baseline.view()["domains"][0]["traits"][0]["statement"] == "我喜欢安静"
    assert baseline.fingerprint == fingerprint
    with pytest.raises(FrozenInstanceError):
        baseline.revision = 5


def test_activation_without_authorization_or_cross_subject_is_refused():
    with pytest.raises(PermissionError):
        freeze(snapshot(), authorized_activation=False)
    with pytest.raises(ValueError):
        freeze(snapshot(), subject_id="recipient")


def test_freeze_preserves_domains_and_requires_model_evidence():
    data = snapshot()
    data["domains"].pop()
    with pytest.raises(ValueError):
        freeze(data)
    data = snapshot()
    data["domains"][0]["traits"] = [{"statement": "无证据结论"}]
    with pytest.raises(ValueError):
        freeze(data)


@pytest.mark.parametrize("fact", [
    {"subject_id": "recipient", "evidence_ids": ["ev-1"], "model_version": "model-v1"},
    {"subject_id": "original-subject", "evidence_ids": [], "model_version": "model-v1"},
    {"subject_id": "original-subject", "evidence_ids": ["ev-1"], "model_version": ""},
])
def test_graph_facts_cannot_lose_scope_or_provenance(fact):
    data = snapshot()
    data["graph_facts"] = [fact]
    with pytest.raises(ValueError):
        freeze(data)
