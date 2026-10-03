"""Unit tests for native OpenCodeClient."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.opencode_client import (
    OpenCodeClient,
    _format_messages_for_prompt,
    check_opencode_credentials,
    fetch_opencode_models,
    find_opencode_binary,
    get_opencode_credentials,
)


class TestOpenCodeClient(unittest.TestCase):
    def test_format_messages_for_prompt(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
            {"role": "user", "content": [{"type": "text", "text": "Explain further."}]},
        ]
        prompt = _format_messages_for_prompt(messages)
        self.assertIn("[System Instruction]\nYou are a helpful assistant.", prompt)
        self.assertIn("[User]\nWhat is Python?", prompt)
        self.assertIn("[Assistant]\nPython is a programming language.", prompt)
        self.assertIn("[User]\nExplain further.", prompt)

    @patch("agent.opencode_client.shutil.which")
    def test_find_opencode_binary(self, mock_which):
        mock_which.return_value = "/usr/local/bin/opencode"
        self.assertEqual(find_opencode_binary(), "/usr/local/bin/opencode")

    @patch("agent.opencode_client.get_opencode_credentials")
    @patch("agent.opencode_client.find_opencode_binary")
    def test_check_opencode_credentials(self, mock_bin, mock_creds):
        mock_creds.return_value = {"groq": {"key": "123"}}
        authed, note = check_opencode_credentials()
        self.assertTrue(authed)
        self.assertIn("groq", note)

        mock_creds.return_value = {}
        mock_bin.return_value = "/usr/bin/opencode"
        authed2, note2 = check_opencode_credentials()
        self.assertTrue(authed2)
        self.assertIn("opencode", note2)

    @patch("agent.opencode_client.subprocess.run")
    @patch("agent.opencode_client.find_opencode_binary")
    def test_fetch_opencode_models(self, mock_bin, mock_run):
        mock_bin.return_value = "/usr/bin/opencode"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "opencode/big-pickle\nopencode/space-bunny-free\ngroq/llama-3\n"
        mock_run.return_value = mock_proc

        models = fetch_opencode_models()
        self.assertEqual(models, ["opencode/big-pickle", "opencode/space-bunny-free", "groq/llama-3"])

    @patch("agent.opencode_client.subprocess.Popen")
    @patch("agent.opencode_client.find_opencode_binary")
    def test_client_execute_sync(self, mock_bin, mock_popen):
        mock_bin.return_value = "/usr/bin/opencode"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        json_output = "\n".join([
            json.dumps({"type": "step_start", "sessionID": "ses_123"}),
            json.dumps({"type": "reasoning", "part": {"text": "Thinking..."}}),
            json.dumps({"type": "text", "part": {"text": "Hello world!"}}),
            json.dumps({"type": "step_finish", "part": {"reason": "stop", "tokens": {"input": 10, "output": 5, "total": 15}}}),
        ])
        mock_proc.communicate.return_value = (json_output, "")
        mock_popen.return_value = mock_proc

        client = OpenCodeClient()
        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": "Hi"}],
            model="opencode/big-pickle",
            stream=False,
        )

        self.assertEqual(resp.choices[0].message.content, "Hello world!")
        self.assertEqual(resp.choices[0].message.reasoning_content, "Thinking...")
        self.assertEqual(resp.choices[0].finish_reason, "stop")
        self.assertEqual(resp.usage.total_tokens, 15)

    @patch("agent.opencode_client.subprocess.Popen")
    @patch("agent.opencode_client.find_opencode_binary")
    def test_client_execute_stream(self, mock_bin, mock_popen):
        mock_bin.return_value = "/usr/bin/opencode"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.poll.return_value = 0
        lines = [
            json.dumps({"type": "step_start", "sessionID": "ses_123"}) + "\n",
            json.dumps({"type": "reasoning", "part": {"text": "Thinking..."}}) + "\n",
            json.dumps({"type": "text", "part": {"text": "Hello stream!"}}) + "\n",
            json.dumps({"type": "step_finish", "part": {"reason": "stop"}}) + "\n",
        ]
        mock_proc.stdout = iter(lines)
        mock_popen.return_value = mock_proc

        client = OpenCodeClient()
        chunks = list(client.chat.completions.create(
            messages=[{"role": "user", "content": "Hi"}],
            model="opencode/big-pickle",
            stream=True,
        ))

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0].choices[0].delta.reasoning_content, "Thinking...")
        self.assertEqual(chunks[1].choices[0].delta.content, "Hello stream!")
        self.assertEqual(chunks[2].choices[0].finish_reason, "stop")

    @patch("agent.opencode_client.subprocess.Popen")
    @patch("agent.opencode_client.find_opencode_binary")
    def test_client_execute_sync_parses_tool_use(self, mock_bin, mock_popen):
        mock_bin.return_value = "/usr/bin/opencode"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        tool_use = {
            "type": "tool_use",
            "part": {
                "type": "tool",
                "tool": "bash",
                "state": {
                    "status": "completed",
                    "input": {"command": "echo TOOLCHECK_12345"},
                    "output": "TOOLCHECK_12345\n",
                },
            },
        }
        json_output = "\n".join([
            json.dumps({"type": "step_start", "sessionID": "ses_123"}),
            json.dumps(tool_use),
            json.dumps({"type": "step_finish", "part": {"reason": "tool-calls"}}),
        ])
        mock_proc.communicate.return_value = (json_output, "")
        mock_popen.return_value = mock_proc

        resp = OpenCodeClient().chat.completions.create(
            messages=[{"role": "user", "content": "run it"}],
            model="opencode/big-pickle",
            stream=False,
        )

        content = resp.choices[0].message.content
        self.assertTrue(content, "a completed tool_use must make the turn non-empty")
        self.assertIn("bash", content)
        self.assertIn("TOOLCHECK_12345", content)
        self.assertEqual(resp.choices[0].finish_reason, "tool-calls")

    @patch("agent.opencode_client._opencode_version")
    @patch("agent.opencode_client.subprocess.Popen")
    @patch("agent.opencode_client.find_opencode_binary")
    def test_client_execute_sync_hollow_tool_calls_raises(self, mock_bin, mock_popen, mock_ver):
        mock_ver.return_value = "9.9.9"
        mock_bin.return_value = "/usr/bin/opencode"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        json_output = "\n".join([
            json.dumps({"type": "step_start", "sessionID": "ses_123"}),
            json.dumps({"type": "step_finish", "part": {"reason": "tool-calls"}}),
        ])
        mock_proc.communicate.return_value = (json_output, "")
        mock_popen.return_value = mock_proc

        with self.assertRaises(RuntimeError) as ctx:
            OpenCodeClient().chat.completions.create(
                messages=[{"role": "user", "content": "run it"}],
                model="opencode/big-pickle",
                stream=False,
            )
        self.assertIn("big-pickle", str(ctx.exception))
        self.assertIn("9.9.9", str(ctx.exception))

    @patch("agent.opencode_client._opencode_version")
    @patch("agent.opencode_client.subprocess.Popen")
    @patch("agent.opencode_client.find_opencode_binary")
    def test_client_execute_sync_tool_calls_never_lets_no_tool_use_through(self, mock_bin, mock_popen, mock_ver):
        mock_ver.return_value = "9.9.9"
        mock_bin.return_value = "/usr/bin/opencode"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        json_output = "\n".join([
            json.dumps({"type": "text", "part": {"text": "I will run the tool."}}),
            json.dumps({"type": "step_finish", "part": {"reason": "tool-calls"}}),
        ])
        mock_proc.communicate.return_value = (json_output, "")
        mock_popen.return_value = mock_proc

        with self.assertRaises(RuntimeError):
            OpenCodeClient().chat.completions.create(
                messages=[{"role": "user", "content": "run it"}],
                model="opencode/big-pickle",
                stream=False,
            )

    @patch("agent.opencode_client.subprocess.Popen")
    @patch("agent.opencode_client.find_opencode_binary")
    def test_client_execute_stream_parses_tool_use(self, mock_bin, mock_popen):
        mock_bin.return_value = "/usr/bin/opencode"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.poll.return_value = 0
        lines = [
            json.dumps({"type": "tool_use", "part": {
                "type": "tool",
                "tool": "bash",
                "state": {
                    "status": "completed",
                    "input": {"command": "echo TOOLCHECK_12345"},
                    "output": "TOOLCHECK_12345\n",
                },
            }}) + "\n",
            json.dumps({"type": "step_finish", "part": {"reason": "tool-calls"}}) + "\n",
        ]
        mock_proc.stdout = iter(lines)
        mock_popen.return_value = mock_proc

        chunks = list(OpenCodeClient().chat.completions.create(
            messages=[{"role": "user", "content": "run it"}],
            model="opencode/big-pickle",
            stream=True,
        ))

        contents = "".join(c.choices[0].delta.content or "" for c in chunks)
        self.assertIn("TOOLCHECK_12345", contents)

    @patch("agent.opencode_client._opencode_version")
    @patch("agent.opencode_client.subprocess.Popen")
    @patch("agent.opencode_client.find_opencode_binary")
    def test_client_execute_stream_hollow_tool_calls_raises(self, mock_bin, mock_popen, mock_ver):
        mock_ver.return_value = "9.9.9"
        mock_bin.return_value = "/usr/bin/opencode"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.poll.return_value = 0
        mock_proc.stdout = iter([
            json.dumps({"type": "step_finish", "part": {"reason": "tool-calls"}}) + "\n",
        ])
        mock_popen.return_value = mock_proc

        with self.assertRaises(RuntimeError):
            list(OpenCodeClient().chat.completions.create(
                messages=[{"role": "user", "content": "run it"}],
                model="opencode/big-pickle",
                stream=True,
            ))

    def _bridge_env(self):
        home = tempfile.mkdtemp(prefix="shiina-home-")
        self.addCleanup(os.rmdir, home)
        self._bridge_home = home
        return patch.dict(os.environ, {"SHIINA_OPENCODE_MCP": "1", "SHIINA_HOME": home}, clear=False)

    @patch("agent.opencode_client.subprocess.Popen")
    @patch("agent.opencode_client.find_opencode_binary")
    def test_create_completion_injects_opencode_config_when_mcp_enabled(self, mock_bin, mock_popen):
        mock_bin.return_value = "/usr/bin/opencode"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (
            json.dumps({"type": "step_finish", "part": {"reason": "stop"}}), "")
        seen = {}

        def _capture(cmd, **kwargs):
            seen["env"] = kwargs.get("env") or {}
            cfg_path = seen["env"].get("OPENCODE_CONFIG")
            seen["cfg_path"] = cfg_path
            if cfg_path:
                seen["cfg_existed_at_spawn"] = Path(cfg_path).is_file()
                seen["cfg"] = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
            return mock_proc

        mock_popen.side_effect = _capture

        with self._bridge_env():
            OpenCodeClient().chat.completions.create(
                messages=[{"role": "user", "content": "Hi"}],
                model="opencode/big-pickle",
                stream=False,
            )

        self.assertIn("OPENCODE_CONFIG", seen["env"], "OPENCODE_CONFIG must be set when the bridge is on")
        self.assertTrue(seen["cfg_existed_at_spawn"], "config must exist when the child is spawned")
        entry = seen["cfg"]["mcp"]["shiina-tools"]
        self.assertEqual(entry["type"], "local")
        self.assertEqual(entry["environment"]["SHIINA_HOME"], self._bridge_home)
        self.assertFalse(
            Path(seen["cfg_path"]).exists(), "config file must be removed once the child exits")

    @patch("agent.opencode_client.subprocess.Popen")
    @patch("agent.opencode_client.find_opencode_binary")
    def test_create_completion_stream_injects_opencode_config_when_mcp_enabled(self, mock_bin, mock_popen):
        mock_bin.return_value = "/usr/bin/opencode"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.poll.return_value = 0
        mock_proc.stdout = iter([
            json.dumps({"type": "step_finish", "part": {"reason": "stop"}}) + "\n",
        ])
        seen = {}

        def _capture(cmd, **kwargs):
            seen["env"] = kwargs.get("env") or {}
            cfg_path = seen["env"].get("OPENCODE_CONFIG")
            seen["cfg_path"] = cfg_path
            if cfg_path:
                seen["cfg"] = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
            return mock_proc

        mock_popen.side_effect = _capture

        with self._bridge_env():
            list(OpenCodeClient().chat.completions.create(
                messages=[{"role": "user", "content": "Hi"}],
                model="opencode/big-pickle",
                stream=True,
            ))

        self.assertIn("OPENCODE_CONFIG", seen["env"])
        self.assertIn("shiina-tools", seen["cfg"]["mcp"])
        self.assertFalse(
            Path(seen["cfg_path"]).exists(), "config file must be removed once the child exits")

    @patch("agent.opencode_client.subprocess.Popen")
    @patch("agent.opencode_client.find_opencode_binary")
    def test_create_completion_skips_opencode_config_when_mcp_kill_switch(self, mock_bin, mock_popen):
        mock_bin.return_value = "/usr/bin/opencode"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (
            json.dumps({"type": "step_finish", "part": {"reason": "stop"}}), "")
        mock_popen.return_value = mock_proc

        with patch.dict(os.environ, {"SHIINA_OPENCODE_MCP": "0"}, clear=False):
            OpenCodeClient().chat.completions.create(
                messages=[{"role": "user", "content": "Hi"}],
                model="opencode/big-pickle",
                stream=False,
            )

        self.assertIsNone(
            mock_popen.call_args.kwargs.get("env"),
            "SHIINA_OPENCODE_MCP=0 must leave the child env inherited (today's behaviour)")


if __name__ == "__main__":
    unittest.main()
