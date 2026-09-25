"""Advisory five-dimension comparison of locked Twin and human answers."""

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .errors import AIOutputInvalid

ASSESSMENT_VERSION = "calibration-assessment-v1"
Verdict = Literal["MATCH", "DIFFERENT", "UNCERTAIN"]

DIMENSION_CUES = {
    "decision": ("决定", "选择", "打算", "decide", "choose", "decision"),
    "reasoning": ("因为", "原因", "所以", "考虑", "because", "reason", "therefore"),
    "value_priority": ("更重要", "优先", "原则", "价值", "priority", "value", "principle"),
    "emotional_reaction": ("感到", "情绪", "开心", "难过", "害怕", "生气", "feel", "happy", "sad", "angry"),
    "expression": ("说话方式", "语气", "表达", "措辞", "tone", "wording", "expression"),
}
INSUFFICIENT_ANSWER = ("没有足够", "无法可靠回答", "insufficient evidence", "cannot answer")


class CalibrationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=1000)
    locked_answer: str = Field(min_length=1, max_length=5000)
    human_answer: str = Field(min_length=1, max_length=5000)


class DimensionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    rationale: str = Field(min_length=1, max_length=300)


class CalibrationAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: DimensionAssessment
    reasoning: DimensionAssessment
    value_priority: DimensionAssessment
    emotional_reaction: DimensionAssessment
    expression: DimensionAssessment
    overall: Verdict
    model_version: str
    assessment_version: str


class ComparisonProvider(Protocol):
    def compare(self, payload: CalibrationInput, schema: dict[str, Any]) -> dict[str, Any]: ...
    def close(self) -> None: ...


class CalibrationAssessor:
    def __init__(self, *, provider: ComparisonProvider, model_version: str) -> None:
        self.provider = provider
        self.model_version = model_version

    def assess(self, payload: CalibrationInput) -> CalibrationAssessment:
        raw = self.provider.compare(payload, CalibrationAssessment.model_json_schema())
        try:
            output = CalibrationAssessment.model_validate(raw)
        except ValidationError as exc:
            raise AIOutputInvalid("Calibration provider failed the assessment schema") from exc
        output.model_version = self.model_version
        output.assessment_version = ASSESSMENT_VERSION
        locked = payload.locked_answer.casefold()
        human = payload.human_answer.casefold()
        if any(marker in locked for marker in INSUFFICIENT_ANSWER):
            output.overall = "UNCERTAIN"
        elif locked == human:
            output.overall = "MATCH"
        for dimension, cues in DIMENSION_CUES.items():
            if (
                output.overall == "UNCERTAIN"
                or not any(cue in locked for cue in cues)
                or not any(cue in human for cue in cues)
            ):
                item = getattr(output, dimension)
                item.verdict = "UNCERTAIN"
                item.rationale = "两个回答未同时提供该维度的直接信息。"
        return output
