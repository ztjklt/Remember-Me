"""Source-handle extraction: exact spans plus quoted semantic anchors.

Anchors describe where a model found a condition, not verified personality or
entity identities. All semantic assertions remain AI_INFERENCE.
"""
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .errors import AIOutputInvalid

VERSION = 'weixin-memory-semantic-units-v5'


class Anchors(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    subject: list[str] = Field(default_factory=list, max_length=8)
    time: list[str] = Field(default_factory=list, max_length=8)
    conditions: list[str] = Field(default_factory=list, max_length=8)
    uncertainty: list[str] = Field(default_factory=list, max_length=8)
    negation: list[str] = Field(default_factory=list, max_length=8)
    reported_speech: list[str] = Field(default_factory=list, max_length=8)


class Unit(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    statement: str = Field(min_length=1, max_length=2000)
    domain: Literal['IDENTITY','EPISODIC_MEMORY','RELATIONSHIPS','PREFERENCES','VALUES_BELIEFS','DECISION_PATTERNS','EXPRESSION']
    memory_type: Literal['EVENT','PERSON','RELATIONSHIP','PREFERENCE','VALUE','EMOTION']
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    source_ids: list[str] = Field(min_length=1, max_length=12)
    anchors: Anchors = Field(default_factory=Anchors)

    @field_validator('statement')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('Blank statement')
        return value


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    memories: list[Unit] = Field(max_length=24)


def ground_units(raw, matches, request, version):
    selected = Selection.model_validate(raw)
    sources = {f's{i}': m for i, m in enumerate(matches, 1)}
    positions = {key: index for index, key in enumerate(sources)}
    output = dict(memory_items=[], graph_updates=[], persona_updates=[], evidence=[], model_version=version)
    evidence_by_span = {}
    seen = set()
    for unit in selected.memories:
        ids = unit.source_ids
        if len(ids) != len(set(ids)) or any(i not in sources for i in ids):
            raise AIOutputInvalid('Unknown or duplicate memory source')
        # Preserve intervening qualifiers. No synthetic concatenated quote or
        # first-occurrence search: each original span keeps its actual offset.
        indices = [positions[i] for i in ids]
        spans = matches[min(indices):max(indices)+1]
        identity = (unit.statement, tuple(m.span() for m in spans))
        if identity in seen: continue
        seen.add(identity)
        anchors = unit.anchors.model_dump()
        for phrases in anchors.values():
            if any(not p.strip() or not any(p in m.group() for m in spans) for p in phrases):
                raise AIOutputInvalid('Semantic anchor has no exact source')
        evidence_ids = []
        for match in spans:
            start, end = match.span()
            if (start, end) not in evidence_by_span:
                eid = 'ev_' + uuid4().hex[:16]
                evidence_by_span[start, end] = eid
                output['evidence'].append(dict(evidence_id=eid, source_type='SUBJECT',
                    source_ref=f'episode:{request.payload.episode_id}#span:{start}-{end}',
                    excerpt=match.group(), span_start=start, span_end=end, confidence=unit.confidence))
            evidence_ids.append(evidence_by_span[start, end])
        output['memory_items'].append(dict(memory_type=unit.memory_type, content=unit.statement,
            source_type='AI_INFERENCE', evidence_ids=evidence_ids, confidence=unit.confidence,
            model_version=version, prompt_version=request.prompt_version, schema_version=request.schema_version,
            metadata={'domain':unit.domain, 'semantic_anchors':anchors}))
        output['persona_updates'].append(dict(trait_id='trait_'+uuid4().hex[:16],domain=unit.domain,
            statement=unit.statement,context=''.join(m.group() for m in spans),confidence=unit.confidence,
            source_type='AI_INFERENCE',evidence_ids=evidence_ids,counter_evidence_ids=[],
            status='active',model_version=version))
        if unit.memory_type in {'EVENT','PERSON','RELATIONSHIP'}:
            output['graph_updates'].append(dict(fact_id='fact_'+uuid4().hex[:16],
                subject_id=request.payload.subject_id,kind=unit.memory_type,content=unit.statement,
                evidence_ids=evidence_ids,model_version=version))
    return output
