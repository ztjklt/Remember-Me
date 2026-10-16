"""Verify prompt routing and evidence preservation, not subjective model quality."""
import pytest

from app.persona import PersonaInput, PersonaProvider
from app.quoted_twin import QuotedTwin
from test_persona import ScriptedChat, payload, point, review
from test_quoted_twin import data


@pytest.mark.parametrize("voice", [False, True])
def test_persona_style_reaches_generation_without_relaxing_review(voice):
    chat = ScriptedChat({"points": [point()]}, review())
    result = PersonaProvider(chat).answer(PersonaInput.model_validate(dict(payload(), voice_response=voice)))
    system, request = chat.requests[0]
    assert "natural-dialogue-v1" in system
    assert ("连续语音补充" in system) == voice
    assert "反例" in system and "不能编造" in system
    assert result.evidence_ids == ["e1", "e2"]
    assert result.answer == point()["text"]
    assert len(chat.requests) == 2
    assert "persona-semantic-review" in chat.requests[1][0]
    assert chat.requests[1][1]["rendered_answer"]["answer"] == result.answer


def test_quote_style_preserves_exact_source_and_does_not_add_rewrite_call():
    class Chat:
        def __init__(self): self.calls = []
        def complete(self, system, packet):
            self.calls.append((system, packet))
            if len(self.calls) == 1:
                return {"points": [{"known": True, "source_ids": ["s1"]}]}, "test-model"
            return {"reasoning": "The complete exact source supports this statement.", "valid": True,
                    "failure_codes": [], "replacement": None}, "test-model"
    source = data()
    source.voice_response = True
    chat = Chat()
    result = QuotedTwin(chat).answer(source)
    assert "natural-dialogue-v1" in chat.calls[0][0]
    assert "不得改写原文" in chat.calls[0][0]
    assert len(chat.calls) == 2
    assert '同事老周告诉我，他父亲曾在铁路工作。' in result.answer
    assert result.evidence_ids == ["e1"]
