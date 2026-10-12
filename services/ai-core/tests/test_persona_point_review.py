"""Point-level review selection; scripted reviews are not live semantic evidence."""
import json
from copy import deepcopy

import pytest

from app.persona import PersonaInput, PersonaProvider
from test_persona import ScriptedChat, payload, point, post


# Preserved fictional v5 draft text, not a TTS creation script or expected answer
# inserted into production prompts. Historical review reasoning was not saved.
SAVED_NOTE = "这是一段虚构亲友的署名补记，不是陈国良本人的原话。我记得一起收拾旧书时，他先问每本书是谁留下的，再问对谁还有用没有，马上扔掉。我的观察是他在意东西背后的人和经历。这只是我的一次观察，不能说他每次都这样。"
PARTIAL = "部分问题尚未回答。"


def checked(index, verdict="supported", codes=None, depends_on=None, rationale="所引原文支持该要点的完整范围。"):
    return dict(point_index=index, verdict=verdict, codes=codes or [], rationale=rationale, depends_on=depends_on or [])


def reviewed(*points, partial=False, redundant=False, missing=None):
    return {"points": list(points), "coverage": {
        "status": "partial" if partial else "complete",
        "codes": (["incomplete"] if partial else []) + (["redundant"] if redundant else []),
        "missing_question_parts": missing if missing is not None else (["尚未回答的判断"] if partial else []),
        "rationale": "按原问题区分信息覆盖与每点来源支持。"}}


def saved_case(simple=False):
    data = payload()
    data["question"] = ("亲友这次署名补记的原话是什么？请区分这是谁的记录。" if simple else
        "亲友刚才署名补记了什么观察？如果参考这段补记，你可能怎样看待旧物？请明确是谁的观察，保留一次观察的边界。")
    data.update(understandings=[], contributions=[dict(id="saved-c1", author_name="A01 亲友体验", classification="firsthand", text=SAVED_NOTE)])
    quote = point(question_part="亲友补记的原话" if simple else "亲友署名补记的观察", mode="ATTRIBUTED",
        text=SAVED_NOTE, understanding_ids=[], contribution_ids=["c1"], names=["陈国良"])
    second = (dict(quote, question_part="这段记录是谁的") if simple else
        point(question_part="参考补记，你可能怎样看待旧物", mode="UNKNOWN", text="", understanding_ids=[]))
    return data, {"points": [quote, second]}


def factual(**changes):
    return point(mode="FACT", text="同事老周说，他父亲以前在铁路工作。", source_ids=["s3"], understanding_ids=[], names=["老周"], **changes)


def test_saved_compound_quote_survives_incomplete_and_bad_unknown(monkeypatch):
    data, draft = saved_case()
    check = reviewed(checked(1), checked(2, "unsupported", ["unsupported_unknown"]), partial=True)
    chat = ScriptedChat(draft, check)
    response = post(monkeypatch, data, chat)
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "A01 亲友体验的亲历观察（原文摘录）：『" + SAVED_NOTE + "』\n" + PARTIAL
    assert body["coverage"] == "partial" and body["omitted_points"] == 1
    assert body["contribution_ids"] == ["saved-c1"] and body["understanding_ids"] == []
    assert "现有记录还不足以确定" not in body["answer"]
    assert len(chat.requests) == 2
    scope = chat.requests[1][1]["review_scope"][0]
    assert scope["point_index"] == 1 and scope["quote_match"] == "full"
    assert scope["attribution_label_verified"] is True


def test_saved_simple_quote_repetition_is_style_not_hard_rejection(monkeypatch):
    data, draft = saved_case(simple=True)
    response = post(monkeypatch, data, ScriptedChat(draft, reviewed(checked(1), checked(2), redundant=True)))
    assert response.status_code == 200
    assert response.json()["coverage"] == "complete" and response.json()["omitted_points"] == 0
    assert SAVED_NOTE in response.json()["answer"]
    assert PARTIAL not in response.json()["answer"]


def test_reviewer_gets_point_scope_and_no_premature_coverage_result(monkeypatch):
    chat = ScriptedChat({"points": [factual()]}, reviewed(checked(1)))
    assert post(monkeypatch, payload(), chat).status_code == 200
    request = chat.requests[1][1]
    assert "coverage" not in request["rendered_answer"]
    assert "omitted_points" not in request["rendered_answer"]
    assert request["review_scope"][0]["point_semantic_scope_complete_required"] is True
    assert request["review_scope"][0]["question_coverage_checked_separately"] is True
    assert "known_information_completeness_required" not in request["review_scope"][0]


