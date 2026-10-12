"""Official DeepSeek JSON chat for existing profile/schema workers."""
from .json_chat import JsonObjectChat


class DeepSeekChat(JsonObjectChat):
    BASE_URL = 'https://api.deepseek.com'
    MODELS = frozenset({'deepseek-flash', 'deepseek-v4-flash'})
    request_options = {'thinking': {'type': 'disabled'}, 'temperature': 0}
    response_model_prefix = 'deepseek-'
