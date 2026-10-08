"""Auditable Bayesian utility estimates, bounded burden and discounted learning.

Information gain is a binary observation-channel estimate, not measured Twin
fidelity. Rewards require surviving SUBJECT/CALIBRATION evidence. No provider,
third-party opinion or repeated GET can manufacture a successful interaction.
"""
from datetime import timedelta
import math
from hashlib import sha256

from .models import as_utc

VERSION = "adaptive-capture-v1"
IMPORTANCE = {"contradiction": 3.2, "calibration_gap": 3.0, "causal_gap": 2.4,
              "missing_domain": 1.8, "weak_evidence": 1.4, "deepen_pattern": 1.0}


def statement_hash(value):
    return sha256(value.encode()).hexdigest()


def entropy(p):
    p = max(0.0, min(1.0, p))
    return -sum(x * math.log2(x) for x in (p, 1 - p) if x > 0)


def information_gain(prior, reliability):
    """I(H; answer) for a symmetric noisy binary evidence channel, in bits."""
    reliability = max(.5, min(.95, reliability))
    observed = prior * reliability + (1 - prior) * (1 - reliability)
    return max(0.0, entropy(observed) - entropy(reliability))


def burden(episodes, now):
    recent = [e for e in episodes if 0 <= (now - as_utc(e.created_at)).total_seconds() < 3600]
    guided = [e for e in recent if (e.capture_metadata or {}).get("question_id")
              or (e.capture_metadata or {}).get("calibration_id")]
    minutes = sum(max(0, e.duration_ms or 0) for e in recent) / 60000
    burst = sum((now - as_utc(e.created_at)).total_seconds() < 1800 for e in guided)
    # Only confirmed, recent, explicit requests affect pacing. Quoted history
    # and inferred mood are not instructions. Free capture is never blocked.
    pause = False
    for e in recent:
        if not e.transcript_reviewed_at:
            continue
        text = (e.transcript or "").strip().strip("。！! ")
        if text in {"今天不想继续回答", "我想休息一下", "先暂停提问", "今天先到这里",
                    "我累了，先不回答了"}:
            pause = True
    stopped = pause or minutes >= 12 or burst >= 4
    return {"paused": stopped, "reason": "explicit_pause" if pause else "session_budget" if stopped else None,
            "recent_minutes": round(minutes, 3), "guided_burst": burst,
            "fatigue": min(1.0, minutes / 12 + burst / 8),
            "budget": 0 if stopped else 1 if minutes >= 6 or burst >= 2 else 3}


def learn(history, episodes, memories, traits, now):
    """Recompute from durable outcomes; source deletion removes its reward.

    Beta(3,1) prior avoids assuming a cold-start question is unanswerable.
    Discount with a 30-day half-life, plus bounded exploration in scoring.
    """
    by_question = {}
    for episode in episodes:
        qid = (episode.capture_metadata or {}).get("question_id")
        if qid:
            by_question.setdefault(qid, []).append(episode)
    by_episode = {}
    for memory in memories:
        by_episode.setdefault(memory.episode_id, []).append(memory)
    learned = {}
    for question in history:
        answers = by_question.get(question.question_id, [])
        if question.status != "answered" or not answers:
            continue
        # One answer interaction = one trial; duplicate excerpts are not trials.
        first = min(answers, key=lambda e: as_utc(e.created_at))
        live = [m for e in answers for m in by_episode.get(e.episode_id, [])]
        if not live:
            continue
        age = max(0, (now - as_utc(first.created_at)).total_seconds() / 86400)
        discount = 2 ** (-age / 30)
        baseline = (question.policy_snapshot or {}).get("baseline", {})
        if set(baseline.get("memory_ids", [])) - {m.memory_item_id for m in memories}:
            continue  # Source deletion also retracts rewards based on that baseline.
        domain = [t for t in traits if t.domain == question.target_domain and t.status != "superseded"]
        answer_ids = {m.memory_item_id for m in live}
        linked = [t for t in domain if answer_ids.intersection(t.memory_item_ids)]
        previous_ids = set(baseline.get("memory_ids", []))
        novelty = any(statement_hash(m.content) not in baseline.get("statement_hashes", []) for m in live)
        independent = bool(answer_ids - previous_ids)
        resolved = baseline.get("unresolved", 0) > sum(t.status == "unresolved" for t in domain)
        reward = min(1.0, .2 * bool(linked) + .35 * novelty * independent + .45 * resolved)
        # Missing-domain acquisition is a directly observable model change.
        if not baseline.get("statement_hashes") and linked:
            reward = 1.0
        key = (question.target_domain, question.reason)
        stat = learned.setdefault(key, {"success": 3.0, "failure": 1.0, "trials": 0.0, "minutes": 1.5})
        stat["success"] += discount * reward
        stat["failure"] += discount * (1 - reward)
        stat["trials"] += discount
        duration = sum(max(0, e.duration_ms or 0) for e in answers) / 60000
        if duration:
            weight = .25 * discount
            stat["minutes"] = (1 - weight) * stat["minutes"] + weight * min(10, max(.25, duration))
    return learned


def evaluate(domain, reason, refs, traits, learned, load, now, last_answer=None):
    relevant = [t for t in traits if t.domain == domain and t.status != "superseded"
                and (not refs or set(refs).intersection(t.evidence_ids + t.counter_evidence_ids))]
    conflict = any(t.status == "unresolved" for t in relevant)
    prior = .5 if not relevant or conflict else max(.5, min(.95, min(t.confidence for t in relevant)))
    stat = learned.get((domain, reason), {"success": 3.0, "failure": 1.0, "trials": 0.0, "minutes": 1.5})
    reliability = stat["success"] / (stat["success"] + stat["failure"])
    gain = information_gain(prior, reliability)
    uncertainty = entropy(prior)
    age = max(0, (now - as_utc(last_answer)).total_seconds() / 86400) if last_answer else 30
    urgency = 1 + min(1, age / 30) * .2
    exploration = .06 / math.sqrt(1 + stat["trials"])
    cost = max(.25, stat["minutes"]) * (1 + load["fatigue"] * 2)
    score = (gain + exploration) * IMPORTANCE[reason] * uncertainty * urgency / cost
    return {"version": VERSION, "score": round(score, 7), "information_gain_bits": round(gain, 6),
            "uncertainty_bits": round(uncertainty, 6), "importance": IMPORTANCE[reason],
            "urgency": urgency, "expected_minutes": stat["minutes"], "interaction_cost": cost,
            "reliability": round(reliability, 6), "discounted_trials": stat["trials"], "exploration": exploration,
            "burden": load, "baseline": {"statement_hashes": [statement_hash(t.statement) for t in relevant],
                "memory_ids": sorted({m for t in relevant for m in t.memory_item_ids}),
                "unresolved": sum(t.status == "unresolved" for t in relevant)}}
