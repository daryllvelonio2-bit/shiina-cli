"""Unit tests for native AntigravityClient."""

import json
import unittest
from unittest.mock import MagicMock, patch

from agent.antigravity_client import (
    AntigravityClient,
    resolve_agy_model,
)


class TestAntigravityClient(unittest.TestCase):
    def test_resolve_agy_model(self):
        self.assertEqual(resolve_agy_model("agy-opus"), "claude-opus-4-6-thinking")
        self.assertEqual(resolve_agy_model("agy-sonnet"), "claude-sonnet-4-6")
        self.assertEqual(resolve_agy_model("agy-pro"), "gemini-pro-agent")
        self.assertEqual(resolve_agy_model("agy-flash"), "gemini-3.8-flash-tiered")
        self.assertEqual(resolve_agy_model("antigravity/claude-opus-4-6-thinking"), "claude-opus-4-6-thinking")
        self.assertEqual(resolve_agy_model("agy/gemini-3.8-flash-high"), "gemini-3.8-flash-tiered")
        self.assertEqual(resolve_agy_model("custom-model"), "custom-model")
        self.assertEqual(resolve_agy_model(""), "gemini-3.8-flash-tiered")

    def test_claude_max_output_tokens_ceiling(self):
        client = AntigravityClient()
        payload = client._build_request_payload(
            resolved_model="claude-sonnet-4-6",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=65535,
        )
        self.assertLessEqual(payload["request"]["generationConfig"]["maxOutputTokens"], 8192)

    def test_gpt_oss_max_output_tokens_ceiling(self):
        client = AntigravityClient()
        payload = client._build_request_payload(
            resolved_model="gpt-oss-120b-medium",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=65535,
        )
        self.assertLessEqual(payload["request"]["generationConfig"]["maxOutputTokens"], 32768)

    def test_claude_tool_schema_anyof_to_oneof(self):
        client = AntigravityClient()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "choice": {
                                "anyOf": [{"type": "string"}, {"type": "number"}]
                            }
                        }
                    }
                }
            }
        ]
        payload = client._build_request_payload(
            resolved_model="claude-sonnet-4-6",
            messages=[{"role": "user", "content": "Hello"}],
            tools=tools,
        )
        tool_json = json.dumps(payload["request"]["tools"])
        self.assertNotIn('"anyOf"', tool_json)
        self.assertIn('"oneOf"', tool_json)

    def test_iter_events_text_and_finish_reason(self):
        client = AntigravityClient()
        fake_sse_lines = [
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "Hello "}]}}]}}',
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "world!"}]}, "finishReason": "STOP"}]}}',
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = fake_sse_lines
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with patch.object(client._http_client, "stream", return_value=mock_resp), \
             patch.object(client.token_manager, "get_access_token", return_value="fake_token"):
            events = list(client._iter_events({}, timeout_seconds=10))

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["response"]["candidates"][0]["content"]["parts"][0]["text"], "Hello ")
        self.assertEqual(events[1]["response"]["candidates"][0]["content"]["parts"][0]["text"], "world!")

    def test_stream_realtime_chunks(self):
        client = AntigravityClient()
        fake_sse_lines = [
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "Hello "}]}}]}}',
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "world!"}]}, "finishReason": "STOP"}]}}',
            'data: {"response": {"usageMetadata": {"promptTokenCount": 25, "candidatesTokenCount": 2, "totalTokenCount": 27}}}',
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = fake_sse_lines
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with patch.object(client._http_client, "stream", return_value=mock_resp), \
             patch.object(client.token_manager, "get_access_token", return_value="fake_token"):
            stream_chunks = list(
                client.chat.completions.create(
                    model="claude-sonnet-4-6",
                    messages=[{"role": "user", "content": "Hi"}],
                    stream=True,
                )
            )

        text_pieces = [
            chunk.choices[0].delta.content
            for chunk in stream_chunks
            if chunk.choices and getattr(chunk.choices[0].delta, "content", None)
        ]
        self.assertEqual(text_pieces, ["Hello ", "world!"])
        finish_reasons = [
            chunk.choices[0].finish_reason
            for chunk in stream_chunks
            if chunk.choices and getattr(chunk.choices[0], "finish_reason", None)
        ]
        self.assertIn("stop", finish_reasons)
        usage_chunks = [chunk for chunk in stream_chunks if getattr(chunk, "usage", None) is not None]
        self.assertEqual(len(usage_chunks), 1)
        self.assertEqual(usage_chunks[0].usage.prompt_tokens, 25)
        self.assertEqual(usage_chunks[0].usage.completion_tokens, 2)
        self.assertEqual(usage_chunks[0].usage.total_tokens, 27)


if __name__ == "__main__":
    unittest.main()
