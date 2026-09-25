import pytest
from pydantic import ValidationError

from app.config import Settings


def test_api_key_is_redacted_from_settings_representations():
    settings = Settings(api_key="test-only-private-key", _env_file=None)
    assert "test-only-private-key" not in repr(settings)
    assert "test-only-private-key" not in settings.model_dump_json()


@pytest.mark.parametrize("overrides", [
    {"timeout_seconds": float("inf")},
    {"model": "   "},
    {"model_version": "   "},
    {"provider": "openai_compatible"},
    {"base_url": "ftp://example.test/v1"},
    {"base_url": "https://user:secret@example.test/v1"},
    {"base_url": "https://example.test/v1?key=secret"},
    {"base_url": "https://example.test/v1#fragment"},
    {"max_concurrent_requests": 0},
    {"max_request_bytes": 0},
    {"prompt_version": "nonexistent-prompt"},
    {"schema_version": "integration-contract-v999"},
])
def test_invalid_configuration_fails_before_serving(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_real_provider_accepts_explicit_model_and_version():
    settings = Settings(
        provider="openai_compatible", model="local-model", model_version="local-revision-1",
        base_url="http://127.0.0.1:8080/v1", _env_file=None,
    )
    assert settings.model_version == "local-revision-1"


def test_json_object_mode_can_be_selected_for_a_compatible_provider():
    settings = Settings(
        provider="openai_compatible", model="test-model", model_version="test-v1",
        structured_output_mode="json_object", _env_file=None,
    )
    assert settings.structured_output_mode == "json_object"
