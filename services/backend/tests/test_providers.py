"""The provider boundaries: what the fakes promise, and how a real one fails.

Neither provider is frozen (ADR-0001 D9), so both sit behind a Protocol and the
only thing the rest of the service knows about them is the shape they return.
That makes two properties worth asserting here rather than in the worker: the
fakes are deterministic and identifiable as fakes, and every way a real provider
can fail arrives as a code from the taxonomy instead of a raw httpx exception.

Both boundaries have a real transport as well as a fake, and both of those are
exercised the same way: against a mock httpx transport, so the wire contract is
visible in the test rather than described in a comment.
"""

import json

import httpx
import pytest

from app.ai_core import (
    FAKE_MODEL_VERSION,
    FAKE_PROMPT_VERSION,
    FakeAiCoreClient,
    HttpAiCoreClient,
    build_ai_client,
)
from app.config import Settings
from app.contracts import SCHEMA_VERSION, AICoreInput, AICoreOutput
from app.errors import (
    AiFailed,
    AiSchemaInvalid,
    AiTimeout,
    AiUnavailable,
    SttFailed,
    SttTimeout,
    SttUnavailable,
)
from app.stt import (
    UNREPORTED_MODEL_VERSION,
    FakeSttProvider,
    HttpSttProvider,
    build_stt_provider,
)
from app.storage.base import checksum_of

AUDIO = b"RIFF\x00\x00\x00\x00WAVEfmt "

INPUT = AICoreInput(
    episode_id="ep_0000000000000001",
    subject_id="subj_ada",
    transcript="We walked by the river.\n\nShe said the water was cold.",
    existing_model_version="none",
    trace_id="trace-0001",
)

VALID_OUTPUT = {
    "memory_items": [
        {
            "memory_type": "EVENT",
            "content": "A walk by the river.",
            "source_type": "AI_INFERENCE",
            "evidence_ids": ["ev_1"],
            "confidence": 0.4,
            "model_version": "ai-core-v1",
            "prompt_version": "extract-v1",
            "schema_version": SCHEMA_VERSION,
        }
    ],
    "graph_updates": [],
    "persona_updates": [],
    "evidence": [
        {
            "evidence_id": "ev_1",
            "source_type": "SUBJECT",
            "source_ref": "episode:ep_0000000000000001#line0",
        }
    ],
    "model_version": "ai-core-v1",
}


@pytest.fixture
def http_post(monkeypatch):
    """Install a mock transport behind httpx.post, and hand back what was sent."""

    def install(handler):  # noqa: ANN001, ANN202 - httpx handler
        transport = httpx.MockTransport(handler)
        sent: list[httpx.Request] = []

        def post(url: str, **kwargs):  # noqa: ANN003, ANN202 - mirrors httpx.post
            with httpx.Client(transport=transport) as client:
                request = client.build_request("POST", url, **kwargs)
                sent.append(request)
                return client.send(request)

        # Both provider boundaries call the same httpx.post, so one patch covers
        # both; that is the reason neither of them builds its own client object.
        monkeypatch.setattr(httpx, "post", post)
        return sent

    return install


def client_for(**overrides) -> HttpAiCoreClient:  # noqa: ANN003
    options = {
        "base_url": "http://ai-core.internal",
        "path": "/process",
        "timeout_seconds": 5.0,
    }
    options.update(overrides)
    return HttpAiCoreClient(**options)


def stt_for(**overrides) -> HttpSttProvider:  # noqa: ANN003
    options = {
        "base_url": "http://stt.internal",
        "path": "/transcribe",
        "timeout_seconds": 5.0,
    }
    options.update(overrides)
    return HttpSttProvider(**options)


def test_the_fake_transcript_is_a_function_of_the_audio_and_says_so():
    provider = FakeSttProvider()

    first = provider.transcribe(AUDIO, "audio/mp4")
    again = provider.transcribe(AUDIO, "audio/mp4")
    other = provider.transcribe(AUDIO + b"x", "audio/mp4")

    assert first == again, "the same audio must transcribe the same way every run"
    assert first != other, "different audio must not transcribe identically"
    # It says what it is. Plausible-sounding placeholder speech would be
    # indistinguishable from a real transcript once it reached the record.
    assert first.text.startswith("[fake-stt]")
    assert checksum_of(AUDIO)[:12] in first.text
    assert str(len(AUDIO)) in first.text
    assert "audio/mp4" in first.text
    assert first.backend == "fake"
    assert first.model_version == "fake-stt-v1"


