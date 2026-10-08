"""Deterministic, evidence-aware scheduling after model and calibration commits."""
from sqlalchemy import select

from .models import CalibrationRun, CaptureQuestion, Episode, MemoryItem, PERSON_DOMAINS, PersonTrait, utcnow
from uuid import uuid4
from datetime import timedelta
from .capture_policy import burden, evaluate, learn

QUESTIONS = {
    "IDENTITY": "你会怎样向一个刚认识的人介绍自己？",
    "EPISODIC_MEMORY": "有没有一段经历，对现在的你影响特别大？",
    "RELATIONSHIPS": "你生命中现在最重要的人是谁？你们的关系是什么样的？",
    "PREFERENCES": "最近有什么东西是你特别喜欢，或者特别不喜欢的？",
    "VALUES_BELIEFS": "遇到两难选择时，你通常最看重什么？",
    "DECISION_PATTERNS": "你做一个重要决定时，通常会先做什么？",
    "EXPRESSION": "你希望别人用什么样的方式跟你交流？",
}
DIMENSION_DOMAIN = {"DECISION": "DECISION_PATTERNS", "REASONING": "DECISION_PATTERNS",
                    "VALUE_PRIORITY": "VALUES_BELIEFS", "EMOTIONAL_REACTION": "EPISODIC_MEMORY", "EXPRESSION": "EXPRESSION"}
PRIORITY = {"contradiction": 100, "calibration_gap": 90, "missing_domain": 70,
            "weak_evidence": 50, "deepen_pattern": 30}


