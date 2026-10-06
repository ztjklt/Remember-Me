"""Offline wire simulator. No claim of learned personality or semantic fidelity."""

import re
from ..errors import AIOutputInvalid

DOMAINS = {
    "EVENT": "EPISODIC_MEMORY",
    "PREFERENCE": "PREFERENCES",
    "PERSON": "RELATIONSHIPS",
    "RELATIONSHIP": "RELATIONSHIPS",
    "VALUE": "VALUES",
}


def generate(request):
    data = request.worker_input
    if request.task == "persona":
        by_id = {m["evidence_id"]: m for m in data["materials"]}
        changes = []
        for eid in data["new_evidence_ids"]:
            m = by_id[eid]
            if (
                m["source_type"] not in {"SUBJECT", "CALIBRATION"}
                or m["speaker_authority"] != "SELF_ATTESTED"
            ):
                continue
            text = m["excerpt"]
            # Deliberately avoid known reported speech. Real providers require quality evaluation.
            if re.search(r"(?:女儿|儿子|妈妈|爸爸|朋友|他|她)说[：:]", text):
                continue
            context = m["context"] or next(
                (w for w in ("工作日下班后", "下班后", "周末") if w in text), ""
            )
            domain = DOMAINS.get(m["memory_type"], "EPISODIC_MEMORY")
            if m["source_type"] == "CALIBRATION":
                domain = "PREFERENCES" if "喜欢" in text else "DECISION_PATTERNS"
            target = next(
                (
                    t
                    for t in data["snapshot"]["traits"]
                    if t["domain"] == domain
                    and t["context"] == context
                    and t["status"] != "SUPERSEDED"
                ),
                None,
            )
            action = "ADD"
            target_id = None
            if target and text == target["statement"]:
                action, target_id = "SUPPORT", target["trait_id"]
            elif target and ("现在" in text or "改为" in text):
                action, target_id = "CHANGE", target["trait_id"]
            elif target and "不喜欢" in text and "喜欢" in target["statement"]:
                action, target_id = "CONFLICT", target["trait_id"]
            changes.append(
                dict(
                    action=action,
                    target_trait_id=target_id,
                    domain=domain,
                    statement=text,
                    context=context,
                    evidence_ids=[eid],
                    confidence=0.55,
                    reason="[fixture] 原文投影，用于离线接线验证",
                )
            )
        return {"changes": changes}
    if request.task == "twin":
        # Offline transport simulator; it cannot establish semantic QA quality.
        materials = data["materials"] + data["corrections"]
        if not materials or "出生日期" in data["question"]:
            return dict(answerable=False, answer="没有相关材料", evidence_ids=[], limitations=["[fixture]"])
        m = max(materials, key=lambda item: (item["observed_at"], item["evidence_id"]))
        return dict(answerable=True, answer=m["excerpt"], evidence_ids=[m["evidence_id"]],
                    limitations=["[fixture] 离线投影，不代表真实推理能力。"])
    if request.task == "compare":
        equal = data["locked_answer"]["answer"].strip() == data["human_answer"].strip()
        return {
            "dimension_diffs": [
                dict(
                    dimension=d,
                    assessment="ALIGNED" if equal else "UNCERTAIN",
                    reason="[fixture] 文本相同"
                    if equal
                    else "[fixture] 文本不同，无法判定语义差异",
                )
                for d in (
                    "DECISION",
                    "REASONING",
                    "VALUE_PRIORITY",
                    "EMOTIONAL_REACTION",
                    "EXPRESSION",
                )
            ],
            "cause": "UNCERTAIN",
            "followup_questions": ["这个回答适用于什么时间和情境？"],
        }
    raise AIOutputInvalid("Unknown fixture worker")
