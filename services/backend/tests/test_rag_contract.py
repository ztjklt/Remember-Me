"""RAG is ranking, never an authority for provenance or authorization."""
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.materials import ContextTooLarge
from app.narrative import fingerprint
from app.rag_contract import (
    AuthorizedSnapshot, AuthorizedSource, ContextGroup, LocalRetrievalAdapter,
    RagBudget, RagContextIncomplete, RagExternalDisabled, RagHit,
    RagRequest, RagResult, RagResultInvalid, RagSourceChanged, RagUnavailable,
    build_rag_provider, retrieve_context,
)


def source(identifier, episode="ep1", text="普通小毛病，我愿意先修。", subject="s1", **extra):
    return AuthorizedSource(subject, {
        "evidence_id": identifier, "episode_id": episode, "excerpt": text,
        "source_type": "SUBJECT", "temporal_context": "", **extra,
    })


def snapshot(*sources, basis="basis1", groups=(), subject="s1"):
    return AuthorizedSnapshot(subject, basis, tuple(sources), tuple(groups))


class Provider:
    def __init__(self, identifiers=(), transform=None):
        self.identifiers = identifiers
        self.transform = transform
        self.calls = []

    def retrieve(self, request):
        self.calls.append(request)
        allowed = {r.evidence_id: r.fingerprint for r in request.authorized_evidence}
        result = {
            "hits": [{"evidence_id": i, "fingerprint": allowed[i], "score": 0.8}
                     for i in self.identifiers],
            "retriever_version": "test-local-v1",
        }
        return self.transform(result) if self.transform else RagResult.model_validate(result)


def test_name_lookup_selects_authorized_self_introduction_over_pronoun_overlap(monkeypatch):
    monkeypatch.setattr('app.retrieval.retrieve',lambda *a,**kw: [])
    current=snapshot(source('bio',text='我叫周明，今年六十岁，住在老街。'),
                     source('tea',text='你来之前打个电话，我在下棋。'))
    adapter=LocalRetrievalAdapter(SimpleNamespace(commit=lambda:None),SimpleNamespace(version='fixture'),
        episode_ids={'ep1'},reader=True,sources=current.source_map)
    result=retrieve_context('你叫什么名字？',lambda:current,adapter,budget=RagBudget(max_hits=1))
    assert result.hit_ids==('bio',)
    assert '周明' in result.sources['bio']['excerpt']
    from app.retrieval import _self_name_hint
    assert not _self_name_hint('我叫什么名字？','我叫周明，今年六十岁。')
    assert not _self_name_hint('你叫什么名字？','他说我叫周明，想来做客。')
    assert not _self_name_hint('你爱喝什么茶？','我叫周明，今年六十岁。')


def test_request_contains_only_query_subject_refs_budget_and_no_source_text():
    local = source("e1", text="唯一私密原文，不发送给检索端。")
    provider = Provider(["e1"])
    current = snapshot(local)
    selected = retrieve_context("修旧物？", lambda: current, provider)
    wire = provider.calls[0].model_dump(mode="json")
    assert set(wire) == {"query", "subject_id", "authorized_evidence", "budget"}
    assert set(wire["authorized_evidence"][0]) == {"evidence_id", "fingerprint"}
    assert wire["authorized_evidence"][0]["fingerprint"] == fingerprint(dict(local.source))
    assert "唯一私密原文" not in json.dumps(wire, ensure_ascii=False)
    assert selected.sources["e1"] == dict(local.source)
    assert selected.source_basis == "basis1"


def test_whole_episode_then_correction_then_support_counter_closure_is_complete():
    sources = [source("seed"), source("negation", text="但电线外露，不能带电拆。"),
               source("correction", "ep2", "后来请电工处理。", source_type="CALIBRATION"),
               source("counter", "ep3", "另一回直接更换。"), source("counter_context", "ep3", "那时已经有危险。")]
    groups = [ContextGroup("correction", ("negation", "correction")),
              ContextGroup("understanding", ("correction", "counter"))]
    current = snapshot(*sources, groups=groups)
    result = retrieve_context("先修吗？", lambda: current, Provider(["seed"]))
    assert set(result.sources) == {s.source["evidence_id"] for s in sources}
    assert result.hit_ids == ("seed",)
    assert result.expanded_ids == ("negation", "correction", "counter", "counter_context")
    assert result.character_count == sum(len(s.source["excerpt"]) for s in sources)