def test_the_fake_ai_client_turns_each_line_of_the_transcript_into_one_memory():
    output = FakeAiCoreClient().process(INPUT)

    # Three lines, one of them blank: a blank line is not a memory.
    assert len(output.memory_items) == 2
    assert output.model_version == FAKE_MODEL_VERSION

    first, second = output.memory_items
    assert first.content == "[fake-ai] We walked by the river."
    assert second.content == "[fake-ai] She said the water was cold."
    for item in output.memory_items:
        assert item.source_type == "AI_INFERENCE"
        assert item.model_version == FAKE_MODEL_VERSION
        assert item.prompt_version == FAKE_PROMPT_VERSION
        assert item.schema_version == SCHEMA_VERSION
        assert len(item.evidence_ids) == 1

    # Every claim points at evidence that was returned with it, and that
    # evidence is the subject's own words rather than the model's conclusion.
    by_id = {row.evidence_id: row for row in output.evidence}
    assert [row.evidence_id for row in output.evidence] == ["ev_ep_0000000000000001_0", "ev_ep_0000000000000001_1"]
    assert by_id[first.evidence_ids[0]].excerpt == "We walked by the river."
    assert by_id[first.evidence_ids[0]].source_type == "SUBJECT"
    assert by_id[first.evidence_ids[0]].source_ref == "episode:ep_0000000000000001#line0"

    # The graph and persona shapes are Phase 2: the fake leaves them empty
    # rather than inventing content for a shape that is not committed.
    assert output.graph_updates == []
    assert output.persona_updates == []


def test_the_fake_ai_client_is_deterministic():
    client = FakeAiCoreClient()

    assert client.process(INPUT) == client.process(INPUT)


def test_the_fake_output_round_trips_through_the_contract_shape():
    output = FakeAiCoreClient().process(INPUT)

    assert AICoreOutput.model_validate(output.model_dump(mode="json")) == output


def test_a_transcript_with_no_lines_yields_no_memories():
    output = FakeAiCoreClient().process(INPUT.model_copy(update={"transcript": "   \n\n"}))

    assert output.memory_items == []
    assert output.evidence == []
    # The model version is still reported: the Episode that produced this is
    # still labelled with what produced it.
    assert output.model_version == FAKE_MODEL_VERSION


def test_the_request_that_is_sent_is_the_contract_shape(http_post):
    sent = http_post(lambda request: httpx.Response(200, json=VALID_OUTPUT))

    client_for().process(INPUT)

    body = sent[0].read()
    assert sent[0].url == httpx.URL("http://ai-core.internal/process")
    assert json.loads(body) == INPUT.model_dump(mode="json")
    # The job id is internal and never leaves this process.
    assert "job_id" not in INPUT.model_dump(mode="json")


def test_a_valid_answer_is_parsed_into_the_contract_shape(http_post):
    http_post(lambda request: httpx.Response(200, json=VALID_OUTPUT))

    output = client_for().process(INPUT)

    assert output.model_version == "ai-core-v1"
    assert output.memory_items[0].content == "A walk by the river."


def test_a_timeout_is_reported_as_a_timeout(http_post):
    def handler(request):  # noqa: ANN001, ANN202 - httpx handler
        raise httpx.ReadTimeout("the other end went quiet")

    http_post(handler)

    with pytest.raises(AiTimeout) as raised:
        client_for(timeout_seconds=2.5).process(INPUT)

    assert "2.5" in raised.value.message
    assert raised.value.retryable, "a slow model is worth asking again"


def test_an_unreachable_ai_core_is_reported_as_unavailable(http_post):
    def handler(request):  # noqa: ANN001, ANN202 - httpx handler
        raise httpx.ConnectError("connection refused")

    http_post(handler)

    with pytest.raises(AiUnavailable) as raised:
        client_for().process(INPUT)

    assert "http://ai-core.internal/process" in raised.value.message
    assert raised.value.retryable


def test_a_refusal_from_ai_core_is_a_failed_call(http_post):
    http_post(lambda request: httpx.Response(500, text="<html>traceback</html>"))

    with pytest.raises(AiFailed) as raised:
        client_for().process(INPUT)

    assert "500" in raised.value.message
    assert "traceback" in raised.value.message
    # AI Core ran and refused: the same request would be refused again.
    assert not raised.value.retryable


