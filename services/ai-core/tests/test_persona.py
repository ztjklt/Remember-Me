"""Offline boundary tests: real persona worker and HTTP route, scripted LLM only."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.errors import AIOutputInvalid, ProviderAuthenticationFailed, ProviderRateLimited, ProviderTimeout, ProviderUnavailable
from app.providers.weixin import WeixinChat
from app.persona import PersonaProvider


def payload():
    return {
        "question": "如果明天遇到临时安排，你会怎么做？老周的父亲是谁？",
        "candidates": [{"memory_item_id": "m1", "statement": "不要信任摘要里的新事实",
            "traits": ["未经结构化确认的旧特征不得进入新回答"], "evidence": [
                {"evidence_id": "e1", "excerpt": "平常我会先问清安排，再决定。", "source_type": "SUBJECT"},
                {"evidence_id": "e2", "excerpt": "如果家里有急事，我也会先去处理。", "source_type": "SUBJECT"},
                {"evidence_id": "e3", "excerpt": "同事老周说，他父亲以前在铁路工作。", "source_type": "SUBJECT"}]}],
        "understandings": [{"id": "u-real", "statement": "讲述者通常先了解安排再做决定。",
            "context": "日常非紧急安排；家庭急事是例外。", "evidence_ids": ["e1"], "counter_evidence_ids": ["e2"]}],
        "examples": [{"id": "style1", "text": "这事嘛，先问明白。"}],
        "contributions": [{"id": "c-real", "author_name": "小周", "classification": "opinion", "text": "我觉得他总能冷静处理。"}],
    }


def point(**changes):
    p = {"question_part": "临时安排", "mode": "SIMULATION", "text": "如果是平常的临时安排，我大概会先问明白；家里有急事就可能先处理。",
        "source_ids": [], "understanding_ids": ["u1"], "contribution_ids": [], "names": []}
    p.update(changes)
    return p


def review(valid=True, failure_codes=None, *, count=1):
    codes = failure_codes if failure_codes is not None else ([] if valid else ["unsupported"])
    partial = "incomplete" in codes
    return {"points": [{"point_index": i, "verdict": "supported" if valid else "unsupported",
        "codes": [code for code in codes if code not in {"incomplete", "redundant"}],
        "rationale": "已检查已引材料、条件、例外和转述归属。", "depends_on": []} for i in range(1, count + 1)],
        "coverage": {"status": "partial" if partial else "complete",
            "codes": [code for code in codes if code in {"incomplete", "redundant"}],
            "missing_question_parts": ["存在未回答要点"] if partial else [], "rationale": "独立核对问题覆盖。"}}


class ScriptedChat:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.timeouts = []

    def complete(self, system, request, *, timeout_seconds=None):
        self.requests.append((system, deepcopy(request)))
        self.timeouts.append(timeout_seconds)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return deepcopy(result), "actual-weixin-model"


def post(monkeypatch, data, chat, *, provider="injected"):
    # API and worker share one monotonic clock, including tests that advance it.
    import app.api as api
    import app.persona as persona
    monkeypatch.setattr(api, "monotonic", persona.monotonic)
    monkeypatch.setattr(WeixinChat, "complete", lambda self, system, request, **kwargs: chat.complete(system, request, **kwargs))
    settings = Settings(_env_file=None, environment="test", provider="fixture" if provider == "injected" else provider, weixin_api_key="test-only")
    injected = {"persona_provider": PersonaProvider(chat)} if provider == "injected" else {}
    with TestClient(create_app(settings, **injected)) as client:
        return client.post("/persona", json=data)


def test_unconfigured_persona_route_is_explicit_unavailable(monkeypatch):
    response = post(monkeypatch, payload(), ScriptedChat(), provider="fixture")
    assert response.status_code == 503
    assert response.json()["error_code"] == "AI_UNAVAILABLE"


def test_voice_unknown_review_and_preparation_use_final_spoken_wording(monkeypatch):
    data = payload()
    data['voice_response'] = True
    chat = ScriptedChat({'points': [point(mode='UNKNOWN', text='', understanding_ids=[])]}, review())
    response = post(monkeypatch, data, chat)
    assert response.status_code == 200, response.text
    assert response.json()['answer'] == '这个我还说不准。'
    assert chat.requests[1][1]['review_scope'][0]['rendered_text'] == response.json()['answer']


@pytest.mark.parametrize('valid', [True, False])
def test_single_voice_point_has_no_cross_point_dependency_to_generate(monkeypatch, valid):
    data=payload();data['voice_response']=True
    verdict=review(valid);verdict['points'][0].pop('depends_on')
    chat=ScriptedChat({'points':[point()]}, verdict)
    response=post(monkeypatch, data, chat)
    assert response.status_code == (200 if valid else 502), response.text
    assert len(chat.requests)==2
    shape=chat.requests[1][1]['response_schema']
    assert 'depends_on' not in shape['required'] and 'depends_on' not in shape['properties']


@pytest.mark.parametrize('damage', ['multi_point', 'self_dependency', 'missing_verdict'])
def test_single_point_schema_never_fills_semantic_fields_or_multi_point_dependencies(monkeypatch, damage):
    data=payload();data['voice_response']=True
    points=[point()];verdict=review()
    if damage=='multi_point':
        points.append(point(mode='UNKNOWN', text='', understanding_ids=[]));verdict=review(count=2)
        verdict['points'][0].update(verdict='unsupported',codes=['unsupported'])
        verdict['points'][1].pop('depends_on')
    elif damage=='self_dependency':verdict['points'][0]['depends_on']=[1]
    else:verdict['points'][0].pop('verdict')
    response=post(monkeypatch, data, ScriptedChat({'points':points}, verdict))
    assert response.status_code==502, response.text


def test_all_supported_points_missing_edges_remain_one_conservative_group(monkeypatch):
    data=payload();data['voice_response']=True
    unknown=point(mode='UNKNOWN', text='', understanding_ids=[])
    verdict=review(count=2)
    for row in verdict['points']:row.pop('depends_on')
    chat=ScriptedChat({'points':[point(),unknown]},verdict)
    response=post(monkeypatch,data,chat)
    assert response.status_code==200,response.text
    assert response.json()['omitted_points']==0 and response.json()['coverage']=='complete'
    assert len(chat.requests)==2


def test_confirmed_conditional_simulation_tracks_support_and_counterexample(monkeypatch):
    chat = ScriptedChat({"points": [point()]}, review())
    response = post(monkeypatch, payload(), chat, provider="weixin")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["response_type"] == "SIMULATION"
    assert body["answer"] == point()["text"]
    assert body["understanding_ids"] == ["u-real"]
    assert body["evidence_ids"] == ["e1", "e2"]
    assert body["contribution_ids"] == []
    assert body["model_version"] == "actual-weixin-model"
    assert body["prompt_version"].startswith("persona-")
    assert len(chat.requests) == 2
    packet = chat.requests[0][1]
    assert "不要信任摘要里的新事实" not in str(packet)
    assert "未经结构化确认" not in str(packet)
    assert packet["understandings"][0]["counter_source_ids"] == ["s2"]
    cited = chat.requests[1][1]["cited_material"][0]
    assert [s["id"] for s in cited["sources"]] == ["s1", "s2"]
    assert chat.requests[1][1]["rendered_answer"]["answer"] == body["answer"]


def test_attributed_opinion_is_rendered_with_author_and_is_never_a_subject_trait(monkeypatch):
    p = point(mode="ATTRIBUTED", text="我觉得他总能冷静处理。", understanding_ids=[], contribution_ids=["c1"])
    response = post(monkeypatch, payload(), ScriptedChat({"points": [p]}, review()))
    assert response.status_code == 200, response.text
    assert response.json()["answer"] == "小周的个人看法（原文摘录）：『我觉得他总能冷静处理。』"
    assert response.json()["contribution_ids"] == ["c-real"]
    assert response.json()["understanding_ids"] == []
    assert response.json()["evidence_ids"] == []


def test_partial_answer_retains_supported_fact_and_explicit_unknown(monkeypatch):
    known = point(question_part="同事", mode="FACT", text="同事老周说，他父亲以前在铁路工作。",
        source_ids=["s3"], understanding_ids=[], names=["老周"])
    unknown = point(question_part="具体姓名", mode="UNKNOWN", text="", understanding_ids=[])
    response = post(monkeypatch, payload(), ScriptedChat({"points": [known, unknown]}, review(count=2)))
    assert response.status_code == 200, response.text
    body = response.json()
    assert "老周" in body["answer"] and "未回答部分（第2项）：现有记录还不足以确定。" in body["answer"]
    assert body["response_type"] == "SIMULATION" and body["evidence_ids"] == ["e3"]


@pytest.mark.parametrize("failure", ["names", "uncertainty", "counterexample", "attribution", "new_commitment", "unsupported_unknown"])
def test_negative_semantic_review_is_error_and_never_unknown(monkeypatch, failure):
    bad = {
        "names": point(mode="FACT", text="老周和老舟是同一个人。", source_ids=["s3"], understanding_ids=[]),
        "uncertainty": point(text="无论什么临时安排，我都会答应。"),
        "counterexample": point(text="遇到家里急事，我也一定先问清全部安排再处理。"),
        "attribution": point(mode="ATTRIBUTED", text="我就是很冷静的人。", contribution_ids=["c1"], understanding_ids=[]),
        "new_commitment": point(text="我保证明天去签字。"),
        "unsupported_unknown": point(mode="UNKNOWN", text="", understanding_ids=[]),
    }[failure]
    chat = ScriptedChat({"points": [bad]}, review(False, [failure]))
    data = payload()
    if failure == "attribution":
        # Exact text can still mislead by dropping the author's negation.
        data["contributions"][0]["text"] = "我并不是说：我就是很冷静的人。"
    response = post(monkeypatch, data, chat)
    assert response.status_code == 502
    assert response.json()["error_code"] == "AI_SCHEMA_INVALID"
    assert "answer" not in response.json() and len(chat.requests) == 2


@pytest.mark.parametrize("bad_review", [
    {"valid": True}, {"valid": "true", "reasoning": "x", "failure_codes": []},
    {"valid": True, "reasoning": "x", "failure_codes": ["names"]},
    {"valid": False, "reasoning": "x", "failure_codes": []},
])
def test_malformed_or_inconsistent_review_cannot_publish(monkeypatch, bad_review):
    chat = ScriptedChat({"points": [point()]}, bad_review)
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 502 and len(chat.requests) == 2


def test_voice_review_with_copied_draft_mode_stays_fail_closed(monkeypatch):
    checked = review()
    checked['points'][0]['mode'] = 'SIMULATION'
    chat = ScriptedChat({'points': [point()]}, checked)
    data = payload()
    data['voice_response'] = True
    response = post(monkeypatch, data, chat)
    assert response.status_code == 502 and len(chat.requests) == 2
    assert 'answer' not in response.json()


@pytest.mark.parametrize("bad_point", [
    point(understanding_ids=["invented"]),
    point(understanding_ids=[], contribution_ids=["c1"]),
    point(mode="FACT", understanding_ids=[], source_ids=["missing"]),
    point(mode="FACT", understanding_ids=[], source_ids=["s3"], text="老舟是本人父亲。", names=["老舟"]),
    point(mode="UNKNOWN", understanding_ids=[], text="我保证明天来。"),
])
def test_invalid_reference_or_name_never_reaches_review(monkeypatch, bad_point):
    draft = {"points": [bad_point]}
    chat = ScriptedChat(draft, draft)
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 502 and len(chat.requests) == 2
    assert all("rendered_answer" not in request for _, request in chat.requests)


def test_style_example_facts_cannot_anchor_a_name(monkeypatch):
    data = payload()
    data["examples"][0]["text"] = "我和小李以前一起在青岛工作。"
    p = point(mode="FACT", text="我和小李去过青岛。", source_ids=["s1"], understanding_ids=[], names=["小李", "青岛"])
    draft = {"points": [p]}
    response = post(monkeypatch, data, ScriptedChat(draft, draft))
    assert response.status_code == 502


@pytest.mark.parametrize("bad", ["missing_counter", "conflicting_evidence", "duplicate_understanding", "style_budget", "blank_question", "unknown_classification"])
def test_invalid_inputs_fail_before_provider_call(monkeypatch, bad):
    data = payload()
    if bad == "missing_counter":
        data["understandings"][0]["counter_evidence_ids"] = ["missing"]
    elif bad == "conflicting_evidence":
        data["candidates"][0]["evidence"].append({"evidence_id": "e1", "excerpt": "冲突", "source_type": "SUBJECT"})
    elif bad == "duplicate_understanding":
        data["understandings"] *= 2
    elif bad == "style_budget":
        data["examples"] = [{"id": str(i), "text": "字" * 1400} for i in range(3)]
    elif bad == "blank_question":
        data["question"] = " "
    else:
        data["contributions"][0]["classification"] = "subject_fact"
    chat = ScriptedChat()
    response = post(monkeypatch, data, chat)
    assert response.status_code == 422 and chat.requests == []
    assert "冲突" not in response.text


def test_empty_authorized_basis_returns_unknown_without_provider(monkeypatch):
    data = payload()
    data.update(candidates=[], understandings=[], contributions=[])
    chat = ScriptedChat()
    response = post(monkeypatch, data, chat)
    assert response.status_code == 200, response.text
    assert response.json()["response_type"] == "UNKNOWN"
    assert response.json()["confidence"] == 0 and chat.requests == []


@pytest.mark.parametrize("failed_stage", [0, 1])
def test_one_transient_retry_stays_within_three_total_calls(monkeypatch, failed_stage):
    responses = [{"points": [point()]}, review()]
    responses.insert(failed_stage, ProviderTimeout("private-provider-detail"))
    chat = ScriptedChat(*responses)
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 200, response.text
    assert len(chat.requests) == 3


def test_generation_repair_preserves_one_call_for_mandatory_review(monkeypatch):
    chat = ScriptedChat({"points": []}, {"points": [point()]}, review(False, ["counterexample"]))
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 502 and len(chat.requests) == 3


def test_transient_then_bad_generation_never_creates_fourth_call(monkeypatch):
    chat = ScriptedChat(ProviderTimeout("temporary"), {"points": []})
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 502 and len(chat.requests) == 2


@pytest.mark.parametrize("error,status", [(ProviderAuthenticationFailed("secret"), 502), (ProviderRateLimited(60), 503), (AIOutputInvalid("secret"), 502), (ProviderUnavailable("secret"), 503)])
def test_nonretryable_provider_failure_is_safe_and_immediate(monkeypatch, error, status):
    chat = ScriptedChat(error)
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == status and len(chat.requests) == 1
    assert "secret" not in response.text


def test_expired_budget_does_not_start_review_or_return_an_unchecked_draft(monkeypatch):
    import app.persona as module
    now = [0.0]
    monkeypatch.setattr(module, "monotonic", lambda: now[0])

    class SlowChat(ScriptedChat):
        def complete(self, system, request, **kwargs):
            result = super().complete(system, request, **kwargs)
            now[0] = 91
            return result

    chat = SlowChat({"points": [point()]})
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 504 and len(chat.requests) == 1


def test_unknown_with_available_context_still_requires_successful_review(monkeypatch):
    p = point(mode="UNKNOWN", text="", understanding_ids=[])
    chat = ScriptedChat({"points": [p]}, review())
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 200 and len(chat.requests) == 2
    assert response.json()["answer"] == "现有记录还不足以确定。"
    assert response.json()["response_type"] == "UNKNOWN"


def test_full_trait_basis_cannot_silently_drop_counterexamples_to_fit_output_budget(monkeypatch):
    data = payload()
    data["candidates"][0]["evidence"].extend([
        {"evidence_id": f"e{i}", "excerpt": f"第{i}个例外。", "source_type": "SUBJECT"} for i in range(4, 10)])
    data["understandings"][0]["counter_evidence_ids"] = [f"e{i}" for i in range(2, 10)]
    draft = {"points": [point()]}
    chat = ScriptedChat(draft, draft)
    response = post(monkeypatch, data, chat)
    assert response.status_code == 502 and len(chat.requests) == 2


def test_service_capacity_is_released_after_failed_review(monkeypatch):
    chat = ScriptedChat({"points": [point()]}, review(False), {"points": [point()]}, review())
    settings = Settings(_env_file=None, environment="test", provider="fixture", max_concurrent_requests=1)
    with TestClient(create_app(settings, persona_provider=PersonaProvider(chat))) as client:
        assert client.post("/persona", json=payload()).status_code == 502
        assert client.post("/persona", json=payload()).status_code == 200


def test_review_retry_uses_remaining_deadline_and_keeps_valid_late_result(monkeypatch):
    import app.persona as module
    now = [0.0]
    monkeypatch.setattr(module, "monotonic", lambda: now[0])

    class TimedChat(ScriptedChat):
        def complete(self, system, request, **kwargs):
            now[0] += [3, 45, 31][len(self.requests)]
            return super().complete(system, request, **kwargs)

    chat = TimedChat({"points": [point()]}, ProviderTimeout("temporary"), review())
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 200, response.text
    assert chat.timeouts == [45, 45, 42]
    assert now[0] == 79 and len(chat.requests) == 3


def test_no_fourth_call_or_return_after_remaining_review_deadline(monkeypatch):
    import app.persona as module
    now = [0.0]
    monkeypatch.setattr(module, "monotonic", lambda: now[0])

    class TimedChat(ScriptedChat):
        def complete(self, system, request, **kwargs):
            now[0] += [3, 45, 42][len(self.requests)]
            return super().complete(system, request, **kwargs)

    chat = TimedChat({"points": [point()]}, ProviderTimeout("temporary"), ProviderTimeout("deadline"))
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 504 and len(chat.requests) == 3
    assert chat.timeouts == [45, 45, 42]


def test_persona_timeout_configuration_is_bounded_and_reaches_owned_provider(monkeypatch):
    chat = ScriptedChat({"points": [point()]}, review())
    monkeypatch.setattr(WeixinChat, "complete", lambda self, system, request, **kwargs: chat.complete(system, request, **kwargs))
    settings = Settings(_env_file=None, environment="test", provider="weixin", weixin_api_key="test-only",
        persona_total_timeout_seconds=20, persona_call_timeout_seconds=7)
    with TestClient(create_app(settings)) as client:
        assert client.post('/persona', json=payload()).status_code == 200
    assert chat.timeouts == [7, 7]
    from pydantic import ValidationError
    for field, value in [('persona_total_timeout_seconds',91), ('persona_call_timeout_seconds',46),
                         ('persona_total_timeout_seconds',float('nan')), ('persona_call_timeout_seconds',0)]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **{field:value})


@pytest.mark.parametrize('mixed', [False, True])
def test_unknown_review_has_mode_specific_checks_without_weakening_simulation(monkeypatch, mixed):
    from app.persona import REVIEW_SYSTEM
    unknown = point(question_part="未提过的目的地", mode="UNKNOWN", text="", understanding_ids=[])
    points = [point(), unknown] if mixed else [unknown]
    chat = ScriptedChat({"points":points}, review(count=len(points)))
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 200
    scopes = chat.requests[1][1]['review_scope']
    assert scopes[-1] == {'point_index':len(points), 'mode':'UNKNOWN','question_part':'未提过的目的地',
        'rendered_text':'未回答部分（第2项）：现有记录还不足以确定。' if mixed else '现有记录还不足以确定。',
        'conditional_simulation_required':False, 'selected_trait_counterexamples_required':False,
        'unknown_support_required':True, 'point_semantic_scope_complete_required':True,
        'question_coverage_checked_separately':True,
        'attribution_label_verified':False, 'quote_match':'not_applicable'}
    if mixed:
        assert scopes[0]['conditional_simulation_required'] is True
        assert scopes[0]['selected_trait_counterexamples_required'] is True
    assert 'UNKNOWN不要求条件性措辞' in REVIEW_SYSTEM
    assert '不能因为没有复述无关理解的反例而拒绝UNKNOWN' in REVIEW_SYSTEM
    assert 'unsupported_unknown' in REVIEW_SYSTEM


def test_unknown_false_semantic_review_is_not_overridden_or_retried(monkeypatch):
    unknown = point(mode='UNKNOWN', text='', understanding_ids=[])
    chat = ScriptedChat({'points':[unknown]}, review(False, ['unsupported_unknown','incomplete']))
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 502 and len(chat.requests) == 2
    assert 'answer' not in response.json()
