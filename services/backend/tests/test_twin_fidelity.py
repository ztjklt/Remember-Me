"""Human holdout measurement must not turn coverage or model grades into fidelity."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.twin_fidelity import (
    DIMENSIONS, BlindPairwiseObservation, CalibrationObservation, EvaluationContext,
    ExposureManifest, FidelityPolicy, HumanPreference, HumanRating, ModelDiagnostic,
    PromotionChecks, PromotionPolicy, export_blind_pair, export_prediction_case,
    gate_candidate_promotion, summarize_fidelity, text_hash, wilson_interval,
)


START = datetime(2026, 10, 14, 1, tzinfo=timezone.utc)


def context(**overrides):
    return replace(EvaluationContext("subject-1", "owner-1", "benchmark-1", "candidate-v2",
                                     "person-v3", "source-guard-4", training_manifest_verified=True), **overrides)


def observation(index=0, **overrides):
    return replace(CalibrationObservation(
        observation_id=f"case-{index}", benchmark_id="benchmark-1", subject_id="subject-1", actor_id="owner-1",
        question_group_id=f"question-group-{index}", holdout_source_group_ids=(f"holdout-source-{index}",),
        question=f"未见问题 {index}", locked_answer=f"已锁定预测 {index}", human_answer=f"本人真实回答 {index}",
        model_version="candidate-v2", person_model_version="person-v3", source_basis="source-guard-4",
        benchmark_frozen_at=START, locked_at=START + timedelta(minutes=1),
        human_answered_at=START + timedelta(minutes=2), rated_at=START + timedelta(minutes=3),
        ratings=tuple(HumanRating(dimension, "MATCH", "owner-1") for dimension in DIMENSIONS),
        held_out=True, human_answer_confirmed=True, exposure=ExposureManifest(verified=True),
    ), **overrides)


def dimension(report, key):
    return next(item for item in report["dimensions"] if item["dimension"] == key)


def all_checks():
    return PromotionChecks(True, True, True, True, True, True)


def paired_material(count=80):
    cases = [observation(index) for index in range(count)]
    baseline = [replace(case, model_version="baseline-v1", locked_answer=f"旧预测 {index}",
                        ratings=tuple(HumanRating(key, "DIFFERENT" if index % 4 == 0 else "MATCH", "owner-1")
                                      for key in DIMENSIONS)) for index, case in enumerate(cases)]
    pairs = [BlindPairwiseObservation(case, "baseline-v1", old.locked_answer, old.locked_at,
                                     ExposureManifest(verified=True),
                                     tuple(HumanPreference(key, "CANDIDATE", "owner-1") for key in DIMENSIONS))
             for case, old in zip(cases, baseline)]
    candidate_report = summarize_fidelity(cases, context())
    baseline_report = summarize_fidelity(baseline, context(model_version="baseline-v1"))
    return cases, baseline, pairs, candidate_report, baseline_report


def test_wilson_known_values_and_symmetry():
    lower, upper = wilson_interval(5, 10)
    assert lower == pytest.approx(0.2365930905)
    assert upper == pytest.approx(0.7634069095)
    assert wilson_interval(0, 10)[1] == pytest.approx(0.2775327999)
    assert wilson_interval(10, 10)[0] == pytest.approx(0.7224672001)


@pytest.mark.parametrize("matches,total,confidence", [(1, 0, .95), (-1, 10, .95), (11, 10, .95),
                                                     (1.5, 10, .95), (True, 10, .95), (1, 10, 1)])
def test_wilson_rejects_invalid_statistics(matches, total, confidence):
    with pytest.raises(ValueError):
        wilson_interval(matches, total, confidence)


def test_empty_or_unrated_diagnostics_show_no_score():
    report = summarize_fidelity([], context(), diagnostic_calibration_count=45,
                                model_diagnostics=[ModelDiagnostic(key, "MATCH") for key in DIMENSIONS] * 40)
    assert report["status"] == "insufficient_data"
    assert report["overall"]["agreement_rate"] is None
    assert report["overall"]["confidence_interval"] is None
    assert all(item["agreement_rate"] is None for item in report["dimensions"])
    assert report["model_diagnostics"]["diagnostic_calibration_count"] == 45
    assert report["model_diagnostics"]["assessment_count"] == 200
    assert report["model_diagnostics"]["agreement_rate"] is None
    assert "HUMAN_RATINGS_REQUIRED" in summarize_fidelity([observation(ratings=())], context())["excluded_observations"][0]["reasons"]


@pytest.mark.parametrize("override,reason", [
    ({"subject_id": "different"}, "SUBJECT_ID_MISMATCH"),
    ({"actor_id": "contributor"}, "ACTOR_ID_MISMATCH"),
    ({"benchmark_id": "other"}, "BENCHMARK_ID_MISMATCH"),
    ({"model_version": "old"}, "MODEL_VERSION_MISMATCH"),
    ({"person_model_version": "old"}, "PERSON_MODEL_VERSION_MISMATCH"),
    ({"source_basis": "deleted-source"}, "SOURCE_BASIS_MISMATCH"),
    ({"held_out": False}, "NOT_FROZEN_HOLDOUT"),
    ({"human_answer_confirmed": False}, "SUBJECT_ANSWER_UNCONFIRMED"),
    ({"human_answer_source_type": "THIRD_PARTY"}, "SUBJECT_ANSWER_UNCONFIRMED"),
    ({"locked_response_type": "ORIGINAL"}, "NOT_A_PREDICTION"),
    ({"locked_response_type": "CONVERSATION"}, "NOT_A_PREDICTION"),
    ({"holdout_source_group_ids": ()}, "PROVENANCE_INCOMPLETE"),
    ({"exposure": ExposureManifest()}, "EXPOSURE_UNVERIFIED"),
    ({"locked_at": START.replace(tzinfo=None)}, "TIMESTAMP_UNVERIFIED"),
    ({"human_answered_at": START}, "ANSWER_NOT_LOCKED_BEFORE_HUMAN"),
    ({"benchmark_frozen_at": START + timedelta(minutes=4)}, "ANSWER_NOT_LOCKED_BEFORE_HUMAN"),
    ({"rated_at": START}, "ANSWER_NOT_LOCKED_BEFORE_HUMAN"),
])
def test_unverified_foreign_stale_or_leaked_results_are_excluded(override, reason):
    report = summarize_fidelity([observation(**override)], context())
    assert report["accepted_observation_count"] == 0
    assert reason in report["excluded_observations"][0]["reasons"]
    assert report["overall"]["agreement_rate"] is None


@pytest.mark.parametrize("manifest,reason", [
    (ExposureManifest(True, source_group_ids=("holdout-source-0",)), "HOLDOUT_SOURCE_EXPOSED"),
    (ExposureManifest(True, question_group_ids=("question-group-0",)), "QUESTION_GROUP_EXPOSED"),
    (ExposureManifest(True, text_hashes=(text_hash("未见问题 0"),)), "QUESTION_EXPOSED"),
    (ExposureManifest(True, text_hashes=(text_hash("本人真实回答 0"),)), "HUMAN_ANSWER_EXPOSED"),
])
def test_retrieval_and_history_exposure_also_disqualify_holdout(manifest, reason):
    report = summarize_fidelity([observation(exposure=manifest)], context())
    assert reason in report["excluded_observations"][0]["reasons"]


@pytest.mark.parametrize("ctx,reason", [
    (context(training_manifest_verified=False), "EXPOSURE_UNVERIFIED"),
    (context(training_source_group_ids=("holdout-source-0",)), "HOLDOUT_SOURCE_EXPOSED"),
    (context(training_question_group_ids=("question-group-0",)), "QUESTION_GROUP_EXPOSED"),
    (context(training_text_hashes=(text_hash("本人真实回答 0"),)), "HUMAN_ANSWER_EXPOSED"),
])
def test_fine_tuning_training_manifest_cannot_overlap_evaluation(ctx, reason):
    report = summarize_fidelity([observation()], ctx)
    assert reason in report["excluded_observations"][0]["reasons"]


@pytest.mark.parametrize("rating,reason", [
    (HumanRating("EXPRESSION", "MATCH", "owner-1", "MODEL_DIAGNOSTIC"), "OWNER_BLIND_RATING_REQUIRED"),
    (HumanRating("EXPRESSION", "MATCH", "owner-1", "HUMAN_OPEN"), "OWNER_BLIND_RATING_REQUIRED"),
    (HumanRating("EXPRESSION", "MATCH", "another-person"), "OWNER_BLIND_RATING_REQUIRED"),
    (HumanRating("EXPRESSION", "HAPPY", "owner-1"), "INVALID_HUMAN_RATING"),
])
def test_only_explicit_owner_blind_assessment_enters_score(rating, reason):
    report = summarize_fidelity([observation(ratings=(rating,))], context())
    assert reason in report["excluded_observations"][0]["reasons"]


def test_duplicate_ratings_and_duplicate_rows_do_not_inflate_counts():
    case = observation()
    report = summarize_fidelity([case, case], context())
    assert report["accepted_observation_count"] == 0
    assert all("DUPLICATE_OBSERVATION" in item["reasons"] for item in report["excluded_observations"])
    report = summarize_fidelity([replace(case, ratings=case.ratings + (case.ratings[0],))], context())
    assert "DUPLICATE_DIMENSION_RATING" in report["excluded_observations"][0]["reasons"]


def test_sufficient_distinct_holdouts_report_empirical_rate_and_simultaneous_bounds():
    report = summarize_fidelity([observation(index) for index in range(80)], context())
    assert report["status"] == "available"
    assert report["overall"]["agreement_rate"] == 1
    interval = report["overall"]["confidence_interval"]
    assert interval["confidence_level"] == .95
    assert interval["lower"] > .92
    assert interval["upper"] == pytest.approx(1)
    assert all(item["confidence_interval"]["confidence_level"] == pytest.approx(.99) for item in report["dimensions"])
    assert "人格复制完成度" in report["interpretation"]
    # A report carries binding hashes without copying sensitive answers.
    serialized = json.dumps(report, ensure_ascii=False)
    assert "本人真实回答" not in serialized
    assert "已锁定预测" not in serialized
    assert len(report["accepted_observation_manifest"]) == 80


def test_partial_matches_are_failures_and_not_observed_does_not_become_a_match():
    cases = [observation(index) for index in range(80)]
    partial = HumanRating("DECISION", "PARTIAL", "owner-1")
    cases[0] = replace(cases[0], ratings=(partial,) + cases[0].ratings[1:])
    report = summarize_fidelity(cases, context())
    assert dimension(report, "DECISION")["agreement_rate"] == 79 / 80
    cases = [replace(case, ratings=tuple(replace(rating, alignment="NOT_OBSERVED") if rating.dimension == "EMOTIONAL_REACTION"
                                        else rating for rating in case.ratings)) for case in cases]
    report = summarize_fidelity(cases, context())
    assert dimension(report, "DECISION")["status"] == "available"
    assert dimension(report, "EMOTIONAL_REACTION")["observed_count"] == 0
    assert dimension(report, "EMOTIONAL_REACTION")["not_observed_count"] == 80
    assert report["overall"]["agreement_rate"] is None
    assert report["overall"]["gaps"] == ["EMOTIONAL_REACTION"]


def test_twenty_mixed_groups_still_withhold_score_when_interval_is_wide():
    cases = [observation(index, ratings=tuple(HumanRating(key, "MATCH" if index % 2 else "DIFFERENT", "owner-1")
                                            for key in DIMENSIONS)) for index in range(20)]
    report = summarize_fidelity(cases, context())
    assert dimension(report, "DECISION")["independent_group_count"] == 20
    assert dimension(report, "DECISION")["agreement_rate"] is None
    assert dimension(report, "DECISION")["gaps"] == ["UNCERTAINTY_TOO_WIDE"]


def test_paraphrases_and_shared_sources_merge_transitively_into_one_unit():
    cases = [observation(index, question_group_id="one-question") for index in range(80)]
    report = summarize_fidelity(cases, context())
    assert dimension(report, "DECISION")["observed_count"] == 80
    assert dimension(report, "DECISION")["independent_group_count"] == 1
    assert dimension(report, "DECISION")["agreement_rate"] is None
    # q1/source-a -> q2/source-a+source-b -> q3/source-b is one component.
    cases = [observation(0, holdout_source_group_ids=("a",)),
             observation(1, holdout_source_group_ids=("a", "b")),
             observation(2, holdout_source_group_ids=("b",))]
    assert summarize_fidelity(cases, context())["independent_group_count"] == 1


def test_mixed_result_within_a_group_is_conservative_failure():
    cases = [observation(index) for index in range(80)]
    duplicate_group = observation(81, question_group_id=cases[0].question_group_id,
                                  ratings=tuple(HumanRating(key, "DIFFERENT", "owner-1") for key in DIMENSIONS))
    report = summarize_fidelity(cases + [duplicate_group], context())
    decision = dimension(report, "DECISION")
    assert decision["observed_count"] == 81
    assert decision["independent_group_count"] == 80
    assert decision["matching_group_count"] == 79
    assert decision["agreement_rate"] == 79 / 80


@pytest.mark.parametrize("kwargs", [{"min_independent_groups": 1}, {"max_interval_width": 1}, {"confidence_level": .80}])
def test_policy_cannot_quietly_make_tiny_samples_reliable(kwargs):
    with pytest.raises(ValueError):
        FidelityPolicy(**kwargs)


def test_prediction_export_cannot_expose_human_reference_to_model():
    case = observation()
    exported = export_prediction_case(case)
    assert exported["prediction_input"] == {"question": case.question}
    assert case.human_answer not in json.dumps(exported, ensure_ascii=False)
    assert case.locked_answer not in json.dumps(exported, ensure_ascii=False)
    assert exported["audit_manifest"]["human_answer_hash"] == text_hash(case.human_answer)


def test_blind_pair_export_is_stable_and_keeps_models_in_private_mapping():
    case = observation()
    kwargs = {"assignment_seed": b"private-32-byte-assignment-secret", "comparison_locked_at": case.locked_at}
    first = export_blind_pair(case, "旧版本的预测", "baseline-v1", **kwargs)
    assert first == export_blind_pair(case, "旧版本的预测", "baseline-v1", **kwargs)
    review = first["human_review"]
    assert {answer["label"] for answer in review["answers"]} == {"A", "B"}
    assert review["human_reference"] == case.human_answer
    assert "candidate-v2" not in json.dumps(review)
    assert "baseline-v1" not in json.dumps(review)
    assert {item["role"] for item in first["private_manifest"]["labels"].values()} == {"BASELINE", "CANDIDATE"}
    with pytest.raises(ValueError):
        export_blind_pair(case, "旧预测", "baseline-v1", assignment_seed=b"x", comparison_locked_at=case.locked_at)
    with pytest.raises(ValueError):
        export_blind_pair(case, "旧预测", "baseline-v1", assignment_seed=kwargs["assignment_seed"],
                          comparison_locked_at=case.human_answered_at)


def test_strong_bound_paired_human_improvement_can_pass_auto_promotion():
    _, _, pairs, candidate, baseline = paired_material()
    gate = gate_candidate_promotion(candidate, baseline, pairs, context(), "baseline-v1", all_checks())
    assert candidate["status"] == baseline["status"] == "available"
    assert gate["eligible"] is True
    assert gate["reasons"] == []
    assert gate["improved_dimensions"] == list(DIMENSIONS)
    assert gate["training_loss_is_fidelity"] is False


@pytest.mark.parametrize("check_name", ["training_consent_active", "source_and_subject_current", "candidate_artifact_available",
                                       "rollback_available", "safety_checks_passed", "benchmark_never_used_for_training"])
def test_auto_promotion_fails_closed_without_operational_guarantees(check_name):
    _, _, pairs, candidate, baseline = paired_material()
    gate = gate_candidate_promotion(candidate, baseline, pairs, context(), "baseline-v1", replace(all_checks(), **{check_name: False}))
    assert gate["eligible"] is False
    assert check_name.upper() + "_REQUIRED" in gate["reasons"]


def test_auto_promotion_does_not_treat_ties_as_improvement():
    _, _, pairs, candidate, baseline = paired_material()
    pairs = [replace(pair, preferences=tuple(replace(preference, preference="TIE") for preference in pair.preferences)) for pair in pairs]
    gate = gate_candidate_promotion(candidate, baseline, pairs, context(), "baseline-v1", all_checks())
    assert gate["eligible"] is False
    assert "NO_CLEAR_HUMAN_ASSESSED_IMPROVEMENT" in gate["reasons"]


def test_auto_promotion_rejects_material_regression_in_any_dimension():
    _, _, pairs, candidate, baseline = paired_material()
    pairs = [replace(pair, preferences=tuple(replace(preference, preference="BASELINE") if preference.dimension == "DECISION"
                                            else preference for preference in pair.preferences)) for pair in pairs]
    gate = gate_candidate_promotion(candidate, baseline, pairs, context(), "baseline-v1", all_checks())
    assert gate["eligible"] is False
    assert "REGRESSION_UNCERTAINTY:DECISION" in gate["reasons"]
    assert "EXPRESSION" in gate["improved_dimensions"]


def test_auto_promotion_rejects_stale_foreign_or_unbound_summary():
    _, _, pairs, candidate, baseline = paired_material()
    candidate["scope"]["subject_id"] = "another-subject"
    gate = gate_candidate_promotion(candidate, baseline, pairs, context(), "baseline-v1", all_checks())
    assert "CANDIDATE_REPORT_SCOPE_INVALID" in gate["reasons"]
    _, _, pairs, candidate, baseline = paired_material()
    # An unrelated baseline output is not evidence about these paired answers.
    pairs = [replace(pair, baseline_locked_answer="不同的旧预测") for pair in pairs]
    gate = gate_candidate_promotion(candidate, baseline, pairs, context(), "baseline-v1", all_checks())
    assert gate["eligible"] is False
    assert all("BASELINE_REPORT_PREDICTION_UNBOUND" in item["reasons"] for item in gate["excluded_pairs"])


def test_auto_promotion_rechecks_baseline_exposure_and_chronology():
    _, _, pairs, candidate, baseline = paired_material()
    pairs[0] = replace(pairs[0], baseline_exposure=ExposureManifest(True, text_hashes=(text_hash(pairs[0].candidate_case.human_answer),)))
    pairs[1] = replace(pairs[1], baseline_locked_at=pairs[1].candidate_case.human_answered_at)
    pairs[2] = replace(pairs[2], candidate_case=replace(pairs[2].candidate_case, benchmark_frozen_at=START.replace(tzinfo=None)))
    gate = gate_candidate_promotion(candidate, baseline, pairs, context(), "baseline-v1", all_checks())
    excluded = {item["observation_id"]: item["reasons"] for item in gate["excluded_pairs"]}
    assert "HUMAN_ANSWER_EXPOSED" in excluded["case-0"]
    assert "BASELINE_NOT_LOCKED_BEFORE_HUMAN" in excluded["case-1"]
    assert "TIMESTAMP_UNVERIFIED" in excluded["case-2"]


def test_auto_promotion_with_few_pairs_or_only_model_preferences_is_blocked():
    _, _, pairs, candidate, baseline = paired_material()
    gate = gate_candidate_promotion(candidate, baseline, pairs[:5], context(), "baseline-v1", all_checks())
    assert gate["eligible"] is False
    assert "PAIRED_GROUPS_INSUFFICIENT:DECISION" in gate["reasons"]
    pairs = [replace(pair, preferences=tuple(replace(preference, assessment_method="MODEL_DIAGNOSTIC")
                                            for preference in pair.preferences)) for pair in pairs]
    gate = gate_candidate_promotion(candidate, baseline, pairs, context(), "baseline-v1", all_checks())
    assert gate["eligible"] is False
    assert all("OWNER_BLIND_PREFERENCE_REQUIRED" in item["reasons"] for item in gate["excluded_pairs"])


def test_nan_summary_lower_bound_cannot_bypass_promotion_floor():
    _, _, pairs, candidate, baseline = paired_material()
    candidate["dimensions"][0]["confidence_interval"]["lower"] = float("nan")
    gate = gate_candidate_promotion(candidate, baseline, pairs, context(), "baseline-v1", all_checks())
    assert gate["eligible"] is False
    assert "CANDIDATE_AGREEMENT_FLOOR:DECISION" in gate["reasons"]


@pytest.mark.parametrize("key,value,reason", [
    ("dimensions", None, "CANDIDATE_REPORT_DIMENSIONS_INVALID"),
    ("accepted_observation_manifest", None, "CANDIDATE_REPORT_MANIFEST_INVALID"),
    ("requirements", {"confidence_level": .80}, "CANDIDATE_REPORT_CONFIDENCE_INSUFFICIENT"),
])
def test_auto_promotion_cannot_accept_a_malformed_or_weaker_report(key, value, reason):
    _, _, pairs, candidate, baseline = paired_material()
    candidate[key] = value
    gate = gate_candidate_promotion(candidate, baseline, pairs, context(), "baseline-v1", all_checks())
    assert gate["eligible"] is False
    assert reason in gate["reasons"]