def test_a_response_that_is_not_json_is_a_schema_problem(http_post):
    http_post(lambda request: httpx.Response(200, text="<html>proxy</html>"))

    with pytest.raises(AiSchemaInvalid) as raised:
        client_for().process(INPUT)

    assert "not JSON" in raised.value.message


def test_a_response_missing_a_required_field_names_the_field(http_post):
    http_post(lambda request: httpx.Response(200, json={"memory_items": []}))

    with pytest.raises(AiSchemaInvalid) as raised:
        client_for().process(INPUT)

    assert "graph_updates" in raised.value.message
    assert "validation error" in raised.value.message
    assert not raised.value.retryable


def test_an_unknown_field_in_a_response_is_refused(http_post):
    """Drift is caught here, not by a client that has already been shipped."""
    drifted = {**VALID_OUTPUT, "confidence": 0.9}
    http_post(lambda request: httpx.Response(200, json=drifted))

    with pytest.raises(AiSchemaInvalid) as raised:
        client_for().process(INPUT)

    assert "confidence" in raised.value.message


def test_an_unregistered_enum_value_in_a_response_is_refused(http_post):
    item = {**VALID_OUTPUT["memory_items"][0], "memory_type": "VIBE"}
    http_post(
        lambda request: httpx.Response(200, json={**VALID_OUTPUT, "memory_items": [item]})
    )

    with pytest.raises(AiSchemaInvalid) as raised:
        client_for().process(INPUT)

    assert "memory_type" in raised.value.message


def test_the_fake_providers_are_refused_outside_development():
    """A deployment that forgot a real provider must fail rather than pretend."""
    settings = Settings(_env_file=None, environment="staging")

    with pytest.raises(ValueError, match="staging") as stt_error:
        build_stt_provider(settings)
    assert "speech-to-text" in str(stt_error.value)

    with pytest.raises(ValueError, match="staging") as ai_error:
        build_ai_client(settings)
    assert "AI Core" in str(ai_error.value)


def test_a_fake_may_run_elsewhere_with_an_explicit_override(caplog):
    """The one way a placeholder reaches a deployed environment: being asked for.

    The override exists so an environment can be brought up end to end before its
    real provider is reachable, and the warning is the price of it — an
    environment running on placeholders says so at startup instead of being
    inferred from the record afterwards.
    """
    settings = Settings(
        _env_file=None, environment="staging", allow_fake_providers=True
    )

    with caplog.at_level("WARNING", logger="app.providers"):
        stt = build_stt_provider(settings)
        ai = build_ai_client(settings)

    assert isinstance(stt, FakeSttProvider)
    assert isinstance(ai, FakeAiCoreClient)

    overrides = [record for record in caplog.records if record.message == "providers.fake_allowed_by_override"]
    assert len(overrides) == 2, "one per provider built"
    assert {record.extra_fields["provider"] for record in overrides} == {
        "speech-to-text",
        "AI Core",
    }
    assert all(record.extra_fields["environment"] == "staging" for record in overrides)


def test_the_http_client_is_built_from_settings():
    settings = Settings(
        _env_file=None,
        environment="staging",
        ai_backend="http",
        ai_core_url="http://ai-core.internal/",
        ai_core_path="/process",
        ai_timeout_seconds=12.5,
    )

    client = build_ai_client(settings)

    assert isinstance(client, HttpAiCoreClient)
    # The trailing slash is dropped here rather than producing a double slash in
    # the URL that is actually requested.
    assert client.base_url == "http://ai-core.internal"
    assert client.path == "/process"
    assert client.timeout_seconds == 12.5


def test_the_http_stt_provider_is_built_from_settings():
    settings = Settings(
        _env_file=None,
        environment="staging",
        stt_backend="http",
        stt_url="http://stt.internal/",
        stt_path="/transcribe",
        stt_timeout_seconds=90.0,
    )

    provider = build_stt_provider(settings)

    assert isinstance(provider, HttpSttProvider)
    assert provider.base_url == "http://stt.internal"
    assert provider.path == "/transcribe"
    assert provider.timeout_seconds == 90.0


# The deployment speech-to-text transport. Its wire contract is this module's
# own — the audio is the body, the answer is JSON with a text field — so it is
# tested against that contract rather than against a vendor.


