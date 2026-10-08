"""Phase 4 immutable-baseline preparation; no activation endpoint is exposed.

Activation proof, recipient grants and persistence require a reviewed Contract
proposal. This value object cannot grant access or authorize a new intent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .models import PERSON_DOMAINS


@dataclass(frozen=True)
class FrozenBaseline:
    subject_id: str
    revision: int
    frozen_at: datetime
    _payload: bytes

    @classmethod
    def freeze(cls, snapshot: dict[str, Any], *, subject_id: str,
               authorized_activation: bool, frozen_at: datetime) -> "FrozenBaseline":
        if not authorized_activation:
            raise PermissionError("Prior subject authorization must be verified before activation")
        if (not subject_id.strip() or snapshot.get("subject_id") != subject_id
                or not isinstance(snapshot.get("version"), int)
                or isinstance(snapshot.get("version"), bool) or snapshot["version"] < 1
                or frozen_at.tzinfo is None or frozen_at.utcoffset() is None):
            raise ValueError("A scoped, versioned snapshot and timezone-aware activation time are required")
        domains = snapshot.get("domains")
        if (not isinstance(domains, list) or len(domains) != len(PERSON_DOMAINS)
                or any(not isinstance(item, dict) for item in domains)
                or {item.get("domain") for item in domains} != set(PERSON_DOMAINS)):
            raise ValueError("All seven person domains must be preserved")
        if "recipient_context" in snapshot or "world_context" in snapshot:
            raise ValueError("Recipient/world context must be separate from the historical person")
        facts = snapshot.get("graph_facts", [])
        if not isinstance(facts, list):
            raise ValueError("Graph facts must preserve the snapshot list")
        records = list(facts)
        for domain in domains:
            traits = domain.get("traits")
            if not isinstance(traits, list):
                raise ValueError("Each person domain must preserve its trait list")
            records.extend(traits)
        for record in records:
            if (not isinstance(record, dict) or not record.get("evidence_ids")
                    or not isinstance(record["evidence_ids"], list)
                    or any(not isinstance(item, str) or not item.strip() for item in record["evidence_ids"])
                    or not isinstance(record.get("model_version"), str) or not record["model_version"].strip()
                    or record.get("subject_id", subject_id) != subject_id):
                raise ValueError("Frozen records must preserve scoped evidence and model versions")
        payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        return cls(subject_id, snapshot["version"], frozen_at, payload)

    @property
    def fingerprint(self) -> str:
        # Content fingerprint only, not a digital signature or proof of consent.
        return hashlib.sha256(self._payload).hexdigest()

    def view(self) -> dict[str, Any]:
        # Return a fresh copy. Neither a recipient nor later world context can
        # mutate the captured historical baseline through an object reference.
        return json.loads(self._payload)

    def with_context(self, *, world_context: dict[str, Any],
                     recipient_context: dict[str, Any]) -> dict[str, Any]:
        return {"baseline": self.view(),
                "world_context": json.loads(json.dumps(world_context, allow_nan=False)),
                "recipient_context": json.loads(json.dumps(recipient_context, allow_nan=False))}