@pytest.mark.parametrize("budget", [RagBudget(max_characters=12), RagBudget(max_evidence=1)])
def test_budget_applies_after_expansion_and_never_returns_cut_context(budget):
    current = snapshot(source("e1", text="普通小毛病可以自己先检查。"),
                       source("e2", text="但涉及电线不能带电拆。"))
    with pytest.raises(ContextTooLarge):
        retrieve_context("怎么修？", lambda: current, Provider(["e1"]), budget=budget)


def test_same_text_distinct_sources_count_toward_budget_and_temporal_context_counts():
    current = snapshot(source("e1", text="相同", temporal_context="历史记载"),
                       source("e2", text="相同"))
    with pytest.raises(ContextTooLarge):
        retrieve_context("变化？", lambda: current, Provider(["e1"]), budget=RagBudget(max_characters=7))


def test_missing_counter_or_correction_fails_before_provider_call():
    provider = Provider(["e1"])
    with pytest.raises(RagContextIncomplete):
        current = snapshot(source("e1"), groups=[ContextGroup("understanding", ("e1", "private_counter"))])
        retrieve_context("？", lambda: current, provider)
    assert not provider.calls


@pytest.mark.parametrize("change", ["revoked", "modified", "basis", "subject", "group", "added_neighbor"])
def test_reload_rejects_mid_call_permission_source_or_group_changes(change):
    first = snapshot(source("e1"), source("e2", "ep2"))
    variants = {
        "revoked": snapshot(source("e2", "ep2")),
        "modified": snapshot(source("e1", text="已纠正的原文"), source("e2", "ep2")),
        "basis": snapshot(source("e1"), source("e2", "ep2"), basis="revoked-grant"),
        "subject": snapshot(source("e1", subject="s2"), subject="s2"),
        "group": snapshot(source("e1"), source("e2", "ep2"), groups=[ContextGroup("understanding", ("e1", "e2"))]),
        "added_neighbor": snapshot(source("e1"), source("e2", "ep2"), source("late_negation")),
    }
    states = iter((first, variants[change]))
    with pytest.raises(RagSourceChanged):
        retrieve_context("？", lambda: next(states), Provider(["e1"]))


def test_subject_mismatch_and_duplicate_local_evidence_are_rejected():
    with pytest.raises(RagSourceChanged):
        snapshot(source("foreign", subject="another-subject"))
    with pytest.raises(RagContextIncomplete):
        snapshot(source("e1"), source("e1"))


@pytest.mark.parametrize("fault", ["unknown", "stale", "duplicate", "text", "many", "version", "nan", "infinity", "bool"])
def test_untrusted_result_rejected_as_a_whole(fault):
    current = snapshot(source("e1"), source("e2", "ep2"))
    def corrupt(data):
        if fault == "unknown": data["hits"][0]["evidence_id"] = "private-or-foreign"
        if fault == "stale": data["hits"][0]["fingerprint"] = "0" * 64
        if fault == "duplicate": data["hits"] += data["hits"]
        if fault == "text": data["hits"][0]["excerpt"] = "外部伪造原话"
        if fault == "many": data["hits"].append({"evidence_id": "e2", "fingerprint": fingerprint(dict(current.sources[1].source)), "score": 0.7})
        if fault == "version": data["retriever_version"] = " "
        if fault == "nan": data["hits"][0]["score"] = float("nan")
        if fault == "infinity": data["hits"][0]["score"] = float("inf")
        if fault == "bool": data["hits"][0]["score"] = True
        return data
    with pytest.raises(RagResultInvalid):
        retrieve_context("？", lambda: current, Provider(["e1"], corrupt), budget=RagBudget(max_hits=1))


