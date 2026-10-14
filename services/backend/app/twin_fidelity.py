"""Empirical, human-assessed Twin agreement; never personality completeness.

This module has no database, provider or model calls. Its caller must persist an
immutable holdout reservation, answer locks, exposure manifests and the owner's
explicit assessments. An LLM calibration diff is useful feedback, but cannot be
turned into a score by this module.

The statistical unit is a connected question/source group, not a chat turn.
Any shared paraphrase group or held-out source joins units transitively. A unit
only counts as a match when *all* observed assessments in it match. Wilson
intervals are approximate binomial intervals: they assume the remaining units
are representative and sufficiently independent. Bonferroni adjustment makes
the five reported dimension intervals conservative as a family. These checks
prevent obvious leakage and inflated counts; they do not prove that a benchmark
represents an entire person.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime
from hashlib import sha256
import hmac
from math import isfinite, sqrt
from statistics import NormalDist
from typing import Iterable


DIMENSIONS = ("DECISION", "REASONING", "VALUE_PRIORITY", "EMOTIONAL_REACTION", "EXPRESSION")
DIMENSION_LABELS = {
    "DECISION": "选择", "REASONING": "理由", "VALUE_PRIORITY": "价值优先级",
    "EMOTIONAL_REACTION": "情绪反应", "EXPRESSION": "表达",
}
ALIGNMENTS = {"MATCH", "PARTIAL", "DIFFERENT", "NOT_OBSERVED"}
PREFERENCES = {"CANDIDATE", "BASELINE", "TIE", "NOT_OBSERVED"}
METHOD_VERSION = "heldout-human-group-agreement-v1"


def text_hash(text: str) -> str:
    """Hash the exact stored UTF-8 text; do not normalize away changed wording."""
    return sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExposureManifest:
    """Complete server audit of everything the prediction could have seen.

    Source groups refer to the held-out human answer's provenance, not ordinary
    historical evidence from which the Twin is meant to make its prediction.
    Text hashes include prior prompts, retrieved messages and tool results,
    excluding the current prediction question itself. The
    verified flag must be backed by captured server context, not a client claim.
    """

    verified: bool = False
    source_group_ids: tuple[str, ...] = ()
    question_group_ids: tuple[str, ...] = ()
    text_hashes: tuple[str, ...] = ()


@dataclass(frozen=True)
class HumanRating:
    dimension: str
    alignment: str
    rater_actor_id: str
    assessment_method: str = "HUMAN_BLIND"


@dataclass(frozen=True)
class CalibrationObservation:
    observation_id: str
    benchmark_id: str
    subject_id: str
    actor_id: str
    question_group_id: str
    holdout_source_group_ids: tuple[str, ...]
    question: str
    locked_answer: str
    human_answer: str
    model_version: str
    person_model_version: str
    source_basis: str
    benchmark_frozen_at: datetime
    locked_at: datetime
    human_answered_at: datetime
    rated_at: datetime
    ratings: tuple[HumanRating, ...] = ()
    held_out: bool = False
    human_answer_confirmed: bool = False
    human_answer_source_type: str = "SUBJECT"
    locked_response_type: str = "SIMULATION"
    exposure: ExposureManifest = field(default_factory=ExposureManifest)


@dataclass(frozen=True)
class EvaluationContext:
    subject_id: str
    actor_id: str
    benchmark_id: str
    model_version: str
    person_model_version: str
    source_basis: str
    training_manifest_verified: bool = False
    training_source_group_ids: tuple[str, ...] = ()
    training_question_group_ids: tuple[str, ...] = ()
    training_text_hashes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FidelityPolicy:
    # Operational minimums, not claims that 20 samples reconstruct a person.
    min_independent_groups: int = 20
    max_interval_width: float = 0.35
    confidence_level: float = 0.95

    def __post_init__(self) -> None:
        if self.min_independent_groups < 20:
            raise ValueError("At least 20 independent groups are required.")
        if not 0 < self.max_interval_width <= 0.5:
            raise ValueError("Invalid maximum confidence interval width.")
        if not 0.90 <= self.confidence_level < 1:
            raise ValueError("Confidence level must be at least 0.90 and below 1.")


@dataclass(frozen=True)
class ModelDiagnostic:
    dimension: str
    alignment: str


def wilson_interval(matches: int, total: int, confidence_level: float = 0.95) -> tuple[float, float]:
    """Two-sided Wilson score interval for an integer binomial match count.

    Formula: https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm
    """
    if isinstance(matches, bool) or isinstance(total, bool) or not isinstance(matches, int) or not isinstance(total, int):
        raise ValueError("Match and total counts must be integers.")
    if total < 1 or not 0 <= matches <= total or not 0 < confidence_level < 1:
        raise ValueError("Invalid binomial counts or confidence level.")
    z = NormalDist().inv_cdf((1 + confidence_level) / 2)
    z2, proportion = z * z, matches / total
    denominator = 1 + z2 / total
    center = (proportion + z2 / (2 * total)) / denominator
    half = z * sqrt(proportion * (1 - proportion) / total + z2 / (4 * total * total)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _scope(context: EvaluationContext) -> dict:
    return {name: getattr(context, name) for name in
            ("subject_id", "actor_id", "benchmark_id", "model_version", "person_model_version", "source_basis")}


def _case_manifest(case: CalibrationObservation, locked_answer: str | None = None) -> dict:
    return {"observation_id": case.observation_id,
            "question_hash": text_hash(case.question),
            "locked_answer_hash": text_hash(case.locked_answer if locked_answer is None else locked_answer),
            "human_answer_hash": text_hash(case.human_answer),
            "question_group_id": case.question_group_id,
            "holdout_source_group_ids": sorted(set(case.holdout_source_group_ids))}


def _manifest_map(report: dict) -> dict[str, dict] | None:
    entries = report.get("accepted_observation_manifest")
    if (not isinstance(entries, list) or any(not isinstance(entry, dict)
                                            or not isinstance(entry.get("observation_id"), str) for entry in entries)):
        return None
    identifiers = [entry["observation_id"] for entry in entries]
    if len(identifiers) != len(set(identifiers)):
        return None
    return {entry["observation_id"]: entry for entry in entries}


def _exposure_reasons(case: CalibrationObservation, exposure: ExposureManifest,
                      context: EvaluationContext) -> list[str]:
    reasons = []
    if not context.training_manifest_verified or not exposure.verified:
        reasons.append("EXPOSURE_UNVERIFIED")
    sources = set(case.holdout_source_group_ids)
    if sources & (set(context.training_source_group_ids) | set(exposure.source_group_ids)):
        reasons.append("HOLDOUT_SOURCE_EXPOSED")
    if case.question_group_id in set(context.training_question_group_ids) | set(exposure.question_group_ids):
        reasons.append("QUESTION_GROUP_EXPOSED")
    hashes = set(context.training_text_hashes) | set(exposure.text_hashes)
    if text_hash(case.question) in hashes:
        reasons.append("QUESTION_EXPOSED")
    if text_hash(case.human_answer) in hashes:
        reasons.append("HUMAN_ANSWER_EXPOSED")
    return reasons


def _case_reasons(case: CalibrationObservation, context: EvaluationContext,
                  *, require_ratings: bool = True) -> list[str]:
    reasons = []
    for name in ("subject_id", "actor_id", "benchmark_id", "model_version", "person_model_version", "source_basis"):
        if not getattr(context, name) or getattr(case, name) != getattr(context, name):
            reasons.append(name.upper() + "_MISMATCH")
    if (not case.observation_id or not case.question_group_id or not case.holdout_source_group_ids
            or any(not value for value in case.holdout_source_group_ids)
            or not case.question.strip() or not case.locked_answer.strip() or not case.human_answer.strip()):
        reasons.append("PROVENANCE_INCOMPLETE")
    if not case.held_out:
        reasons.append("NOT_FROZEN_HOLDOUT")
    if not case.human_answer_confirmed or case.human_answer_source_type != "SUBJECT":
        reasons.append("SUBJECT_ANSWER_UNCONFIRMED")
    if case.locked_response_type != "SIMULATION":
        # Quoting a stored original is retrieval quality, not unseen prediction.
        reasons.append("NOT_A_PREDICTION")
    stamps = (case.benchmark_frozen_at, case.locked_at, case.human_answered_at, case.rated_at)
    if not all(_aware(value) for value in stamps):
        reasons.append("TIMESTAMP_UNVERIFIED")
    elif not case.benchmark_frozen_at <= case.locked_at < case.human_answered_at <= case.rated_at:
        reasons.append("ANSWER_NOT_LOCKED_BEFORE_HUMAN")
    reasons.extend(_exposure_reasons(case, case.exposure, context))
    if require_ratings:
        dimensions = [rating.dimension for rating in case.ratings]
        if not dimensions:
            reasons.append("HUMAN_RATINGS_REQUIRED")
        if len(dimensions) != len(set(dimensions)):
            reasons.append("DUPLICATE_DIMENSION_RATING")
        if any(r.dimension not in DIMENSIONS or r.alignment not in ALIGNMENTS for r in case.ratings):
            reasons.append("INVALID_HUMAN_RATING")
        if any(r.assessment_method != "HUMAN_BLIND" or r.rater_actor_id != context.actor_id for r in case.ratings):
            reasons.append("OWNER_BLIND_RATING_REQUIRED")
    return sorted(set(reasons))


def _clusters(cases: Iterable[CalibrationObservation]) -> list[list[CalibrationObservation]]:
    """Connected components prevent repeated/paraphrased questions inflating n."""
    rows = list(cases)
    parents = list(range(len(rows)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    seen = {}
    for index, case in enumerate(rows):
        keys = [("question", case.question_group_id)] + [("source", identifier) for identifier in case.holdout_source_group_ids]
        for key in keys:
            if key in seen:
                parents[root(index)] = root(seen[key])
            else:
                seen[key] = index
    groups = {}
    for index, case in enumerate(rows):
        groups.setdefault(root(index), []).append(case)
    return list(groups.values())


def _interval_view(lower: float, upper: float, confidence: float) -> dict:
    return {"lower": lower, "upper": upper, "confidence_level": confidence, "method": "WILSON"}


def summarize_fidelity(observations: Iterable[CalibrationObservation], context: EvaluationContext,
                       policy: FidelityPolicy | None = None, *,
                       model_diagnostics: Iterable[ModelDiagnostic] = (),
                       diagnostic_calibration_count: int = 0) -> dict:
    """Return a JSON-ready report without any raw question or personal answer.

    ``agreement_rate`` is null whenever evidence is insufficient. MATCH is the
    only success; PARTIAL is not quietly awarded half a point. NOT_OBSERVED is
    excluded for that dimension. No recording-count or model self-rating enters
    the numerator. Diagnostics are returned separately with no score.
    """
    policy = policy or FidelityPolicy()
    rows = list(observations)
    counts = Counter(case.observation_id for case in rows)
    accepted, excluded = [], []
    for case in rows:
        reasons = _case_reasons(case, context)
        if counts[case.observation_id] > 1:
            reasons.append("DUPLICATE_OBSERVATION")
        if reasons:
            excluded.append({"observation_id": case.observation_id, "reasons": sorted(set(reasons))})
        else:
            accepted.append(case)
    groups = _clusters(accepted)
    # Family-wise adjustment for the five dimensions. The overall interval is
    # the mean of these simultaneous bounds, not a falsely pooled binomial CI.
    adjusted_confidence = 1 - (1 - policy.confidence_level) / len(DIMENSIONS)
    dimensions, estimates, bounds = [], [], []
    for dimension in DIMENSIONS:
        alignment_counts: Counter = Counter()
        matched_groups, observed_groups, observed_count = 0, 0, 0
        for group in groups:
            alignments = [rating.alignment for case in group for rating in case.ratings
                          if rating.dimension == dimension]
            alignment_counts.update(alignments)
            observed = [value for value in alignments if value != "NOT_OBSERVED"]
            observed_count += len(observed)
            if observed:
                observed_groups += 1
                matched_groups += int(all(value == "MATCH" for value in observed))
        gaps = []
        if observed_groups < policy.min_independent_groups:
            gaps.append("MORE_INDEPENDENT_HOLDOUT_GROUPS_REQUIRED")
        interval = wilson_interval(matched_groups, observed_groups, adjusted_confidence) if observed_groups else None
        if interval and interval[1] - interval[0] > policy.max_interval_width:
            gaps.append("UNCERTAINTY_TOO_WIDE")
        available = not gaps
        rate = matched_groups / observed_groups if available else None
        dimensions.append({
            "dimension": dimension, "label": DIMENSION_LABELS[dimension],
            "status": "available" if available else "insufficient_data",
            "observed_count": observed_count, "independent_group_count": observed_groups,
            "matching_group_count": matched_groups,
            "not_observed_count": alignment_counts["NOT_OBSERVED"],
            "agreement_rate": rate,
            "confidence_interval": _interval_view(*interval, adjusted_confidence) if available else None,
            "gaps": gaps,
        })
        if available:
            estimates.append(rate)
            bounds.append(interval)
    available = len(estimates) == len(DIMENSIONS)
    diagnostic_counts = Counter((item.dimension, item.alignment) for item in model_diagnostics
                                if item.dimension in DIMENSIONS and item.alignment in ALIGNMENTS)
    return {
        "method_version": METHOD_VERSION, "scope": _scope(context),
        "label": "未见问题上的本人一致率", "status": "available" if available else "insufficient_data",
        "assessment_method": "OWNER_HUMAN_BLIND", "statistical_unit": "CONNECTED_QUESTION_SOURCE_GROUP",
        "accepted_observation_count": len(accepted), "independent_group_count": len(groups),
        "accepted_observation_manifest": [_case_manifest(case) for case in accepted],
        "excluded_observation_count": len(excluded), "excluded_observations": excluded,
        "dimensions": dimensions,
        "overall": {
            "agreement_rate": sum(estimates) / len(DIMENSIONS) if available else None,
            "confidence_interval": {
                "lower": sum(lower for lower, _ in bounds) / len(DIMENSIONS),
                "upper": sum(upper for _, upper in bounds) / len(DIMENSIONS),
                "confidence_level": policy.confidence_level,
                "method": "MEAN_OF_BONFERRONI_WILSON_BOUNDS",
            } if available else None,
            "aggregation": "EQUAL_WEIGHT_FIVE_DIMENSIONS",
            "gaps": [item["dimension"] for item in dimensions if item["status"] != "available"],
        },
        "requirements": {
            "min_independent_groups_per_dimension": policy.min_independent_groups,
            "max_interval_width": policy.max_interval_width,
            "confidence_level": policy.confidence_level,
            "dimension_confidence_level": adjusted_confidence,
            "representative_independent_groups_required": True,
        },
        "model_diagnostics": {
            "diagnostic_calibration_count": max(0, diagnostic_calibration_count),
            "assessment_count": sum(diagnostic_counts.values()), "agreement_rate": None,
            "purpose": "FEEDBACK_ONLY_NOT_HUMAN_FIDELITY",
            "dimensions": [{"dimension": dimension,
                            "counts": {alignment: diagnostic_counts[(dimension, alignment)]
                                       for alignment in sorted(ALIGNMENTS)}} for dimension in DIMENSIONS],
        },
        "interpretation": "衡量本次未见问题上的本人评估一致性；不代表人格复制完成度，也不包含音色相似度。",
    }


def export_prediction_case(case: CalibrationObservation) -> dict:
    """Separate the safe prediction request from the private holdout manifest.

    Only ``prediction_input`` belongs in the model request. The human answer,
    ratings and locked prediction are intentionally absent from that request.
    """
    return {"prediction_input": {"question": case.question}, "audit_manifest": {
        "observation_id": case.observation_id, "benchmark_id": case.benchmark_id,
        "question_group_id": case.question_group_id, "question_hash": text_hash(case.question),
        "human_answer_hash": text_hash(case.human_answer),
        "holdout_source_group_ids": list(case.holdout_source_group_ids),
        "benchmark_frozen_at": case.benchmark_frozen_at.isoformat(),
    }}


def export_blind_pair(case: CalibrationObservation, comparison_answer: str,
                      comparison_model_version: str, *, assignment_seed: bytes,
                      comparison_locked_at: datetime) -> dict:
    """Human-review shape and a separate private model-label binding.

    The human reference is for the owner's review *after* both predictions have
    been locked. Neither this shape nor its private manifest is a model prompt.
    Keep the secret assignment seed and private mapping off the review client.
    """
    if len(assignment_seed) < 16 or not comparison_answer.strip() or not comparison_model_version:
        raise ValueError("A private assignment seed and two non-empty predictions are required.")
    if comparison_model_version == case.model_version:
        raise ValueError("Pairwise evaluation requires distinct model versions.")
    if (not all(_aware(value) for value in (case.benchmark_frozen_at, case.locked_at,
                                           comparison_locked_at, case.human_answered_at))
            or not case.benchmark_frozen_at <= case.locked_at < case.human_answered_at
            or not case.benchmark_frozen_at <= comparison_locked_at < case.human_answered_at):
        raise ValueError("Both predictions must be locked before the human answer.")
    digest = hmac.new(assignment_seed, (case.benchmark_id + "\0" + case.observation_id).encode(), "sha256").digest()
    swap = bool(digest[0] & 1)
    predictions = [("CANDIDATE", case.model_version, case.locked_answer),
                   ("BASELINE", comparison_model_version, comparison_answer)]
    if swap:
        predictions.reverse()
    return {
        "human_review": {"observation_id": case.observation_id, "question": case.question,
                         "human_reference": case.human_answer,
                         "answers": [{"label": label, "text": entry[2]}
                                     for label, entry in zip(("A", "B"), predictions)],
                         "dimensions": list(DIMENSIONS),
                         "choices": ["A", "B", "TIE", "NOT_OBSERVED"]},
        "private_manifest": {"benchmark_id": case.benchmark_id, "observation_id": case.observation_id,
                             "labels": {label: {"role": entry[0], "model_version": entry[1],
                                                "answer_hash": text_hash(entry[2])}
                                        for label, entry in zip(("A", "B"), predictions)},
                             "human_answer_hash": text_hash(case.human_answer)},
    }


@dataclass(frozen=True)
class HumanPreference:
    dimension: str
    preference: str
    rater_actor_id: str
    assessment_method: str = "HUMAN_BLIND"


@dataclass(frozen=True)
class BlindPairwiseObservation:
    candidate_case: CalibrationObservation
    baseline_model_version: str
    baseline_locked_answer: str
    baseline_locked_at: datetime
    baseline_exposure: ExposureManifest
    preferences: tuple[HumanPreference, ...]


@dataclass(frozen=True)
class PromotionChecks:
    # None of these operational guarantees can be inferred from an accuracy CI.
    training_consent_active: bool = False
    source_and_subject_current: bool = False
    candidate_artifact_available: bool = False
    rollback_available: bool = False
    safety_checks_passed: bool = False
    benchmark_never_used_for_training: bool = False


@dataclass(frozen=True)
class PromotionPolicy:
    min_independent_groups: int = 20
    min_candidate_agreement_lower_bound: float = 0.60
    max_regression_upper_bound: float = 0.20
    min_improvement_lower_bound: float = 0.50
    confidence_level: float = 0.95

    def __post_init__(self) -> None:
        if self.min_independent_groups < 20 or not 0.90 <= self.confidence_level < 1:
            raise ValueError("Promotion requires at least 20 groups and 90% confidence.")
        if not all(0 <= value <= 1 for value in (self.min_candidate_agreement_lower_bound,
                                                self.max_regression_upper_bound,
                                                self.min_improvement_lower_bound)):
            raise ValueError("Invalid promotion threshold.")


def gate_candidate_promotion(candidate_report: dict, baseline_report: dict,
                             pairwise: Iterable[BlindPairwiseObservation], context: EvaluationContext,
                             baseline_model_version: str, checks: PromotionChecks,
                             policy: PromotionPolicy | None = None) -> dict:
    """Conservative automatic-promotion decision from paired human holdout tests.

    A candidate must have sufficient absolute agreement, no detectable material
    regression in any dimension, and a clear improvement in at least one. Ties
    never count as wins. Report availability, version/subject scope, leakage,
    consent, source validity, rollback and separate safety checks all fail closed.
    Training/test loss and the LLM's own grades are deliberately not inputs.
    """
    policy = policy or PromotionPolicy()
    reasons = []
    baseline_context = replace(context, model_version=baseline_model_version)
    safe_dimensions = {}
    if not baseline_model_version or baseline_model_version == context.model_version:
        reasons.append("DISTINCT_BASELINE_REQUIRED")
    for name, report, expected in (("CANDIDATE", candidate_report, context),
                                    ("BASELINE", baseline_report, baseline_context)):
        if report.get("method_version") != METHOD_VERSION or report.get("scope") != _scope(expected):
            reasons.append(name + "_REPORT_SCOPE_INVALID")
        if report.get("status") != "available":
            reasons.append(name + "_HUMAN_EVIDENCE_INSUFFICIENT")
        dimensions = report.get("dimensions", [])
        if (not isinstance(dimensions, list) or len(dimensions) != len(DIMENSIONS)
                or {item.get("dimension") for item in dimensions if isinstance(item, dict)} != set(DIMENSIONS)):
            reasons.append(name + "_REPORT_DIMENSIONS_INVALID")
            safe_dimensions[name] = {}
        else:
            safe_dimensions[name] = {item["dimension"]: item for item in dimensions}
        requirements = report.get("requirements") or {}
        confidence = requirements.get("confidence_level")
        if (not isinstance(confidence, (int, float)) or not isfinite(confidence)
                or confidence < policy.confidence_level or confidence >= 1):
            reasons.append(name + "_REPORT_CONFIDENCE_INSUFFICIENT")
    candidate_dimensions = safe_dimensions["CANDIDATE"]
    for dimension in DIMENSIONS:
        lower = (candidate_dimensions.get(dimension, {}).get("confidence_interval") or {}).get("lower")
        if (not isinstance(lower, (int, float)) or not isfinite(lower)
                or not 0 <= lower <= 1 or lower < policy.min_candidate_agreement_lower_bound):
            reasons.append("CANDIDATE_AGREEMENT_FLOOR:" + dimension)
    for name, passed in vars(checks).items():
        if passed is not True:
            reasons.append(name.upper() + "_REQUIRED")
    rows = list(pairwise)
    duplicates = Counter(row.candidate_case.observation_id for row in rows)
    candidate_manifests = _manifest_map(candidate_report)
    baseline_manifests = _manifest_map(baseline_report)
    if candidate_manifests is None:
        reasons.append("CANDIDATE_REPORT_MANIFEST_INVALID")
        candidate_manifests = {}
    if baseline_manifests is None:
        reasons.append("BASELINE_REPORT_MANIFEST_INVALID")
        baseline_manifests = {}
    accepted, excluded = [], []
    for row in rows:
        case = row.candidate_case
        invalid = _case_reasons(case, context, require_ratings=False)
        if duplicates[case.observation_id] > 1:
            invalid.append("DUPLICATE_OBSERVATION")
        if row.baseline_model_version != baseline_model_version:
            invalid.append("BASELINE_MODEL_MISMATCH")
        if (not all(_aware(value) for value in (row.baseline_locked_at, case.benchmark_frozen_at, case.human_answered_at))
                or not case.benchmark_frozen_at <= row.baseline_locked_at < case.human_answered_at):
            invalid.append("BASELINE_NOT_LOCKED_BEFORE_HUMAN")
        if candidate_manifests.get(case.observation_id) != _case_manifest(case):
            invalid.append("CANDIDATE_REPORT_PREDICTION_UNBOUND")
        if baseline_manifests.get(case.observation_id) != _case_manifest(case, row.baseline_locked_answer):
            invalid.append("BASELINE_REPORT_PREDICTION_UNBOUND")
        invalid.extend(_exposure_reasons(case, row.baseline_exposure, baseline_context))
        dims = [preference.dimension for preference in row.preferences]
        if (len(dims) != len(set(dims)) or any(p.dimension not in DIMENSIONS or p.preference not in PREFERENCES
                                             for p in row.preferences)):
            invalid.append("INVALID_PAIRED_HUMAN_PREFERENCE")
        if any(p.assessment_method != "HUMAN_BLIND" or p.rater_actor_id != context.actor_id for p in row.preferences):
            invalid.append("OWNER_BLIND_PREFERENCE_REQUIRED")
        if invalid:
            excluded.append({"observation_id": case.observation_id, "reasons": sorted(set(invalid))})
        else:
            accepted.append(row)
    choices = {row.candidate_case.observation_id: row.preferences for row in accepted}
    groups = _clusters(row.candidate_case for row in accepted)
    # Two families of five bounds are consulted: wins and regressions.
    confidence = 1 - (1 - policy.confidence_level) / (2 * len(DIMENSIONS))
    dimensions, improved = [], []
    for dimension in DIMENSIONS:
        observed, wins, regressions = 0, 0, 0
        for group in groups:
            preferences = [p.preference for case in group for p in choices[case.observation_id]
                           if p.dimension == dimension and p.preference != "NOT_OBSERVED"]
            if preferences:
                observed += 1
                wins += int(all(value == "CANDIDATE" for value in preferences))
                regressions += int(any(value == "BASELINE" for value in preferences))
        win_interval = wilson_interval(wins, observed, confidence) if observed else None
        regression_interval = wilson_interval(regressions, observed, confidence) if observed else None
        if observed < policy.min_independent_groups:
            reasons.append("PAIRED_GROUPS_INSUFFICIENT:" + dimension)
        if not regression_interval or regression_interval[1] > policy.max_regression_upper_bound:
            reasons.append("REGRESSION_UNCERTAINTY:" + dimension)
        if observed >= policy.min_independent_groups and win_interval and win_interval[0] > policy.min_improvement_lower_bound:
            improved.append(dimension)
        dimensions.append({"dimension": dimension, "independent_group_count": observed,
                           "candidate_win_count": wins, "baseline_win_count": regressions,
                           "candidate_win_interval": _interval_view(*win_interval, confidence) if win_interval else None,
                           "regression_interval": _interval_view(*regression_interval, confidence) if regression_interval else None})
    if not improved:
        reasons.append("NO_CLEAR_HUMAN_ASSESSED_IMPROVEMENT")
    return {"eligible": not reasons, "reasons": sorted(set(reasons)),
            "improved_dimensions": improved, "dimensions": dimensions,
            "excluded_pairs": excluded, "assessment_method": "OWNER_HUMAN_BLIND_PAIRED_HOLDOUT",
            "policy": vars(policy), "training_loss_is_fidelity": False}
