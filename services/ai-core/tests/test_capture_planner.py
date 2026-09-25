"""Guided capture uses model gaps and supplies actual follow-up questions."""

import pytest

from app.capture_planner import CapturePlanner, PlannerInput
from app.errors import AIOutputInvalid


class Stub:
    def __init__(self, output):
        self.output = output

    def complete(self, payload, schema, prompt, name):
        assert name == "remember_me_capture_plan"
        assert payload["calibrations"][0]["domains"] == ["Preferences"]
        return self.output


def payload():
    return PlannerInput.model_validate({
        "coverage": {"Preferences": 1},
        "traits": [{"domain": "Preferences", "statement": "过去喜欢咖啡",
                    "confidence": 0.7, "status": "disputed", "conflict_type": "unresolved"}],
        "calibrations": [{"question": "喜欢什么？", "human_answer": "现在喝茶",
                          "domains": ["Preferences"]}],
        "limit": 2,
    })


def output():
    question = {
        "domain": "Preferences", "question": "你什么时候从咖啡改喝茶？",
        "followups": ["当时有什么具体经历让你改变？"],
        "rationale": "最近的校准指出偏好发生变化",
        "information_gain": 1.5, "importance": 1.2, "uncertainty": 1.8,
        "time_urgency": 1.3, "interaction_cost": 1,
    }
    return {"questions": [question, {**question, "domain": "Relationships",
                                    "question": "谁曾影响你改变这个习惯？"}],
            "model_version": "untrusted", "planning_version": "untrusted"}


def test_dynamic_capture_questions_keep_followups_and_version():
    result = CapturePlanner(provider=Stub(output()), model_version="deepseek-real").plan(payload())
    assert len(result.questions) == 2
    assert result.questions[0].followups == ["当时有什么具体经历让你改变？"]
    assert result.planning_version == "capture-planner-llm-v1"
    assert result.model_version == "deepseek-real"


def test_repeated_main_question_is_rejected():
    invalid = output()
    invalid["questions"][1]["question"] = invalid["questions"][0]["question"]
    with pytest.raises(AIOutputInvalid):
        CapturePlanner(provider=Stub(invalid), model_version="real").plan(payload())
