"""Anker event router; shared source-selection and evidence protocols remain unchanged."""
from .json_chat import JsonObjectChat
from .weixin import WeixinProvider, WeixinTwinProvider, WeixinCalibrationProvider

BASE_URL = 'https://ai-router-cn-pub.anker-in.com'
MODELS = frozenset('hackathon/v_model/' + name for name in
    ('qwen-max', 'glm-5.2', 'deepseek-v4-pro', 'deepseek-v4.1-flash', 'kimi-k3', 'nova-pro'))


class AnkerChat(JsonObjectChat):
    BASE_URL = BASE_URL
    MODELS = MODELS


class AnkerMemoryProvider(AnkerChat):
    # Reuse locally validated source-handle selection rather than changing Contract.
    generate = WeixinProvider.generate
    response_model_version = staticmethod(WeixinProvider.response_model_version)


class AnkerTwinProvider(AnkerChat):
    answer = WeixinTwinProvider.answer
    review_answer = WeixinTwinProvider.review_answer

    def __init__(self, *, focus_hints=False, verify_answers=True,
                 structured_answers=False, quote_answers=False, **kwargs):
        super().__init__(**kwargs)
        self.focus_hints, self.verify_answers = focus_hints, verify_answers
        self.structured_answers, self.quote_answers = structured_answers, quote_answers


class AnkerCalibrationProvider(AnkerChat):
    compare = WeixinCalibrationProvider.compare
