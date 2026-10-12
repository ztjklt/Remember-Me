"""Only the selected contribution's exact rendered author is a prefix anchor."""
from copy import deepcopy

import pytest

from test_persona import ScriptedChat, point, post
from test_persona_point_review import SAVED_NOTE, checked, reviewed, saved_case


def saved_author_draft(*, repaired=False):
    # Exact retained v7 L01 drafts, trace 6a7501fbd4f9480ea8cca26fd8e999d4.
    first = point(question_part="亲友署名补记的原话" if repaired else "亲友这次署名补记的原话是什么",
        mode="ATTRIBUTED", text=SAVED_NOTE, understanding_ids=[], contribution_ids=["c1"],
        names=[] if repaired else ["A01 亲友体验", "陈国良"])
    second = point(question_part="这是谁的记录", mode="ATTRIBUTED",
        text="这是一段虚构亲友的署名补记，不是陈国良本人的原话。", understanding_ids=[], contribution_ids=["c1"],
        names=["A01 亲友体验"] if repaired else ["A01 亲友体验", "陈国良"])
    return {"points": [first, second]}


@pytest.mark.parametrize("repaired", [False, True])
def test_saved_actual_author_anchor_can_be_in_rendered_prefix(monkeypatch, repaired):
    data, _ = saved_case(simple=True)
    draft = saved_author_draft(repaired=repaired)
    chat = ScriptedChat(draft, reviewed(checked(1), checked(2), redundant=True))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 200, response.text
    assert len(chat.requests) == 2
    assert response.json()["contribution_ids"] == ["saved-c1"]
    assert response.json()["prompt_version"] == "persona-conditional-reviewed-v8"
    scopes = chat.requests[1][1]["review_scope"]
    assert all(p["rendered_text"].startswith("A01 亲友体验的亲历观察（原文摘录）：『") for p in scopes)
    assert "A01 亲友体验" not in draft["points"][1]["text"]


@pytest.mark.parametrize("name", ["不存在的作者", "亲友体验", "亲历观察", "另一个作者", "旁观者甲"])
def test_unrendered_or_nonexact_author_names_do_not_receive_prefix_exception(monkeypatch, name):
    data, _ = saved_case(simple=True)
    data["contributions"][0]["text"] += "旁观者甲也在场。"
    data["contributions"].append(dict(id="other-note", author_name="另一个作者", classification="opinion", text="我的看法不同。"))
    p = saved_author_draft()["points"][1]
    p["names"] = [name]
    draft = {"points": [p]}
    chat = ScriptedChat(draft, deepcopy(draft))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 502 and len(chat.requests) == 2
    assert chat.requests[1][1]["validation_error"]["category"] == "name_text_mismatch"
    assert "answer" not in response.json()


@pytest.mark.parametrize("mode", ["FACT", "SIMULATION"])
def test_non_attributed_modes_do_not_receive_author_prefix_exception(monkeypatch, mode):
    data, _ = saved_case(simple=True)
    data["candidates"][0]["evidence"][0]["excerpt"] = "A01 亲友体验记得那次我先问清安排。"
    if mode == "SIMULATION":
        from test_persona import payload
        data["understandings"] = payload()["understandings"]
    p = point(mode=mode, text="那次我先问清安排。", source_ids=["s1"],
        understanding_ids=["u1"] if mode == "SIMULATION" else [], names=["A01 亲友体验"])
    draft = {"points": [p]}
    chat = ScriptedChat(draft, deepcopy(draft))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 502 and len(chat.requests) == 2
    assert chat.requests[1][1]["validation_error"]["category"] == "name_text_mismatch"


def test_matching_author_does_not_excuse_another_fabricated_name_in_quote(monkeypatch):
    data, _ = saved_case(simple=True)
    p = saved_author_draft()["points"][1]
    p["text"] = "虚构名字说他见过我。"
    p["names"] = ["A01 亲友体验", "虚构名字"]
    draft = {"points": [p]}
    chat = ScriptedChat(draft, deepcopy(draft))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 502 and len(chat.requests) == 2
    assert chat.requests[1][1]["validation_error"]["category"] == "name_source_mismatch"
    assert "answer" not in response.json()
