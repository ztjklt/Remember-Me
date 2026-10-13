"""Review sees the exact labelled presentation, never a guessed line split."""
from copy import deepcopy

from test_persona import ScriptedChat, payload, point, post
from test_persona_point_review import checked, reviewed, saved_case, SAVED_NOTE


def test_actual_l02_draft_with_empty_names_gets_its_final_author_and_name_text(monkeypatch):
    # trace 5f9712691fe048579b445630aa068d53. Preserve the actual empty names
    # array: it did not mean that the quoted text contained no proper name.
    data, draft = saved_case()
    draft["points"][0].update(question_part="亲友补记了什么观察", names=[])
    chat = ScriptedChat(draft, reviewed(checked(1), checked(2), partial=True))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 200
    packet = chat.requests[1][1]
    scopes = packet["review_scope"]
    expected = "A01 亲友体验的亲历观察（原文摘录）：『" + SAVED_NOTE + "』"
    assert scopes[0]["rendered_text"] == expected
    assert "陈国良" in scopes[0]["rendered_text"]
    assert packet["draft"]["points"][0]["names"] == []
    assert scopes[0]["attribution_label_verified"] is True
    assert scopes[0]["quote_match"] == "full"
    assert scopes[1]["rendered_text"] == "未回答部分（第2项）：现有记录还不足以确定。"
    assert "\n".join(s["rendered_text"] for s in scopes) == packet["rendered_answer"]["answer"]
    assert response.json()["omitted_points"] == 0 and response.json()["coverage"] == "partial"


def test_multiline_contribution_stays_one_labelled_point_in_review(monkeypatch):
    data, _ = saved_case()
    text = "我的记录：\n老周当时说还没有决定。\n这是一次转述。"
    data["contributions"][0].update(text=text, classification="reported")
    quote = point(mode="ATTRIBUTED", text=text, understanding_ids=[], contribution_ids=["c1"], names=["老周"])
    unknown = point(mode="UNKNOWN", text="", understanding_ids=[])
    chat = ScriptedChat({"points": [quote, unknown]}, reviewed(checked(1), checked(2), partial=True))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 200
    packet = chat.requests[1][1]
    assert packet["review_scope"][0]["rendered_text"] == "A01 亲友体验的转述（原文摘录）：『" + text + "』"
    assert len(packet["review_scope"]) == 2
    assert "\n".join(s["rendered_text"] for s in packet["review_scope"]) == packet["rendered_answer"]["answer"]


def test_third_party_fact_review_sees_its_non_subject_quote_label(monkeypatch):
    data, _ = saved_case()
    data["candidates"][0]["evidence"][2].update(source_type="THIRD_PARTY", excerpt="老周说他并没有决定。")
    p = point(mode="FACT", text="老周说他并没有决定。", source_ids=["s3"], understanding_ids=[])
    chat = ScriptedChat({"points": [p]}, reviewed(checked(1)))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 200
    scope = chat.requests[1][1]["review_scope"][0]
    assert scope["rendered_text"] == "第三方记录（非本人原话）原文摘录：『老周说他并没有决定。』"
    assert scope["rendered_text"] == response.json()["answer"]


def test_third_party_view_does_not_require_inventing_a_subject_trait(monkeypatch):
    data, draft = saved_case()
    data["candidates"] = []
    data["understandings"] = []
    chat = ScriptedChat(draft, reviewed(checked(1), checked(2), partial=True))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 200
    assert response.json()["understanding_ids"] == []
    assert response.json()["omitted_points"] == 0
    for _, packet in chat.requests:
        policy = packet["mode_policy"]["UNKNOWN"]
        assert policy["third_party_observation_is_not_subject_trait"] is True
        assert policy["subject_simulation_requires_related_confirmed_understanding"] is True
    # Scripted review proves the supported UNKNOWN path is kept, not that a
    # live model will always classify this scope correctly.
    assert "现有记录还不足以确定" in response.json()["answer"]


