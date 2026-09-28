import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.insight_provider import generate


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, *args):
        return json.dumps(self.payload).encode()


class ProviderTests(unittest.TestCase):
    def test_http_diagnostics_keep_only_allowlisted_codes(self):
        body = {
            "error": {
                "status": "INVALID_ARGUMENT",
                "message": "API key not valid: secret-value",
                "details": [{"reason": "API_KEY_INVALID", "metadata": {"key": "secret-value"}}],
            }
        }
        error = HTTPError(
            "https://example.test/?key=secret-value",
            400,
            "secret-value",
            {},
            io.BytesIO(json.dumps(body).encode()),
        )
        with (
            patch("scripts.insight_provider.urlopen", side_effect=error),
            self.assertRaises(HTTPError) as caught,
        ):
            generate({}, "prompt", "gemini", "test", "secret-value")
        self.assertEqual(
            {"http_status": 400, "api_status": "INVALID_ARGUMENT", "reason": "API_KEY_INVALID"},
            caught.exception.diagnostics,
        )
        self.assertNotIn("secret-value", str(caught.exception))
        self.assertEqual("", caught.exception.url)

    def test_unrecognized_http_body_is_not_exposed(self):
        error = HTTPError("https://example.test", 403, "denied", {}, io.BytesIO(b"private response"))
        with (
            patch("scripts.insight_provider.urlopen", side_effect=error),
            self.assertRaises(HTTPError) as caught,
        ):
            generate({}, "prompt", "gemini", "test", "secret")
        self.assertEqual({"http_status": 403}, caught.exception.diagnostics)

    def test_gemini_requests_schema_and_ignores_thought_parts(self):
        def respond(request, **kwargs):
            self.assertNotIn("secret", request.full_url)
            self.assertEqual("secret", request.get_header("X-goog-api-key"))
            self.assertIn("responseJsonSchema", json.loads(request.data)["generationConfig"])
            return Response(
                {
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {
                                "parts": [
                                    {"text": "private reasoning", "thought": True},
                                    {"text": '{"ok": true}'},
                                ]
                            },
                        }
                    ]
                }
            )

        with patch("scripts.insight_provider.urlopen", side_effect=respond):
            self.assertEqual({"ok": True}, generate({}, "prompt", "gemini", "test", "secret"))

    def test_retryable_failure_recovers_but_auth_failure_is_not_retried(self):
        response = Response(
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}]}
        )
        calls = []

        def temporary(request, **kwargs):
            calls.append(request)
            if len(calls) == 1:
                raise HTTPError(request.full_url, 429, "rate limit", {}, None)
            return response

        with (
            patch("scripts.insight_provider.urlopen", side_effect=temporary),
            patch("scripts.insight_provider.time.sleep"),
        ):
            self.assertEqual({}, generate({}, "prompt", "gemini", "test", "secret"))

        def denied(request, **kwargs):
            raise HTTPError(request.full_url, 401, "auth", {}, None)

        with patch("scripts.insight_provider.urlopen", side_effect=denied), self.assertRaises(HTTPError):
            generate({}, "prompt", "gemini", "test", "secret")

    def test_truncated_generation_is_rejected(self):
        response = Response(
            {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{}"}]}}]}
        )
        with patch("scripts.insight_provider.urlopen", return_value=response), self.assertRaises(ValueError):
            generate({}, "prompt", "gemini", "test", "secret")