def test_the_audio_is_the_request_body_and_the_declared_type_is_the_header(http_post):
    sent = http_post(lambda request: httpx.Response(200, json={"text": "hello"}))

    stt_for().transcribe(AUDIO, "audio/mp4")

    assert sent[0].url == httpx.URL("http://stt.internal/transcribe")
    assert sent[0].headers["content-type"] == "audio/mp4"
    assert sent[0].read() == AUDIO


def test_a_transcript_is_read_with_the_model_that_produced_it(http_post):
    http_post(
        lambda request: httpx.Response(
            200, json={"text": "We walked by the river.", "model_version": "whisper-large-v3"}
        )
    )

    transcript = stt_for().transcribe(AUDIO, "audio/mp4")

    assert transcript.text == "We walked by the river."
    assert transcript.backend == "http"
    assert transcript.model_version == "whisper-large-v3"


def test_a_provider_that_names_no_model_is_recorded_as_unreported(http_post):
    """Absence gets a name, so the record never reads a missing version as a real one."""
    for body in ({"text": "hello"}, {"text": "hello", "model_version": ""}, {"text": "hello", "model_version": None}):
        http_post(lambda request, body=body: httpx.Response(200, json=body))

        assert stt_for().transcribe(AUDIO, "audio/mp4").model_version == UNREPORTED_MODEL_VERSION


def test_a_slow_provider_is_reported_as_a_timeout(http_post):
    def handler(request):  # noqa: ANN001, ANN202 - httpx handler
        raise httpx.ReadTimeout("the other end went quiet")

    http_post(handler)

    with pytest.raises(SttTimeout) as raised:
        stt_for(timeout_seconds=2.5).transcribe(AUDIO, "audio/mp4")

    assert raised.value.code == "STT_TIMEOUT"
    assert "2.5" in raised.value.message
    assert raised.value.retryable, "a slow provider is worth asking again"


def test_an_unreachable_provider_is_reported_as_unavailable(http_post):
    def handler(request):  # noqa: ANN001, ANN202 - httpx handler
        raise httpx.ConnectError("connection refused")

    http_post(handler)

    with pytest.raises(SttUnavailable) as raised:
        stt_for().transcribe(AUDIO, "audio/mp4")

    assert raised.value.code == "STT_UNAVAILABLE"
    assert "http://stt.internal/transcribe" in raised.value.message
    assert raised.value.retryable


@pytest.mark.parametrize(
    ("status_code", "error_type", "retryable"),
    [
        (413, SttFailed, False),
        (422, SttFailed, False),
        (500, SttFailed, False),
        (502, SttFailed, False),
        (503, SttUnavailable, True),
        (504, SttTimeout, True),
    ],
)
def test_the_status_a_provider_answers_keeps_the_retry_boundary(
    http_post, status_code, error_type, retryable
):
    """A refusal and a provider that is not ready yet are not the same failure.

    This is the same table the AI Core boundary keeps, deliberately: one worker
    decides whether to retry using `retryable` alone, so a status that meant
    "retry" on one provider and "stop" on the other would make the worker's
    behaviour depend on which stage it happened to be running.

    503 is the one that matters in practice. A model server that is still
    loading answers 503, and treating that as terminal ends the Episode on a
    condition that clears by itself — with the audio already stored, and two
    unused attempts left in the budget.
    """
    http_post(lambda request: httpx.Response(status_code, text="provider error"))

    with pytest.raises(error_type) as raised:
        stt_for().transcribe(AUDIO, "audio/mp4")

    assert str(status_code) in raised.value.message
    assert "provider error" in raised.value.message
    assert raised.value.retryable is retryable


def test_a_response_that_is_not_json_is_a_failed_call(http_post):
    http_post(lambda request: httpx.Response(200, text="<html>proxy</html>"))

    with pytest.raises(SttFailed) as raised:
        stt_for().transcribe(AUDIO, "audio/mp4")

    assert "not JSON" in raised.value.message


def test_a_response_without_a_text_field_is_a_failed_call(http_post):
    """A 200 that says nothing is not a transcript, and must not read as one."""
    for body in ({"transcript": "hello"}, {"text": 12}, []):
        http_post(lambda request, body=body: httpx.Response(200, json=body))

        with pytest.raises(SttFailed) as raised:
            stt_for().transcribe(AUDIO, "audio/mp4")

        assert "text" in raised.value.message