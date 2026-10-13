import asyncio
import json
import logging
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.contracts import load_fixture
from app.extractor import MemoryExtractor
from app.errors import ProviderTimeout
from app.providers.fixture import FixtureProvider


def payload():
    return load_fixture("phase1-happy").model_dump(exclude_none=True)


class BlockingProvider:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()

    def generate(self, request):
        self.entered.set()
        self.release.wait(timeout=2)
        self.finished.set()
        return FixtureProvider().generate(request)


def test_slow_extraction_does_not_block_health_or_overload_rejection():
    provider = BlockingProvider()
    extractor = MemoryExtractor(provider=provider, model="test", model_version="v1")
    app = create_app(Settings(_env_file=None, environment="test", max_concurrent_requests=1), extractor=extractor)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            first = asyncio.create_task(client.post("/process", json=payload()))
            try:
                assert await asyncio.to_thread(provider.entered.wait, 3)
                health = await client.get("/health")
                assert health.status_code == 200
                assert not provider.finished.is_set(), "Health waited for the model to finish"
                overload = await client.post("/process", json=payload())
                assert overload.status_code == 503
                assert overload.json()["error_code"] == "AI_UNAVAILABLE"
            finally:
                provider.release.set()
                assert (await first).status_code == 200
            assert (await client.post("/process", json=payload())).status_code == 200

    asyncio.run(scenario())


def test_interactive_twin_waits_for_busy_background_slot_without_extra_model_call():
    provider = BlockingProvider()
    extractor = MemoryExtractor(provider=provider, model='test', model_version='v1')
    class Twin:
        calls = 0
        def answer(self, payload):
            from app.twin import TwinOutput
            self.calls += 1
            return TwinOutput(answer='unknown', response_type='UNKNOWN', evidence_ids=[], confidence=0, model_version='test')
    twin = Twin()
    app = create_app(Settings(_env_file=None, environment='test', max_concurrent_requests=1), extractor=extractor, twin_provider=twin)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            first=asyncio.create_task(client.post('/process',json=payload()))
            assert await asyncio.to_thread(provider.entered.wait,3)
            second=asyncio.create_task(client.post('/twin',json={'question':'q','candidates':[]}))
            await asyncio.sleep(.1)
            waiting=not second.done()
            provider.release.set()
            assert (await first).status_code==200
            result=await second
            assert waiting and result.status_code==200
            assert twin.calls==1
    asyncio.run(scenario())


@pytest.mark.parametrize("streamed", [False, True])
def test_request_body_limit_applies_before_json_validation(streamed):
    app = create_app(Settings(_env_file=None, environment="test", max_request_bytes=512))
    data = json.dumps({**payload(), "transcript": "x" * 2048}).encode()
    with TestClient(app) as client:
        response = client.post(
            "/process", content=(part for part in [data[:500], data[500:]]) if streamed else data,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert client.post("/process", json=payload()).status_code == 200


def test_invalid_request_does_not_echo_transcript_or_unknown_field_names():
    data = {"transcript": "PRIVATE-TRANSCRIPT", "PRIVATE-KEY-NAME": "PRIVATE-VALUE"}
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        response = client.post("/process", json=data)
    assert response.status_code == 422
    assert "PRIVATE" not in response.text
    assert "episode_id" in response.text


def test_runtime_records_trace_duration_and_outcome_without_memory_text(caplog):
    data = {**payload(), "trace_id": "trace-test-123", "transcript": "PRIVATE-TRANSCRIPT喜欢咖啡。"}
    with caplog.at_level(logging.INFO, logger="remember_me.ai_core"):
        with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
            assert client.post("/process", json=data).status_code == 200
    records = [record for record in caplog.records if record.name == "remember_me.ai_core"]
    assert records
    event = json.loads(records[-1].getMessage())
    assert event["trace_id"] == "trace-test-123"
    assert event["outcome"] == "ok"
    assert event["duration_ms"] >= 0
    assert "PRIVATE-TRANSCRIPT" not in caplog.text


def test_failed_extraction_releases_capacity_for_the_next_request(caplog):
    class FailOnceProvider:
        failed = False

        def generate(self, request):
            if not self.failed:
                self.failed = True
                raise ProviderTimeout("PRIVATE-UPSTREAM-ERROR")
            return FixtureProvider().generate(request)

    extractor = MemoryExtractor(provider=FailOnceProvider(), model="test", model_version="v1")
    app = create_app(Settings(_env_file=None, environment="test", max_concurrent_requests=1), extractor=extractor)
    with caplog.at_level(logging.INFO, logger="remember_me.ai_core"), TestClient(app) as client:
        assert client.post("/process", json=payload()).status_code == 504
        assert client.post("/process", json=payload()).status_code == 200
    assert "AI_TIMEOUT" in caplog.text
    assert "PRIVATE-UPSTREAM-ERROR" not in caplog.text


def test_body_limit_does_not_trust_a_forged_content_length():
    app = create_app(Settings(_env_file=None, environment="test", max_request_bytes=64))
    data = json.dumps(payload()).encode()

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/process", content=data, headers={"Content-Length": "1"})
            assert response.status_code == 413

    asyncio.run(scenario())
