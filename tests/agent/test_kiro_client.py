"""Unit tests for native KiroClient."""

import unittest
from unittest.mock import MagicMock, patch

from agent.kiro_client import (
    KiroClient,
    clean_kiro_output,
    ensure_shiina_agent_config,
    extract_thinking_from_text,
    format_messages_for_kiro,
    kiro_completion_to_stream_chunks,
    resolve_kiro_model,
)


class TestKiroClient(unittest.TestCase):
    def test_resolve_kiro_model(self):
        self.assertEqual(resolve_kiro_model("kiro-sonnet"), "claude-sonnet-4.5")
        self.assertEqual(resolve_kiro_model("sonnet"), "claude-sonnet-4.5")
        self.assertEqual(resolve_kiro_model("kiro-deepseek"), "deepseek-3.2")
        self.assertEqual(resolve_kiro_model("deepseek"), "deepseek-3.2")
        self.assertEqual(resolve_kiro_model("kiro-haiku"), "claude-haiku-4.5")
        self.assertEqual(resolve_kiro_model("kiro-qwen"), "qwen3-coder-next")
        self.assertEqual(resolve_kiro_model("kiro-minimax"), "minimax-m2.5")
        self.assertEqual(resolve_kiro_model("kiro/claude-sonnet-4.5"), "claude-sonnet-4.5")
        self.assertEqual(resolve_kiro_model("custom-model"), "custom-model")
        self.assertEqual(resolve_kiro_model(""), "claude-sonnet-4.5")

    def test_clean_kiro_output(self):
        raw = """WARNING: --trust-tools arg for custom tool needs to be prepended with @{MCPSERVERNAME}/

> Hello world! Here is the response.

 ▸ Credits: 0.05 • Time: 3s
"""
        cleaned = clean_kiro_output(raw)
        self.assertEqual(cleaned, "Hello world! Here is the response.")

    def test_clean_kiro_output_multiple_lines(self):
        raw = """> Line one
> Line two
>
> Line three

 ▸ Credits: 0.10 • Time: 1s"""
        cleaned = clean_kiro_output(raw)
        self.assertEqual(cleaned, "Line one\nLine two\n\nLine three")

    def test_extract_thinking_from_text(self):
        raw = "<thinking>\nStep 1: plan\nStep 2: execute\n</thinking>\nHere is the answer."
        thinking, text = extract_thinking_from_text(raw)
        self.assertEqual(thinking, "Step 1: plan\nStep 2: execute")
        self.assertEqual(text, "Here is the answer.")

        # Test case insensitive and thought tag
        raw_thought = "<thought>Reflecting deeply</thought>Done."
        thinking2, text2 = extract_thinking_from_text(raw_thought)
        self.assertEqual(thinking2, "Reflecting deeply")
        self.assertEqual(text2, "Done.")

        # Test without thinking
        raw_none = "Just plain text."
        thinking3, text3 = extract_thinking_from_text(raw_none)
        self.assertIsNone(thinking3)
        self.assertEqual(text3, "Just plain text.")

    def test_format_messages_with_tools_and_reasoning(self):
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read contents",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                },
            }
        ]
        msgs = [
            {"role": "user", "content": "Please read test.txt"},
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "Planning to read file",
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{\"path\": \"test.txt\"}"},
                    }
                ],
            },
            {"role": "tool", "name": "read_file", "tool_call_id": "call_abc", "content": "File data 123"},
        ]
        prompt = format_messages_for_kiro(msgs, tools=tools)
        self.assertIn("read_file", prompt)
        self.assertIn("Available tools", prompt)
        self.assertIn("[User]\nPlease read test.txt", prompt)
        self.assertIn("<thinking>\nPlanning to read file\n</thinking>", prompt)
        self.assertIn('<tool_call>{"id": "call_abc"', prompt)
        self.assertIn("[Tool Result (read_file id=call_abc)]\nFile data 123", prompt)

    @patch("agent.kiro_client.subprocess.run")
    def test_create_chat_completion_with_thinking_and_tool_call(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = """
> <thinking>
Analyzing request to read file.
</thinking>

<tool_call>{"id": "call_99", "type": "function", "function": {"name": "read_file", "arguments": "{\\"path\\": \\"/tmp/test.txt\\"}"}}</tool_call>

 ▸ Credits: 0.05 • Time: 2s
"""
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        client = KiroClient()
        res = client.chat.completions.create(
            model="kiro-sonnet",
            messages=[{"role": "user", "content": "Read /tmp/test.txt"}],
            tools=[{"type": "function", "function": {"name": "read_file"}}],
            stream=False,
        )

        msg = res.choices[0].message
        self.assertEqual(res.choices[0].finish_reason, "tool_calls")
        self.assertEqual(msg.reasoning_content, "Analyzing request to read file.")
        self.assertEqual(msg.reasoning, "Analyzing request to read file.")
        self.assertIsNotNone(msg.tool_calls)
        self.assertEqual(len(msg.tool_calls), 1)
        self.assertEqual(msg.tool_calls[0].id, "call_99")
        self.assertEqual(msg.tool_calls[0].function.name, "read_file")
        self.assertEqual(msg.tool_calls[0].function.arguments, '{"path": "/tmp/test.txt"}')

    @patch("agent.kiro_client.subprocess.run")
    def test_create_chat_completion_streaming(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = """
> <thinking>
Deep thought here.
</thinking>

Here is the final answer.

 ▸ Credits: 0.05 • Time: 2s
"""
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        client = KiroClient()
        chunks = client.chat.completions.create(
            model="kiro-sonnet",
            messages=[{"role": "user", "content": "Hi"}],
            stream=True,
        )

        # Stage 1: Reasoning chunk
        self.assertEqual(chunks[0].choices[0].delta.reasoning_content, "Deep thought here.")
        # Stage 2: Content chunk
        self.assertEqual(chunks[1].choices[0].delta.content, "Here is the final answer.")
        # Stage 3: Finish reason chunk
        self.assertEqual(chunks[2].choices[0].finish_reason, "stop")


if __name__ == "__main__":
    unittest.main()
