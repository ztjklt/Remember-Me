"""Private preparation for marker follow-ups, deliberately not an HTTP route.

The future adapter must verify audio/time alignment and ownership before making
a binding. This planner neither validates SDK timestamps nor grants access.
"""
from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
import hashlib
import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from .narrative import fingerprint
from .rag_contract import AuthorizedSnapshot, Identifier, RagEvidenceRef

PLANNER_VERSION = 'marked-followup-v1'


class MarkerBinding(BaseModel):
    """Locally resolved references, never a raw SDK or client assertion."""
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, hide_input_in_errors=True)
    marker_id: Identifier
    subject_id: Identifier
    episode_id: Identifier
    source_basis: Annotated[StrictStr, Field(min_length=1, max_length=512)]
    evidence: Annotated[tuple[RagEvidenceRef, ...], Field(min_length=1, max_length=32)]

    @model_validator(mode='after')
    def unique_references(self):
        if len({ref.evidence_id for ref in self.evidence}) != len(self.evidence):
            raise ValueError('Duplicate marker references')
        return self


@dataclass(frozen=True)
class MarkedQuestion:
    id: str
    text: str
    reason: str
    evidence_ids: tuple[str, ...]
    episode_id: str
    source_basis: str
    marker_id: str


def next_marked_question(
    snapshot: AuthorizedSnapshot,
    marks: Iterable[MarkerBinding],
    *,
    suppressed_ids: Collection[str] = (),
) -> MarkedQuestion | None:
    """Return one optional meaning question over complete, unchanged sources.

    Caller supplies fresh owner-authorized sources and IDs currently answered,
    declined or snoozed. Recheck permissions/version before display and response.
    No model call, storage, truth score or automatic personality update occurs.
    """
    sources = snapshot.source_map
    bindings = [MarkerBinding.model_validate(mark.model_dump()) for mark in marks]
    for mark in sorted(bindings, key=lambda m: (m.episode_id, m.marker_id)):
        if mark.subject_id != snapshot.subject_id or mark.source_basis != snapshot.source_basis:
            continue
        if any(ref.evidence_id not in sources
               or sources[ref.evidence_id]['episode_id'] != mark.episode_id
               or sources[ref.evidence_id]['source_type'] != 'SUBJECT'
               or fingerprint(sources[ref.evidence_id]) != ref.fingerprint
               for ref in mark.evidence):
            continue
        refs = sorted((ref.evidence_id, ref.fingerprint) for ref in mark.evidence)
        # Repeated presses on identical anchors share a decision. Marker count
        # is not independent event support. A new binding preserves that ID if
        # an unrelated global revision changed but these sources stayed intact.
        key = [PLANNER_VERSION, snapshot.subject_id, mark.episode_id, refs]
        id = 'marked:' + hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()
        if id in suppressed_ids:
            continue
        return MarkedQuestion(id=id, marker_id=mark.marker_id, episode_id=mark.episode_id,
            source_basis=snapshot.source_basis, evidence_ids=tuple(ref[0] for ref in refs),
            text='你标记的这段对你有什么特别意义？也可以说说当时的想法，不想补充可以跳过。',
            reason='本人标记的瞬间尚可补充意义；标记本身不是事实或人格结论。')
    return None
