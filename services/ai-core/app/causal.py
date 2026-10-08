"""Optional schema worker output: quoted, subjective causal assertions."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .errors import EvidenceInvalid

VERSION = "temporal-causal-v1"


class Anchor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_index: int | None = Field(default=None, ge=0)
    memory_item_id: str | None = None
    quote: str = Field(min_length=1, max_length=500)
    time_text: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def one_reference(self):
        if (self.memory_index is None) == (self.memory_item_id is None):
            raise ValueError("Anchor requires exactly one memory reference")
        return self


class CausalLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assertion_memory_index: int = Field(ge=0)
    relation: Literal["REPORTED_CAUSE", "DENIES_CAUSE", "BEFORE", "ASSOCIATED_WITH", "HYPOTHESIS"]
    cause: Anchor
    effect: Anchor
    quote: str = Field(min_length=1, max_length=1000)
    context: str | None = Field(default=None, max_length=200)


def attach(links, output, current):
    evidence = {e.evidence_id: e for e in output.evidence}
    old = {m["memory_item_id"]: m for m in current if isinstance(m, dict) and "memory_item_id" in m}

    def new_snapshot(index):
        if index >= len(output.memory_items):
            raise EvidenceInvalid("Causal anchor references unknown memory")
        m = output.memory_items[index]
        return {"memory_index": index, "content": m.content,
                "evidence": [evidence[e].model_dump(exclude_none=True) for e in m.evidence_ids]}

    def grounded(snapshot, quote):
        sources = snapshot.get("evidence", []) if snapshot else []
        if not quote.strip() or not sources or any(e.get("source_type") not in {"SUBJECT", "CALIBRATION"} for e in sources):
            raise EvidenceInvalid("Causal assertion requires own evidence")
        refs = [e["evidence_id"] for e in sources if quote in (e.get("excerpt") or "")]
        if not refs:
            raise EvidenceInvalid("Causal quote does not resolve to source evidence")
        return refs

    def anchor(a):
        snapshot = new_snapshot(a.memory_index) if a.memory_index is not None else old.get(a.memory_item_id)
        refs = grounded(snapshot, a.quote)
        if a.time_text and (not a.time_text.strip() or not any(a.time_text in (e.get("excerpt") or "")
                                                             for e in snapshot["evidence"] if e["evidence_id"] in refs)):
            raise EvidenceInvalid("Event time is not in the anchor evidence")
        return {**({"memory_index": a.memory_index} if a.memory_index is not None else {"memory_item_id": a.memory_item_id}),
                "content": snapshot["content"], "evidence_ids": refs, "quote": a.quote, "time_text": a.time_text}

    for link in links:
        assertion = new_snapshot(link.assertion_memory_index)
        refs = grounded(assertion, link.quote)
        if link.context and link.context not in link.quote:
            raise EvidenceInvalid("Causal context must be explicit in the assertion quote")
        cause, effect = anchor(link.cause), anchor(link.effect)
        if cause == effect:
            raise EvidenceInvalid("Causal self-loop is invalid")
        relation = link.relation
        if relation == "REPORTED_CAUSE":
            if any(w in link.quote for w in ("不是因为", "并非因为", "并没有导致", "没有导致", "不是原因")):
                relation = "DENIES_CAUSE"
            elif any(w in link.quote for w in ("可能", "也许", "或许", "不确定", "猜测")):
                relation = "HYPOTHESIS"
            elif not any(w in link.quote for w in ("因为", "导致", "所以", "使我", "让我", "原因")):
                raise EvidenceInvalid("Reported causality needs an explicit causal statement")
        if relation == "DENIES_CAUSE" and not any(w in link.quote for w in ("不是", "并非", "没有", "无关", "不导致")):
            raise EvidenceInvalid("Causal denial is not explicit")
        memory = output.memory_items[link.assertion_memory_index]
        meta = dict(memory.metadata or {})
        entries = meta.setdefault("temporal_causal", [])
        entry = {"version": VERSION, "input_statement": memory.content, "relation": relation,
                 "cause": cause, "effect": effect, "quote": link.quote, "context": link.context,
                 "evidence_ids": refs, "model_version": output.model_version}
        if entry not in entries:
            entries.append(entry)
        memory.metadata = meta
