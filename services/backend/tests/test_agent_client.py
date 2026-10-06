import httpx
import pytest
from remember_contracts.agent import QuestionRequest

from app.agent_client import AgentClient
from app.errors import AiSchemaInvalid, AiUnavailable


@pytest.mark.parametrize('code', ['AI_SCHEMA_INVALID', 'EVIDENCE_INVALID'])
def test_worker_validation_errors_are_not_service_unavailability(monkeypatch, code):
    monkeypatch.setattr(httpx, 'post', lambda *args, **kwargs: httpx.Response(
        502, json={'error_code': code, 'error_message': 'PRIVATE-PROVIDER-OUTPUT'}))
    with pytest.raises(AiSchemaInvalid) as error:
        AgentClient('http://worker.test').call('twin', QuestionRequest(question="test"), object)
    assert error.value.http_status == 502 and not error.value.retryable
    assert 'PRIVATE' not in str(error.value)


@pytest.mark.parametrize('status,body', [(503, {'error_code': 'AI_UNAVAILABLE'}),
                                       (502, None), (500, {})])
def test_unknown_gateway_failures_remain_retryable(monkeypatch, status, body):
    monkeypatch.setattr(httpx, 'post', lambda *args, **kwargs: httpx.Response(status, json=body))
    with pytest.raises(AiUnavailable):
        AgentClient('http://worker.test').call('twin', QuestionRequest(question="test"), object)
