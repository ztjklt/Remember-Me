import httpx
from fastapi.testclient import TestClient

from app.main import create_app


def test_raw_audio_is_forwarded_as_multipart_and_returns_nonfake_version():
    seen = {}

    def upstream(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        seen["type"] = request.headers["content-type"]
        return httpx.Response(200, json={"text": "  我喜欢咖啡。  "})

    client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    app = create_app(whisper_url="http://whisper.test", model_version="whisper-base-rev1", client=client)
    with TestClient(app) as test_client:
        response = test_client.post("/transcribe", content=b"audio-bytes", headers={"Content-Type": "audio/mp4"})
    assert response.status_code == 200
    assert response.json() == {"text": "我喜欢咖啡。", "model_version": "whisper-base-rev1"}
    assert b"audio-bytes" in seen["body"]
    assert b'response_format' in seen["body"]
    assert seen["type"].startswith("multipart/form-data")


def test_invalid_audio_and_empty_transcript_fail_closed():
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"text": "  "})))
    app = create_app(whisper_url="http://whisper.test", model_version="whisper-base-rev1", client=upstream)
    with TestClient(app) as client:
        assert client.post("/transcribe", content=b"x", headers={"Content-Type": "application/octet-stream"}).status_code == 415
        assert client.post("/transcribe", content=b"", headers={"Content-Type": "audio/mp4"}).status_code == 422
        assert client.post("/transcribe", content=b"audio", headers={"Content-Type": "audio/mp4"}).status_code == 422
