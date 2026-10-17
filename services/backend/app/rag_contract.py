"""Evidence-only retrieval boundary; authorization and original text stay local.

No HTTP client or external index is enabled here. The caller supplies a fresh,
server-authorized snapshot loader and still rechecks permissions before sending
model input and before publishing its answer. Providers rank references only.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError, field_validator, model_validator

from .errors import AppError
from .materials import ContextTooLarge
from .narrative import fingerprint


class RagResultInvalid(AppError):
    code = "RAG_RESULT_INVALID"
    http_status = 502


class RagSourceChanged(AppError):
    code = "SOURCE_CHANGED"
    http_status = 409


class RagContextIncomplete(AppError):
    code = "RAG_CONTEXT_INCOMPLETE"
    http_status = 409


class RagUnavailable(AppError):
    code = "RAG_UNAVAILABLE"
    http_status = 503
    retryable = True


class RagExternalDisabled(AppError):
    code = "RAG_EXTERNAL_DISABLED"
    http_status = 503


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


Identifier = Annotated[StrictStr, Field(min_length=1, max_length=64, pattern=r"^\S+$")]
Fingerprint = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]


class RagBudget(_WireModel):
    """Hit limit is for seeds. The final closure is checked, never sliced."""
    max_hits: Annotated[StrictInt, Field(ge=1, le=256)] = 8
    max_evidence: Annotated[StrictInt, Field(ge=1, le=256)] = 256
    max_characters: Annotated[StrictInt, Field(ge=1, le=24000)] = 24000
    max_authorized_evidence: Annotated[StrictInt, Field(ge=1, le=8192)] = 8192


class RagEvidenceRef(_WireModel):
    evidence_id: Identifier
    fingerprint: Fingerprint


class RagRequest(_WireModel):
    query: Annotated[StrictStr, Field(min_length=1, max_length=1000)]
    subject_id: Identifier
    authorized_evidence: Annotated[tuple[RagEvidenceRef, ...], Field(max_length=8192)]
    budget: RagBudget = Field(default_factory=RagBudget)

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value):
        if not value.strip():
            raise ValueError("Query cannot be blank")
        return value.strip()

    @model_validator(mode="after")
    def unique_refs(self):
        ids = [ref.evidence_id for ref in self.authorized_evidence]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate evidence references")
        if len(ids) > self.budget.max_authorized_evidence:
            raise ValueError("Authorized reference budget exceeded")
        return self


class RagHit(RagEvidenceRef):
    score: Annotated[float, Field(strict=True, allow_inf_nan=False)]


class RagResult(_WireModel):
    hits: Annotated[tuple[RagHit, ...], Field(max_length=256)]
    retriever_version: Annotated[StrictStr, Field(min_length=1, max_length=128)]

    @field_validator("retriever_version")
    @classmethod
    def nonblank_version(cls, value):
        if not value.strip():
            raise ValueError("Retriever version cannot be blank")
        return value.strip()

    @model_validator(mode="after")
    def unique_hits(self):
        ids = [hit.evidence_id for hit in self.hits]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate hits")
        return self


class RagProvider(Protocol):
    def retrieve(self, request: RagRequest) -> RagResult: ...


@dataclass(frozen=True)
class AuthorizedSource:
    """Local only. subject_id must be read from the owning Episode by the loader.

    Accept the flat canonical contextual_sources entry, before transport-only
    fields are added. The snapshot copies it so caller mutations cannot rewrite
    its captured fingerprint. Never construct this from a provider response.
    """
    subject_id: str
    source: Mapping[str, str | int | None]

    def __post_init__(self):
        data = dict(self.source)
        for key in ("evidence_id", "episode_id", "excerpt", "source_type"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise RagContextIncomplete("有效来源缺少可核对的本地字段。")
        if any(value is not None and type(value) not in (str, int) for value in data.values()):
            raise RagContextIncomplete("有效来源必须使用本地规范的平面证据字段。")
        object.__setattr__(self, "source", MappingProxyType(data))


@dataclass(frozen=True)
class ContextGroup:
    """Complete, locally authorized membership; never a provider-supplied group.

    For an understanding include ALL support and counter-evidence. Correction
    groups contain current effective sources only, never suppressed old words.
    """
    kind: Literal["story", "correction", "understanding"]
    evidence_ids: tuple[str, ...]

    def __post_init__(self):
        members = tuple(self.evidence_ids)
        if (self.kind not in {"story", "correction", "understanding"} or not members
                or any(not isinstance(i, str) or not i for i in members)
                or len(members) != len(set(members))):
            raise RagContextIncomplete("上下文关系必须包含完整且不重复的来源。")
        object.__setattr__(self, "evidence_ids", members)


@dataclass(frozen=True)
class AuthorizedSnapshot:
    subject_id: str
    source_basis: str
    sources: tuple[AuthorizedSource, ...]
    groups: tuple[ContextGroup, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "groups", tuple(self.groups))
        if not self.subject_id or not self.source_basis:
            raise RagContextIncomplete("缺少人物或来源版本。")
        if any(s.subject_id != self.subject_id for s in self.sources):
            raise RagSourceChanged("来源不属于当前人物。")
        ids = [s.source["evidence_id"] for s in self.sources]
        if len(ids) != len(set(ids)):
            raise RagContextIncomplete("本地来源存在重复标识，不能静默合并。")
        if any(not set(g.evidence_ids) <= set(ids) for g in self.groups):
            raise RagContextIncomplete("完整的来源、纠正或理解反例不可用，请重新核对。")

    @property
    def source_map(self) -> dict[str, dict]:
        return {s.source["evidence_id"]: dict(s.source) for s in self.sources}

    @property
    def signature(self) -> str:
        # Also catches a forgotten basis update: same-episode neighbors and
        # relation membership must not change unnoticed during retrieval.
        value = {
            "subject": self.subject_id, "basis": self.source_basis,
            "sources": {i: fingerprint(s) for i, s in self.source_map.items()},
            "groups": sorted((g.kind, sorted(g.evidence_ids)) for g in self.groups),
        }
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class RagSelection:
    sources: dict[str, dict]
    selected_evidence_ids: tuple[str, ...]
    hit_ids: tuple[str, ...]
    expanded_ids: tuple[str, ...]
    source_basis: str
    retriever_version: str
    character_count: int


def retrieve_context(
    query: str,
    load_snapshot: Callable[[], AuthorizedSnapshot],
    provider: RagProvider,
    *,
    budget: RagBudget | None = None,
) -> RagSelection:
    """Rank a fresh allowlist, reload locally, and close all safety groups.

    The loader must check current actor + story/cloud permissions and release
    its short transaction before returning; this function cannot authorize an
    actor, publish an answer, or replace the final source_basis check.
    """
    budget = RagBudget.model_validate((budget or RagBudget()).model_dump())
    before = load_snapshot()
    signature = before.signature
    source_map = before.source_map
    if len(source_map) > budget.max_authorized_evidence:
        raise ContextTooLarge("可检索来源标识超过预算，未截断或发送。")
    request = RagRequest(query=query, subject_id=before.subject_id,
        authorized_evidence=tuple(RagEvidenceRef(evidence_id=i, fingerprint=fingerprint(s))
                                  for i, s in source_map.items()), budget=budget)
    try:
        raw_result = provider.retrieve(request)
    except (RagExternalDisabled, RagSourceChanged, RagContextIncomplete):
        raise
    except ValidationError:
        raise RagResultInvalid("检索结果不符合证据引用合同。") from None
    except Exception:
        # Provider text/exception bodies can contain credentials. Never expose
        # them as an AppError or turn a transport failure into "no evidence".
        raise RagUnavailable("检索服务不可用，本次未生成回答。") from None
    try:
        current = load_snapshot()
    except AppError as exc:
        if exc.http_status in {401, 403, 404, 409}:
            raise RagSourceChanged("资料或授权已变化，请重新检索。") from None
        raise
    if current.signature != signature:
        raise RagSourceChanged("资料或授权已变化，请重新检索。")
    try:
        # Dump instances as well: model_construct must not bypass validation.
        result = RagResult.model_validate(raw_result.model_dump() if isinstance(raw_result, BaseModel) else raw_result)
    except (ValidationError, TypeError, ValueError):
        raise RagResultInvalid("检索结果不符合证据引用合同。") from None
    allowed = {r.evidence_id: r.fingerprint for r in request.authorized_evidence}
    if len(result.hits) > budget.max_hits:
        raise RagResultInvalid("检索命中超过约定预算，未截断。")
    if any(hit.evidence_id not in allowed or hit.fingerprint != allowed[hit.evidence_id] for hit in result.hits):
        raise RagResultInvalid("检索引用未知或过期，不能用于回答。")
    sources = current.source_map
    hit_ids = tuple(hit.evidence_id for hit in result.hits)
    selected = set(hit_ids)
    # Same Episode means every effective authorized source, NOT raw transcript
    # slicing. Never resurrect suppressed/replaced/revoked neighboring words.
    groups = [set(g.evidence_ids) for g in current.groups]
    by_episode: dict[str, set[str]] = {}
    for identifier, source in sources.items():
        by_episode.setdefault(source["episode_id"], set()).add(identifier)
    groups.extend(by_episode.values())
    changed = True
    while changed:
        changed = False
        for members in groups:
            if members & selected and not members <= selected:
                selected.update(members)
                changed = True
    selected_sources = {i: s for i, s in sources.items() if i in selected}
    # Count by identity, not deduplicated text; identical words from different
    # recordings are still separate evidence with separate provenance.
    count = sum(len(s["excerpt"]) + len(str(s.get("temporal_context") or "")) for s in selected_sources.values())
    if len(selected_sources) > budget.max_evidence or count > budget.max_characters:
        raise ContextTooLarge("完整来源、纠正和理解反例超过上下文预算；没有截断。")
    return RagSelection(sources=selected_sources,
        selected_evidence_ids=tuple(selected_sources), hit_ids=hit_ids,
        expanded_ids=tuple(i for i in selected_sources if i not in hit_ids),
        source_basis=current.source_basis, retriever_version=result.retriever_version,
        character_count=count)


class LocalRetrievalAdapter:
    """Reuse the existing local MemoryItem index, treating text only as hints.

    Optional local sources add lexical seeds for unextracted raw gaps. They are
    never on the wire and must match the request fingerprints. A valid embedding
    installation is still required for indexed MemoryItems; failure is explicit.
    """
    def __init__(self, session, encoder, *, episode_ids: set[str], reader: bool,
                 sources: Mapping[str, dict] | None = None):
        self.session = session
        self.encoder = encoder
        self.episode_ids = frozenset(episode_ids)
        self.reader = reader
        self.has_bound_sources = sources is not None
        self.sources = {i: dict(s) for i, s in (sources or {}).items()}

    def retrieve(self, request: RagRequest) -> RagResult:
        from . import retrieval
        refs = {r.evidence_id: r.fingerprint for r in request.authorized_evidence}
        if self.has_bound_sources:
            bound = {i: fingerprint(s) for i, s in self.sources.items()}
            if bound != refs or any(s["episode_id"] not in self.episode_ids for s in self.sources.values()):
                # Adapter construction can precede the fresh request snapshot.
                # An added/revoked Episode must not silently keep the old pool.
                raise RagSourceChanged("本地检索范围或来源已变化，请重新检索。")
        hints = retrieval.retrieve(self.session, request.subject_id, request.query,
            self.encoder, limit=request.budget.max_hits, episode_ids=set(self.episode_ids), reader=self.reader)
        # Retrieval writes only the derived, content/version-keyed vector cache.
        # Commit it before load_snapshot starts a NEW authorization transaction:
        # publication_lock intentionally rolls back any open transaction, which
        # otherwise made every spoken question re-embed the unchanged archive.
        # The caller still reloads permissions/fingerprints before using hints.
        self.session.commit()
        scores = {}
        for hint in hints:
            for evidence in hint["evidence"]:
                identifier = evidence["evidence_id"]
                if identifier in refs:
                    # Validate even local rankers; no NaN/bool coercion.
                    hit = RagHit(evidence_id=identifier, fingerprint=refs[identifier], score=hint["score"])
                    scores[identifier] = max(hit.score, scores.get(identifier, float("-inf")))
        for identifier, source in self.sources.items():
            if identifier not in refs:
                continue
            score = retrieval._lexical(request.query, source["excerpt"])
            if source.get('source_type')=='SUBJECT' and retrieval._self_name_hint(request.query,source['excerpt']):
                score=max(score,1.1)
            if score >= 0.35:
                scores[identifier] = max(score, scores.get(identifier, float("-inf")))
        # This is a seed budget, not truncation of an Episode or counterexample.
        seeds = sorted(scores, key=lambda i: (-scores[i], i))[:request.budget.max_hits]
        suffix = "+source-lexical-v2" if self.sources else ""
        return RagResult(hits=tuple(RagHit(evidence_id=i, fingerprint=refs[i], score=scores[i]) for i in seeds),
                         retriever_version="local-v1:" + self.encoder.version + suffix)


def build_rag_provider(session, encoder, *, episode_ids: set[str], reader: bool,
                       sources: Mapping[str, dict] | None = None,
                       external_enabled: bool = False) -> RagProvider:
    """Default to existing local retrieval; no external endpoint is invented."""
    if external_enabled:
        raise RagExternalDisabled("外部 RAG 尚未配置与验收，本次不会发送请求。")
    return LocalRetrievalAdapter(session, encoder, episode_ids=episode_ids, reader=reader, sources=sources)
