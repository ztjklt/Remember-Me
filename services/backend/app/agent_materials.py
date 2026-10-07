"""Sentence-level provenance without modifying the original transcript or v0.1 evidence."""

from hashlib import sha256
import re
from remember_contracts.agent import Material

REPORTED = re.compile(r"(?:女儿|儿子|朋友|医生|同事|妈妈|爸爸|他|她)(?:说|觉得|认为)[：:，,]?")
SENTENCE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;\n]*")


def resolve_speakers(materials: list[Material], transcripts: dict[str, str]) -> list[Material]:
    resolved = {}
    for material in materials:
        start, end = map(int, material.source_ref.rsplit("#span:", 1)[1].split("-"))
        # Classify in the full sentence's context, even when extraction omitted "同事说".
        spans = [(max(start, m.start()), min(end, m.end()), bool(REPORTED.search(m.group())))
                 for m in SENTENCE.finditer(transcripts[material.episode_id]) if m.start() < end and m.end() > start]
        reported = [third for _, _, third in spans]
        if not any(reported) or all(reported):
            parts = [material.model_copy(update={"source_type": "THIRD_PARTY" if any(reported) else "SUBJECT"})]
        else:
            parts = []
            for left, right, third in spans:
                ref = f"episode:{material.episode_id}#span:{left}-{right}"
                parts.append(material.model_copy(update={
                    "evidence_id": "sp_" + sha256(ref.encode()).hexdigest()[:40],
                    "source_ref": ref, "excerpt": transcripts[material.episode_id][left:right],
                    "source_type": "THIRD_PARTY" if third else "SUBJECT",
                }))
        for part in parts:
            resolved.setdefault(part.source_ref, part)
    return list(resolved.values())