def test_constructed_pydantic_instance_cannot_bypass_result_validation():
    current = snapshot(source("e1"))
    bad_hit = RagHit.model_construct(evidence_id="e1", fingerprint="0" * 64, score=float("nan"))
    bad = RagResult.model_construct(hits=(bad_hit,), retriever_version="untrusted")
    with pytest.raises(RagResultInvalid):
        retrieve_context("？", lambda: current, Provider(transform=lambda _: bad))


def test_provider_failure_is_bounded_unavailable_not_empty_or_secret_text():
    current = snapshot(source("e1"))
    def fail(_): raise RuntimeError("secret-token-or-provider-body")
    with pytest.raises(RagUnavailable) as caught:
        retrieve_context("？", lambda: current, Provider(transform=fail))
    assert "secret-token" not in str(caught.value)


def test_empty_hits_still_rechecks_current_sources_and_is_a_valid_empty_selection():
    current = snapshot(source("e1"))
    calls = []
    def reload():
        calls.append(True)
        return current
    selected = retrieve_context("未知？", reload, Provider())
    assert len(calls) == 2
    assert selected.sources == {}
    assert selected.hit_ids == ()


def test_local_adapter_preserves_existing_retrieve_scope_and_filters_rank_hints(monkeypatch):
    from app import retrieval
    calls = []
    def retrieve(session, subject, question, encoder, limit, *, episode_ids, reader):
        calls.append((session, subject, question, encoder, limit, episode_ids, reader))
        return [
            {"score": 0.9, "evidence": [{"evidence_id": "unauthorized"}, {"evidence_id": "e1"}]},
            {"score": 0.8, "evidence": [{"evidence_id": "e1"}]},
        ]
    monkeypatch.setattr(retrieval, "retrieve", retrieve)
    session = SimpleNamespace(commit=lambda:None)
    encoder = SimpleNamespace(version="fixture-embedding-v1")
    adapter = build_rag_provider(session, encoder, episode_ids={"ep1"}, reader=True)
    assert isinstance(adapter, LocalRetrievalAdapter)
    current = snapshot(source("e1"), source("tail", text="但不能带电拆。"))
    result = retrieve_context("修理", lambda: current, adapter)
    assert calls == [(session, "s1", "修理", encoder, 8, {"ep1"}, True)]
    assert result.hit_ids == ("e1",)
    assert set(result.sources) == {"e1", "tail"}
    assert "fixture-embedding-v1" in result.retriever_version


def test_external_cannot_be_enabled_by_configuration_without_an_adapter():
    with pytest.raises(RagExternalDisabled):
        build_rag_provider(object(), object(), episode_ids=set(), reader=False, external_enabled=True)


def test_unextracted_original_can_seed_local_retrieval_without_a_memory_item(monkeypatch):
    from app import retrieval
    monkeypatch.setattr(retrieval, "retrieve", lambda *a, **kw: [])
    current = snapshot(source("raw", text="台灯坏了先看看原因。"),
                       source("condition", text="但电线露出来要先拔插头。"),
                       source("unrelated", "ep2", "晚饭吃面。"))
    adapter = build_rag_provider(SimpleNamespace(commit=lambda:None), SimpleNamespace(version="fixture"),
        episode_ids={"ep1", "ep2"}, reader=True, sources=current.source_map)
    selected = retrieve_context("台灯", lambda: current, adapter)
    assert selected.hit_ids == ("raw",)
    assert set(selected.sources) == {"raw", "condition"}
    assert "source-lexical-v2" in selected.retriever_version


def test_local_extra_source_or_stale_bound_source_fails(monkeypatch):
    from app import retrieval
    monkeypatch.setattr(retrieval, "retrieve", lambda *a, **kw: [])
    current = snapshot(source("e1", text="台灯"))
    sources = {**current.source_map, "foreign": dict(source("foreign", "ep-other", text="台灯").source)}
    adapter = build_rag_provider(object(), SimpleNamespace(version="fixture"),
        episode_ids={"ep1"}, reader=True, sources=sources)
    with pytest.raises(RagSourceChanged):
        retrieve_context("台灯", lambda: current, adapter)
    sources.pop("foreign")
    sources["e1"]["excerpt"] = "过期旧文本"
    stale = build_rag_provider(object(), SimpleNamespace(version="fixture"),
        episode_ids={"ep1"}, reader=True, sources=sources)
    with pytest.raises(RagSourceChanged):
        retrieve_context("台灯", lambda: current, stale)