def test_visible_true_quote_cannot_substitute_an_unavailable_target(monkeypatch):
    data = payload()
    data["question"] = "请复述那段还未分享的录音内容。"
    data["candidates"][0]["evidence"][2]["excerpt"] = "我录了一段生日祝福。"
    unknown = point(question_part="未分享的录音内容", mode="UNKNOWN", text="", understanding_ids=[])
    # The generated subquestion invents relevance that the user's question did
    # not supply. A true visible quote does not identify the unavailable target.
    extra = point(question_part="未分享录音的内容说明", mode="FACT", text="我录了一段生日祝福。",
        source_ids=["s3"], understanding_ids=[])
    chat = ScriptedChat({"points": [unknown, extra]}, reviewed(checked(1),
        checked(2, "unsupported", ["irrelevant", "context"]), partial=True))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 502  # Cannot disguise rejected known content as pure UNKNOWN.
    assert "answer" not in response.json()
    for _, packet in chat.requests:
        assert packet["evidence_policy"] == {
            "verbatim_does_not_establish_relevance": True,
            "visible_similar_material_cannot_substitute_unavailable_target": True,
            "draft_question_part_is_not_new_user_request": True,
        }
        assert packet["question"] == data["question"]


def test_same_visible_quote_is_deliverable_when_it_answers_actual_question(monkeypatch):
    data = payload()
    data["question"] = "已分享的那段录音里，他说录了什么？"
    data["candidates"][0]["evidence"][2]["excerpt"] = "我录了一段生日祝福。"
    quote = point(mode="FACT", text="我录了一段生日祝福。", source_ids=["s3"], understanding_ids=[])
    chat = ScriptedChat({"points": [quote]}, reviewed(checked(1)))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 200
    assert response.json()["answer"] == quote["text"]
    assert response.json()["evidence_ids"] == ["e3"]


def test_name_elsewhere_in_input_does_not_fix_missing_selected_context(monkeypatch):
    data = payload()
    data["candidates"][0]["evidence"][0]["excerpt"] = "小林那天给我打过电话。"
    data["candidates"][0]["evidence"][2]["excerpt"] = "他在这次通话里只说了几句。"
    draft = {"points": [point(mode="FACT", text="小林在这次通话里只说了几句。",
        source_ids=["s3"], understanding_ids=[], names=["小林"])]}
    chat = ScriptedChat(draft, deepcopy(draft))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 502 and len(chat.requests) == 2
    repair = chat.requests[1][1]
    assert repair["validation_error"]["category"] == "name_source_mismatch"
    assert repair["rejected_draft"] == draft


def test_name_repair_can_select_the_connected_context_without_global_fallback(monkeypatch):
    data = payload()
    data["candidates"][0]["evidence"][0]["excerpt"] = "小林那天给我打过电话。"
    data["candidates"][0]["evidence"][2]["excerpt"] = "他在这次通话里只说了几句。"
    draft = {"points": [point(mode="FACT", text="小林在这次通话里只说了几句。",
        source_ids=["s3"], understanding_ids=[], names=["小林"])]}
    repaired = deepcopy(draft)
    repaired["points"][0]["source_ids"] = ["s1", "s3"]
    chat = ScriptedChat(draft, repaired, reviewed(checked(1)))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 200 and len(chat.requests) == 3
    assert response.json()["evidence_ids"] == ["e1", "e3"]
    assert [s["id"] for s in chat.requests[2][1]["cited_material"][0]["sources"]] == ["s1", "s3"]


def test_matching_name_in_unrelated_selected_story_still_requires_semantic_identity(monkeypatch):
    data = payload()
    data["candidates"][0]["evidence"][0]["excerpt"] = "我以前有个同事叫小林。"
    data["candidates"][0]["evidence"][2]["excerpt"] = "另一个人昨天打电话，只说了几句。"
    p = point(mode="FACT", text="小林昨天打电话，只说了几句。", source_ids=["s1", "s3"],
        understanding_ids=[], names=["小林"])
    chat = ScriptedChat({"points": [p]}, reviewed(checked(1, "unsupported", ["names", "context"])))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 502 and len(chat.requests) == 2
    assert "answer" not in response.json()
