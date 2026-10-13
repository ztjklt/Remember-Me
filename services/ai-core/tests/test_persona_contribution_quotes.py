"""Signed contribution wording belongs to its author, not to the persona."""
import pytest

from test_persona import ScriptedChat, payload, point, post, review


OBSERVATION = "我的观察是他在意东西背后的人和经历。这只是我的一次观察，不能说他每次都这样。"


def contribution_payload():
    data = payload()
    data["question"] = "亲友补记了什么观察？参考补记可以怎样理解，保留一次观察的边界。"
    data["contributions"][0].update(classification="firsthand",
        text="我记得收拾旧书时，他先问是谁留下的，再问对谁还有用没有，马上扔掉。" + OBSERVATION)
    return data


def attributed(text=OBSERVATION, **changes):
    return point(mode="ATTRIBUTED", text=text, understanding_ids=[], contribution_ids=["c1"], **changes)


def test_signed_observation_is_verbatim_and_program_adds_quoted_author_label(monkeypatch):
    data = contribution_payload()
    data["understandings"] = []
    chat = ScriptedChat({"points": [attributed()]}, review())
    response = post(monkeypatch, data, chat)
    assert response.status_code == 200
    assert response.json()["answer"] == "小周的亲历观察（原文摘录）：『" + OBSERVATION + "』"
    assert response.json()["understanding_ids"] == []
    assert response.json()["contribution_ids"] == ["c-real"]
    for _, request in chat.requests:
        assert request["mode_policy"]["ATTRIBUTED"]["text_requirement"] == "continuous_verbatim_quote_from_selected_contribution"
        assert request["mode_policy"]["SIMULATION"]["relatedness_requirement"] == "question_specific_not_merely_shared_topic"


@pytest.mark.parametrize("text", [
    "他先问每本书是谁留下的，再决定扔不扔。",
    "其观察：他先问是谁留下的，再问对谁还有用没有，马上扔掉；其解读是在意东西背后的人和经历。",
    "他在意东西背后的人和经历，不能说他每次都这样。",
    "小周的观察是：" + OBSERVATION,
    OBSERVATION.replace("。", ";"),
])
def test_contribution_paraphrase_splice_or_punctuation_rewrite_is_rejected(monkeypatch, text, caplog):
    draft = {"points": [attributed(text)]}
    chat = ScriptedChat(draft, draft)
    response = post(monkeypatch, contribution_payload(), chat)
    assert response.status_code == 502
    assert chat.requests[1][1]["validation_error"] == {"category": "contribution_quote_basis"}
    assert len(chat.requests) == 2
    assert all("rendered_answer" not in request for _, request in chat.requests)
    assert text not in caplog.text


def test_quote_must_come_from_selected_author_not_another_available_note(monkeypatch):
    data = contribution_payload()
    data["contributions"].append({"id": "c-second", "author_name": "老李", "classification": "opinion",
        "text": "我觉得他重视做东西的过程。这仅是我的看法。"})
    draft = {"points": [attributed("我觉得他重视做东西的过程。这仅是我的看法。") ]}
    chat = ScriptedChat(draft, draft)
    response = post(monkeypatch, data, chat)
    assert response.status_code == 502
    assert chat.requests[1][1]["validation_error"]["category"] == "contribution_quote_basis"


def test_each_author_remains_a_separate_exact_quote(monkeypatch):
    data = contribution_payload()
    data["contributions"].append({"id": "c-second", "author_name": "老李", "classification": "opinion",
        "text": "我的看法不同，不能只看这一次。"})
    second = point(mode="ATTRIBUTED", text="我的看法不同，不能只看这一次。", understanding_ids=[], contribution_ids=["c2"])
    chat = ScriptedChat({"points": [attributed(), second]}, review(count=2))
    response = post(monkeypatch, data, chat)
    assert response.status_code == 200
    assert response.json()["answer"] == "小周的亲历观察（原文摘录）：『" + OBSERVATION + "』\n老李的个人看法（原文摘录）：『我的看法不同，不能只看这一次。』"
    assert response.json()["contribution_ids"] == ["c-real", "c-second"]


def test_cutting_away_negation_still_requires_semantic_rejection_without_retry(monkeypatch):
    # The substring exists, but its source says this cannot be generalized.
    chat = ScriptedChat({"points": [attributed("他每次都这样。") ]}, review(False, ["uncertainty", "attribution"]))
    response = post(monkeypatch, contribution_payload(), chat)
    assert response.status_code == 502 and len(chat.requests) == 2
    assert chat.requests[1][1]["cited_material"][0]["contributions"][0]["text"].endswith(OBSERVATION)
    assert "answer" not in response.json()


def test_repaired_quote_survives_but_does_not_publish_irrelevant_trait(monkeypatch):
    bad = {"points": [attributed("他每次都舍不得旧物。") ]}
    repaired = {"points": [attributed(), point()]}
    checked = review(count=2)
    checked['points'][1].update(verdict='unsupported', codes=['irrelevant'])
    chat = ScriptedChat(bad, repaired, checked)
    response = post(monkeypatch, contribution_payload(), chat)
    assert response.status_code == 200 and len(chat.requests) == 3
    assert chat.requests[1][1]["validation_error"]["category"] == "contribution_quote_basis"
    assert chat.requests[2][1]["review_scope"][1]["conditional_simulation_required"] is True
    assert response.json()['coverage'] == 'partial' and response.json()['omitted_points'] == 1
    assert response.json()['understanding_ids'] == [] and response.json()['contribution_ids'] == ['c-real']
    assert point()['text'] not in response.json()['answer']