@pytest.mark.parametrize("change", ["new_source", "revoked_source", "episode_scope"])
def test_changed_adapter_pool_is_rejected_before_index_access(monkeypatch, change):
    from app import retrieval
    calls = []
    monkeypatch.setattr(retrieval, "retrieve", lambda *a, **kw: calls.append(True) or [])
    one = snapshot(source("e1", text="台灯"))
    two = snapshot(source("e1", text="台灯"), source("e2", "ep2", "后来有例外。"))
    bound, current = (one, two) if change == "new_source" else (two, one)
    episodes = {"ep1", "ep2"}
    if change == "episode_scope":
        bound, current, episodes = one, one, {"ep2"}
    adapter = build_rag_provider(object(), SimpleNamespace(version="fixture"),
        episode_ids=episodes, reader=True, sources=bound.source_map)
    with pytest.raises(RagSourceChanged):
        retrieve_context("台灯", lambda: current, adapter)
    assert not calls


def test_revocation_during_retrieval_is_source_changed_not_not_found():
    from app.access import Hidden
    current = snapshot(source("e1"))
    reads = 0
    def reload():
        nonlocal reads
        reads += 1
        if reads == 2:
            raise Hidden("没有可访问的故事。")
        return current
    with pytest.raises(RagSourceChanged):
        retrieve_context("？", reload, Provider(["e1"]))


def test_initial_authorization_failure_keeps_its_status_and_never_calls_provider():
    from app.access import Hidden
    provider = Provider(["e1"])
    def denied(): raise Hidden("没有可访问的故事。")
    with pytest.raises(Hidden):
        retrieve_context("？", denied, provider)
    assert provider.calls == []


def test_embedding_failure_does_not_fall_back_to_lexical_unknown(monkeypatch):
    from app import retrieval
    def unavailable(*a, **kw): raise retrieval.EmbeddingUnavailable("model unavailable")
    monkeypatch.setattr(retrieval, "retrieve", unavailable)
    current = snapshot(source("e1", text="台灯"))
    adapter = build_rag_provider(object(), SimpleNamespace(version="fixture"),
        episode_ids={"ep1"}, reader=False, sources=current.source_map)
    with pytest.raises(RagUnavailable):
        retrieve_context("台灯", lambda: current, adapter)


def test_local_sources_are_detached_and_unknown_request_budget_is_rejected():
    raw = dict(source("e1").source)
    authorized = AuthorizedSource("s1", raw)
    raw["excerpt"] = "caller mutation"
    assert authorized.source["excerpt"] != "caller mutation"
    with pytest.raises(TypeError):
        authorized.source["excerpt"] = "cannot mutate snapshot"
    with pytest.raises(ValidationError):
        RagBudget(max_hits=True)


def test_authorized_reference_budget_fails_before_provider_and_no_list_is_sliced():
    current = snapshot(source("e1"), source("e2", "ep2"))
    provider = Provider(["e1"])
    with pytest.raises(ContextTooLarge):
        retrieve_context("？", lambda: current, provider, budget=RagBudget(max_authorized_evidence=1))
    assert not provider.calls


def test_selected_sources_and_ids_preserve_canonical_order_not_provider_text_order():
    current = snapshot(source("e1"), source("e2", "ep2"))
    selection = retrieve_context("？", lambda: current, Provider(["e2", "e1"]))
    assert selection.hit_ids == ("e2", "e1")
    assert selection.selected_evidence_ids == ("e1", "e2")


@pytest.mark.parametrize("changes", [{"query": " "}, {"subject_id": " "}, {"query": "x" * 1001},
                                       {"authorized_evidence": [{"evidence_id": "e1", "fingerprint": "bad"}]}])
def test_wire_request_validation(changes):
    payload = {"query": "？", "subject_id": "s1", "authorized_evidence": [], "budget": {}}
    payload.update(changes)
    with pytest.raises(ValidationError):
        RagRequest.model_validate(payload)