def test_coverage_missing_text_is_not_rendered_as_a_fact(monkeypatch):
    check = reviewed(checked(1), partial=True, missing=["我已经同意转出全部财产"])
    response = post(monkeypatch, payload(), ScriptedChat({"points": [factual()]}, check))
    assert response.status_code == 200
    assert response.json()["answer"] == factual()["text"] + "\n" + PARTIAL
    assert response.json()["coverage"] == "partial" and response.json()["omitted_points"] == 0
    assert "财产" not in response.json()["answer"]


@pytest.mark.parametrize("code,verdict", [("unsupported", "unsupported"), ("attribution", "unsupported"),
    ("new_commitment", "unsupported"), ("counterexample", "unsupported"), ("uncertainty", "unsupported"),
    ("context", "uncertain")])
def test_bad_point_is_removed_but_supported_independent_fact_and_its_refs_survive(monkeypatch, code, verdict):
    bad = point(text="我保证明天按这个办法办，不管有什么例外。")
    check = reviewed(checked(1), checked(2, verdict, [code]), partial=True)
    response = post(monkeypatch, payload(), ScriptedChat({"points": [factual(), bad]}, check))
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == factual()["text"] + "\n" + PARTIAL
    assert body["evidence_ids"] == ["e3"] and body["understanding_ids"] == []
    assert body["omitted_points"] == 1 and body["response_type"] == "SIMULATION"


def test_dependency_on_omitted_point_is_removed_transitively(monkeypatch):
    second = point(text="我保证明天照办。")
    third = point(text="如果是上述安排，我大概会如此办理；紧急情况另说。")
    fourth = point(text="在前述判断成立时，我可能按同样条件处理。")
    check = reviewed(checked(1), checked(2, "unsupported", ["new_commitment"]),
        checked(3, depends_on=[2]), checked(4, depends_on=[3]), partial=True)
    response = post(monkeypatch, payload(), ScriptedChat({"points": [factual(), second, third, fourth]}, check))
    assert response.status_code == 200
    assert response.json()["answer"] == factual()["text"] + "\n" + PARTIAL
    assert response.json()["omitted_points"] == 3
    assert response.json()["evidence_ids"] == ["e3"]


@pytest.mark.parametrize("only_unknown_remains", [False, True])
def test_all_failed_or_only_unknown_after_dropping_known_point_is_failure(monkeypatch, only_unknown_remains):
    points = [point()]
    checks = [checked(1, "unsupported", ["counterexample"])]
    if only_unknown_remains:
        points.append(point(mode="UNKNOWN", text="", understanding_ids=[]))
        checks.append(checked(2))
    chat = ScriptedChat({"points": points}, reviewed(*checks, partial=True))
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 502 and len(chat.requests) == 2
    assert "answer" not in response.json()


def test_supported_pure_unknown_without_omissions_remains_possible(monkeypatch):
    unknown = point(mode="UNKNOWN", text="", understanding_ids=[])
    response = post(monkeypatch, payload(), ScriptedChat({"points": [unknown]}, reviewed(checked(1))))
    assert response.status_code == 200
    assert response.json()["answer"] == "现有记录还不足以确定。"
    assert response.json()["omitted_points"] == 0


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "out_of_range", "self_dependency", "bad_dependency",
    "supported_with_error", "unsupported_without_error", "hard_incomplete", "coverage_conflict", "legacy", "extra"])
def test_malformed_or_unaccounted_review_cannot_publish(monkeypatch, mutation):
    check = reviewed(checked(1), checked(2))
    if mutation == "missing": check["points"].pop()
    elif mutation == "duplicate": check["points"][1]["point_index"] = 1
    elif mutation == "out_of_range": check["points"][1]["point_index"] = 3
    elif mutation == "self_dependency": check["points"][0]["depends_on"] = [1]
    elif mutation == "bad_dependency": check["points"][0]["depends_on"] = [4]
    elif mutation == "supported_with_error": check["points"][0]["codes"] = ["new_commitment"]
    elif mutation == "unsupported_without_error": check["points"][0]["verdict"] = "unsupported"
    elif mutation == "hard_incomplete": check["points"][0].update(verdict="unsupported", codes=["incomplete"])
    elif mutation == "coverage_conflict": check["coverage"]["missing_question_parts"] = ["遗漏"]
    elif mutation == "legacy": check = {"valid": True, "reasoning": "old", "failure_codes": []}
    else: check["PRIVATE_EXTRA_FIELD"] = "PRIVATE_REVIEW_DATA"
    chat = ScriptedChat({"points": [factual(), point()]}, check)
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 502 and len(chat.requests) == 2
    assert "answer" not in response.json()