def plan(session, subject_id: str, *, limit: int = 3, now=None) -> list[CaptureQuestion]:
    session.flush()
    now = now or utcnow()
    traits = list(session.scalars(select(PersonTrait).where(PersonTrait.subject_id == subject_id,
                                                           PersonTrait.status != "superseded")))
    history = list(session.scalars(select(CaptureQuestion).where(CaptureQuestion.subject_id == subject_id)))
    episodes = list(session.scalars(select(Episode).where(Episode.subject_id == subject_id).order_by(Episode.created_at)))
    load = burden(episodes, now)
    if load["paused"]:
        return []  # Preserve pending IDs; elapsed rest, not refresh, reopens them.
    answered_keys = {(q.text, q.target_domain, tuple(sorted(q.evidence_ids))) for q in history if q.status == "answered"}
    answered_gaps = {q.target_domain for q in history if q.status == "answered" and q.reason == "missing_domain"}
    candidates = []

    def add(text, domain, reason, evidence):
        refs = sorted(set(evidence))
        key = (text, domain, tuple(refs))
        if key not in answered_keys and not any(c[0] == key for c in candidates):
            candidates.append((key, reason, refs))

    for trait in traits:
        if trait.status == "unresolved":
            related = sorted(set(trait.evidence_ids + trait.counter_evidence_ids))
            if any(reason == "contradiction" and key[1] == trait.domain and refs == related for key, reason, refs in candidates):
                continue
            add(f"前面你对「{trait.statement}」有过不同说法。现在你会怎么描述它？", trait.domain,
                "contradiction", related)
    rows = session.execute(select(MemoryItem, Episode).join(Episode).where(
        Episode.subject_id == subject_id, MemoryItem.deleted_at.is_(None))).all()
    live_evidence = {eid for m, _ in rows for eid in m.evidence_ids}
    episodes_for_memory = {m.memory_item_id: e.episode_id for m, e in rows}
    live_memories = {m.memory_item_id: m for m, _ in rows}
    from .models import as_utc, Evidence
    own_memories = [m for m, _ in rows if m.evidence_ids and all(
        (ev := session.get(Evidence, eid)) is not None and ev.source_type in {"SUBJECT", "CALIBRATION"}
        for eid in m.evidence_ids)]
    learned = learn(history, episodes, own_memories, traits, now)
    last_answers = {}
    for e in episodes:
        q = next((q for q in history if q.question_id == (e.capture_metadata or {}).get("question_id")
                  and q.status == "answered"), None)
        if q and any(m.episode_id == e.episode_id for m in own_memories):
            last_answers[q.target_domain] = max(last_answers.get(q.target_domain, as_utc(e.created_at)), as_utc(e.created_at))
    ever_linked = {(e.capture_metadata or {}).get("question_id") for e in session.scalars(select(Episode).where(Episode.subject_id == subject_id))}
    live_answers = {(e.capture_metadata or {}).get("question_id") for _, e in rows}
    # An answered gap supported only by deleted records becomes a gap again.
    # Preserve older explicit/manual answer records that had no Episode link.
    retired_answers = [q for q in history if q.status == "answered" and q.reason == "missing_domain"
                       and q.question_id in ever_linked and q.question_id not in live_answers]
    for question in retired_answers:
        answered_keys.discard((question.text, question.target_domain, tuple(sorted(question.evidence_ids))))
    answered_gaps = {q.target_domain for q in history if q.status == "answered" and q.reason == "missing_domain" and q not in retired_answers}
    for calibration in session.scalars(select(CalibrationRun).where(
            CalibrationRun.subject_id == subject_id, CalibrationRun.status == "complete").order_by(CalibrationRun.created_at.desc())):
        diffs = [d for d in calibration.dimension_diffs if d.get("alignment") in {"PARTIAL", "DIFFERENT"}]
        refs = [eid for m, e in rows if e.episode_id == calibration.human_episode_id for eid in m.evidence_ids]
        snapshot_valid = all((memory := live_memories.get(item["memory_item_id"])) is not None
                             and memory.content == item["content"] and memory.evidence_ids == item["evidence_ids"]
                             for item in calibration.source_snapshot)
        if diffs and calibration.suggested_question and refs and snapshot_valid and set(calibration.locked_evidence_ids) <= live_evidence:
            add(calibration.suggested_question, DIMENSION_DOMAIN[diffs[0]["dimension"]], "calibration_gap", refs)
    covered = {t.domain for t in traits}
    for domain in PERSON_DOMAINS:
        if domain not in covered and domain not in answered_gaps:
            add(QUESTIONS[domain], domain, "missing_domain", [])
    for domain in PERSON_DOMAINS:
        domain_traits = [t for t in traits if t.domain == domain and t.status == "active"]
        if not domain_traits or domain == "EPISODIC_MEMORY":
            continue
        trait = min(domain_traits, key=lambda t: (len({episodes_for_memory.get(mid) for mid in t.memory_item_ids}), t.confidence, t.trait_id))
        independent = len({episodes_for_memory[mid] for mid in trait.memory_item_ids if mid in episodes_for_memory})
        weak = trait.confidence < .6 or independent < 2
        if domain in last_answers and now - last_answers[domain] < timedelta(hours=24):
            continue
        add(f"关于「{trait.statement}」，能说一次具体经历，以及什么时候会例外吗？", domain,
            "weak_evidence" if weak else "deepen_pattern", trait.evidence_ids)
    from .temporal_reasoning import graph, clarification_questions
    for text, refs in clarification_questions(graph(session, subject_id)):
        add(text, "DECISION_PATTERNS", "causal_gap", refs)
    evaluations = {c[0]: evaluate(c[0][1], c[1], c[2], traits, learned, load, now,
                                last_answers.get(c[0][1])) for c in candidates}
    # Greedy marginal utility penalizes redundant evidence/domain in one round.
    selected = []
    remaining = list(candidates)
    while remaining and len(selected) < min(max(0, limit), 4, load["budget"]):
        def marginal(c):
            overlap = max((len(set(c[2]) & set(s[2])) / max(1, len(set(c[2]) | set(s[2])))
                           for s in selected), default=0)
            domain_repeat = any(c[0][1] == s[0][1] for s in selected)
            return evaluations[c[0]]["score"] * (1 - .7 * overlap) * (.55 if domain_repeat else 1)
        remaining.sort(key=lambda c: (-marginal(c), PERSON_DOMAINS.index(c[0][1]), c[0][0]))
        selected.append(remaining.pop(0))
    retained = []
    for key, reason, refs in selected:
        text, domain, _ = key
        existing = next((q for q in history if q.status == "pending" and q.text == text
                         and q.target_domain == domain and q.reason == reason and sorted(q.evidence_ids) == refs), None)
        if existing is None:
            existing = CaptureQuestion(question_id="question_" + uuid4().hex[:16], subject_id=subject_id,
                                       text=text, target_domain=domain, reason=reason, evidence_ids=refs,
                                       status="pending", created_at=utcnow())
            existing.policy_snapshot = evaluations[key]
            session.add(existing)
        else:
            # Preserve the pre-answer baseline while keeping current ranking.
            existing.policy_snapshot = {**evaluations[key], "baseline": (existing.policy_snapshot or {}).get(
                "baseline", evaluations[key]["baseline"])}
        retained.append(existing)
    for question in history:
        key = (question.text, question.target_domain, tuple(sorted(question.evidence_ids)))
        if question.status == "pending" and question not in retained and key not in evaluations:
            question.status = "skipped"
    return retained
