"""Focused wire and failure tests for verify_stt_endpoint.py."""

from __future__ import annotations

import unittest

import httpx

from verify_stt_endpoint import SttCheckFailed, endpoint, verify


AUDIO = b"RIFF\x00\x00\x00\x00WAVEfmt real sample"
URL = "http://127.0.0.1:8200/transcribe"


class SttEndpointTests(unittest.TestCase):
    def run_response(
        self,
        response: httpx.Response | None = None,
        *,
        expected_fragment: str | None = None,
        handler=None,
    ):
        def respond(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url), URL)
            self.assertEqual(request.headers["content-type"], "audio/wav")
            self.assertEqual(request.read(), AUDIO)
            if handler is not None:
                return handler(request)
            return response or httpx.Response(
                200, json={"text": "I prefer tea.", "model_version": "stt-test-v1"}
            )

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            return verify(
                url=URL,
                audio=AUDIO,
                content_type="audio/wav",
                timeout_seconds=1,
                expected_fragment=expected_fragment,
                client=client,
            )

    def test_raw_audio_and_recognition_phrase(self) -> None:
        result = self.run_response(expected_fragment="prefer tea")
        self.assertEqual(result.model_version, "stt-test-v1")
        self.assertEqual(result.text_chars, len("I prefer tea."))
        self.assertTrue(result.expected_phrase_checked)

    def test_fake_or_empty_transcript_fails(self) -> None:
        for text in ("", "[fake-stt] no speech recognition ran"):
            with self.subTest(text=text), self.assertRaises(SttCheckFailed):
                self.run_response(httpx.Response(200, json={
                    "text": text, "model_version": "stt-test-v1"
                }))

    def test_missing_or_fake_model_version_fails(self) -> None:
        for model in (None, "", "fake-stt-v1", " fake-stt-v1 "):
            with self.subTest(model=model), self.assertRaises(SttCheckFailed):
                self.run_response(httpx.Response(200, json={
                    "text": "I prefer tea.", "model_version": model
                }))

    def test_unrecognized_phrase_fails_without_echoing_audio(self) -> None:
        with self.assertRaisesRegex(SttCheckFailed, "Expected spoken phrase"):
            self.run_response(expected_fragment="coffee")

    def test_http_and_json_failures_are_safe(self) -> None:
        for response in (
            httpx.Response(503, text="private provider trace"),
            httpx.Response(200, text="private non-json transcript"),
            httpx.Response(200, json=[]),
        ):
            with self.subTest(status=response.status_code), self.assertRaises(SttCheckFailed) as raised:
                self.run_response(response)
            self.assertNotIn("private", str(raised.exception))

    def test_timeout_is_safe(self) -> None:
        def timeout(_request):
            raise httpx.ReadTimeout("private transport detail")

        with self.assertRaisesRegex(SttCheckFailed, "timed out") as raised:
            self.run_response(handler=timeout)
        self.assertNotIn("private", str(raised.exception))

    def test_endpoint_matches_backend_url_join_and_refuses_credentials(self) -> None:
        self.assertEqual(endpoint("http://localhost:8200/", "/transcribe"), URL.replace("127.0.0.1", "localhost"))
        with self.assertRaises(SttCheckFailed):
            endpoint("http://user:secret@localhost:8200", "/transcribe")
        with self.assertRaises(SttCheckFailed):
            endpoint("http://localhost:8200", "relative")


if __name__ == "__main__":
    unittest.main()