def test_false_quote_cutoff_is_not_promoted_by_full_author_metadata(monkeypatch):
    data, _ = saved_case()
    cut = point(mode="ATTRIBUTED", text="他每次都这样。", understanding_ids=[], contribution_ids=["c1"])
    chat = ScriptedChat({"points": [cut]}, reviewed(checked(1, "unsupported", ["uncertainty", "attribution"]), partial=True))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 502
    scope = chat.requests[1][1]["review_scope"][0]
    assert scope["quote_match"] == "excerpt"
    assert chat.requests[1][1]["cited_material"][0]["contributions"][0]["text"] == SAVED_NOTE


def test_contribution_cannot_be_laundered_into_personality_via_unrelated_trait(monkeypatch):
    data, draft = saved_case()
    data["understandings"] = payload()["understandings"]
    draft["points"][1] = point(text="我一直看重物品背后的人和经历，所以每次都不会舍弃旧物。")
    check = reviewed(checked(1), checked(2, "unsupported", ["attribution", "irrelevant"]), partial=True)
    response = post(monkeypatch, data, ScriptedChat(draft, check))
    assert response.status_code == 200
    assert "我一直看重" not in response.json()["answer"]
    assert response.json()["understanding_ids"] == [] and response.json()["evidence_ids"] == []
    assert response.json()["contribution_ids"] == ["saved-c1"]


def test_declared_dependency_does_not_excuse_a_missing_necessary_condition(monkeypatch):
    bad = point(text="我不管家里有没有急事，都先问清所有安排。")
    check = reviewed(checked(1), checked(2, "unsupported", ["counterexample"], depends_on=[1]), partial=True)
    response = post(monkeypatch, payload(), ScriptedChat({"points": [factual(), bad]}, check))
    assert response.status_code == 200 and response.json()["omitted_points"] == 1
    assert "不管家里" not in response.json()["answer"]


def test_partial_notice_cannot_exceed_output_budget_or_silently_truncate(monkeypatch):
    data = payload()
    data["candidates"][0]["evidence"][0]["excerpt"] = "甲" * 350
    data["candidates"][0]["evidence"][2]["excerpt"] = "乙" * 148
    points = [point(mode="FACT", text="甲" * 350, source_ids=["s1"], understanding_ids=[]),
        point(mode="FACT", text="乙" * 148, source_ids=["s3"], understanding_ids=[])]
    chat = ScriptedChat({"points": points}, reviewed(checked(1), checked(2), partial=True))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 502 and len(chat.requests) == 2
    assert "answer" not in response.json()


def test_review_rationale_is_only_in_opted_in_fictional_trace(monkeypatch, tmp_path, caplog):
    import app.persona as module
    monkeypatch.setattr(module, "FICTIONAL_TRACE_DIR", tmp_path)
    check = reviewed(checked(1, rationale="PRIVATE_REASON_WITH_SOURCE_TEXT"), partial=True,
        missing=["PRIVATE_MISSING_PART"])
    for enabled in [False, True]:
        chat = ScriptedChat({"points": [factual()]}, deepcopy(check))
        result = PersonaProvider(chat, fictional_debug_trace=enabled).answer(PersonaInput.model_validate(payload()))
        assert result.coverage == "partial"
        if not enabled: assert list(tmp_path.iterdir()) == []
    files = list(tmp_path.glob("*-semantic_review.json"))
    assert len(files) == 1
    stored = json.loads(files[0].read_text(encoding="utf8"))
    assert stored["review"] == check and stored["fictional_debug_only"] is True
    assert "PRIVATE_REASON" not in caplog.text and "PRIVATE_MISSING" not in caplog.text
    events = [json.loads(r.message) for r in caplog.records if r.message.startswith("{")]
    event = [e for e in events if e.get("event") == "persona_request"][-1]
    assert event["point_reviews"] == [{"point_index": 1, "verdict": "supported", "codes": []}]
    assert event["coverage_codes"] == ["incomplete"] and event["missing_question_part_count"] == 1
