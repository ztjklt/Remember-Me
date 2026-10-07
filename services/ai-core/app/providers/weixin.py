"""Bounded Weixin JSON-object transport; retry policy belongs to backend jobs."""
import json
import logging
from time import perf_counter
import httpx
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from ..errors import AIOutputInvalid, ProviderTimeout, ProviderUnavailable, ProviderAuthenticationFailed
from .ollama import PROMPT, grounded_result

BASE_URL = 'https://chatapi.weixin.qq.com/openai/v1'
MODEL = 'Deepseek-v4-flash'
logger = logging.getLogger('remember_me.ai_core')


def reject_constant(value):
    raise ValueError('Nonfinite JSON number')


class WeixinChat:
    def __init__(self, *, api_key, model=MODEL, base_url=BASE_URL, timeout_seconds=45,
                 max_response_bytes=1_048_576, client=None):
        if base_url != BASE_URL or model != MODEL:
            raise ValueError('Weixin requires its approved endpoint and model')
        self.api_key, self.model, self.base_url = api_key, model, base_url
        self.timeout_seconds = 45
        self.max_response_bytes = max_response_bytes
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=45, trust_env=False)

    def close(self):
        if self._owns_client:
            self.client.close()

    def complete(self, system, payload):
        started = perf_counter()
        telemetry = {'event':'weixin_chat', 'requested_model':self.model, 'status':None}
        try:
            body = {'model': self.model, 'messages':[
                {'role':'system','content':system},
                {'role':'user','content':json.dumps(payload, ensure_ascii=False)}],
                'response_format':{'type':'json_object'}}
            with self.client.stream('POST', self.base_url + '/chat/completions', json=body,
                    headers={'Authorization':'Bearer ' + self.api_key, 'Content-Type':'application/json'},
                    timeout=45, follow_redirects=False) as response:
                telemetry['status'] = response.status_code
                if response.status_code in {401,403}:
                    raise ProviderAuthenticationFailed('Weixin authentication failed')
                if response.status_code in {408,504}:
                    raise ProviderTimeout('Weixin timed out')
                if response.status_code == 429 or response.status_code >= 500:
                    raise ProviderUnavailable('Weixin temporarily unavailable')
                if not response.is_success:
                    raise AIOutputInvalid('Weixin rejected request')
                chunks = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    if len(chunks) + len(chunk) > self.max_response_bytes:
                        raise AIOutputInvalid('Weixin output too large')
                    chunks.extend(chunk)
            envelope = json.loads(chunks, parse_constant=reject_constant)
            model = envelope['model']
            if not isinstance(model, str) or not model.strip() or len(model) > 128:
                raise AIOutputInvalid('Weixin model identity missing')
            telemetry['response_model'] = model
            usage = envelope.get('usage', {})
            telemetry['usage'] = {k:v for k,v in usage.items() if k in {'prompt_tokens','completion_tokens','total_tokens'} and isinstance(v,int) and not isinstance(v,bool)} if isinstance(usage,dict) else {}
            choice = envelope['choices'][0]
            finish = choice.get('finish_reason')
            telemetry['finish_reason'] = finish if finish in {'stop','length','content_filter','tool_calls'} else 'unknown'
            if finish != 'stop' or choice['message'].get('refusal'):
                raise AIOutputInvalid('Weixin output incomplete or refused')
            result = json.loads(choice['message']['content'], parse_constant=reject_constant)
            if not isinstance(result, dict):
                raise AIOutputInvalid('Weixin output must be an object')
            return result, model
        except httpx.TimeoutException as exc:
            raise ProviderTimeout('Weixin timed out') from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailable('Weixin transport failed') from exc
        except (ValueError, KeyError, IndexError, TypeError, AttributeError, RecursionError) as exc:
            raise AIOutputInvalid('Weixin malformed JSON output') from exc
        finally:
            telemetry['duration_ms'] = round((perf_counter()-started)*1000, 3)
            logger.info(json.dumps(telemetry, ensure_ascii=True))


class CompactMemory(BaseModel):
    """Reject malformed suggestions before provenance grounding can filter them."""
    model_config = ConfigDict(extra='forbid', strict=True)
    quote: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    domain: Literal['IDENTITY','EPISODIC_MEMORY','RELATIONSHIPS','PREFERENCES','VALUES_BELIEFS','DECISION_PATTERNS','EXPRESSION']
    memory_type: Literal['EVENT','PERSON','RELATIONSHIP','PREFERENCE','VALUE','EMOTION']
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @field_validator('quote', 'statement')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Blank compact field')
        return value


class CompactExtraction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    memories: list[CompactMemory] = Field(max_length=24)


class WeixinProvider(WeixinChat):
    def generate(self, request):
        raw, version = self.complete(PROMPT + '\n只返回符合以下结构的 JSON：' + json.dumps(CompactExtraction.model_json_schema(), ensure_ascii=False), {'transcript': request.payload.transcript})
        try:
            validated = CompactExtraction.model_validate(raw)
        except ValidationError as exc:
            raise AIOutputInvalid('Weixin extraction compact schema invalid') from exc
        return grounded_result(validated.model_dump(), request, model_version=version)

    @staticmethod
    def response_model_version(output):
        return output['model_version']
class WeixinTwinProvider(WeixinChat):
    def answer(self, payload):
        from ..twin import TwinOutput, TWIN_SYSTEM
        from pydantic import ValidationError
        if not payload.candidates:
            return TwinOutput(answer='现有记录还不足以确定。', response_type='UNKNOWN', evidence_ids=[], confidence=0, model_version='no-evidence')
        raw, version = self.complete(TWIN_SYSTEM, payload.model_dump())
        try:
            raw['model_version'] = version
            output = TwinOutput.model_validate(raw)
            # Python len counts Unicode code points, including punctuation, spaces,
            # emoji and combining marks. It is deliberately not a Han-only count.
            if len(output.answer) > 200:
                raise AIOutputInvalid('Twin answer exceeds 200 Unicode code points')
            evidence = {e.evidence_id:e for c in payload.candidates for e in c.evidence}
            if not set(output.evidence_ids) <= evidence.keys():
                raise AIOutputInvalid('Twin cites unknown evidence')
            if output.response_type != 'UNKNOWN' and not output.evidence_ids:
                raise AIOutputInvalid('Twin answer needs evidence')
            if output.response_type == 'ORIGINAL' and not any(evidence[i].source_type == 'SUBJECT' and evidence[i].excerpt == output.answer for i in output.evidence_ids):
                raise AIOutputInvalid('Twin original is not supplied subject evidence')
            return output
        except (ValidationError, TypeError, ValueError) as exc:
            raise AIOutputInvalid('Twin schema invalid') from exc


class WeixinCalibrationProvider(WeixinChat):
    def compare(self, payload):
        from ..calibration import CalibrationOutput, SYSTEM
        from pydantic import ValidationError
        raw, version = self.complete(SYSTEM, payload.model_dump())
        try:
            raw['model_version'] = version
            output = CalibrationOutput.model_validate(raw)
            if any(d.human_excerpt not in payload.human_answer for d in output.dimensions if d.human_excerpt is not None):
                raise AIOutputInvalid('Calibration excerpt absent from human answer')
            return output
        except (ValidationError, TypeError, ValueError) as exc:
            raise AIOutputInvalid('Calibration schema invalid') from exc
