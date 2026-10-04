"""IDs are assigned by trusted code, stable within an Episode and globally scoped."""

import hashlib
import json


def canonical_evidence_id(episode_id: str, source: object) -> str:
    values = [episode_id] + [
        getattr(source, key, None)
        for key in ("source_ref", "span_start", "span_end", "excerpt", "source_type")
    ]
    return (
        "ev_"
        + hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()[
            :40
        ]
    )
