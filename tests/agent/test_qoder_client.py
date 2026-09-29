"""Tests for QoderClient encoding, decoding, model resolution, and streaming logic."""

import unittest
from agent.qoder_client import (
    qoder_encode_body,
    qoder_decode_body,
    resolve_qoder_model,
    QoderClient,
)


class TestQoderClient(unittest.TestCase):
    def test_encode_decode_roundtrip(self):
        sample = b'{"messages": [{"role": "user", "content": "Hello Qoder!"}]}'
        encoded = qoder_encode_body(sample)
        decoded = qoder_decode_body(encoded.decode("utf-8"))
        self.assertEqual(decoded, sample)

    def test_model_resolution(self):
        self.assertEqual(resolve_qoder_model("qoder-qwen"), "qmodel_38max")
        self.assertEqual(resolve_qoder_model("qwen"), "qmodel_38max")
        self.assertEqual(resolve_qoder_model("qoder-flash"), "qfmodel")
        self.assertEqual(resolve_qoder_model("flash"), "qfmodel")
        self.assertEqual(resolve_qoder_model("qoder-deepseek"), "dmodel")
        self.assertEqual(resolve_qoder_model("qoder-sonus"), "smodel")
        self.assertEqual(resolve_qoder_model("qoder-cantus"), "cmodel")
        self.assertEqual(resolve_qoder_model("qoder-kimi"), "kmodel_latest")
        self.assertEqual(resolve_qoder_model("qoder-glm"), "gmodel")
        self.assertEqual(resolve_qoder_model("qoder-minimax"), "mmodel")
        self.assertEqual(resolve_qoder_model("Auto"), "auto")

    def test_client_attributes(self):
        client = QoderClient(api_key="pt-test-123")
        self.assertTrue(getattr(client, "SHIINA_SKIP_TRANSPORT_WRAP", False))
        self.assertTrue(getattr(client, "SHIINA_SKIP_ASYNC_WRAP", False))
        self.assertIsNotNone(client.chat.completions.create)

    def test_parse_qoder_queue_info(self):
        from agent.qoder_client import parse_qoder_queue_info

        # Direct 10605 envelope
        env1 = {
            "code": "10605",
            "message": '{"isQueued":true,"modelKey":"qfmodel","queueCount":0,"queueType":"p3","retryAfterSeconds":30,"serviceAvailable":false,"waitTime":30}'
        }
        is_q, wait_sec, q_type = parse_qoder_queue_info(env1)
        self.assertTrue(is_q)
        self.assertEqual(wait_sec, 30)
        self.assertEqual(q_type, "p3")

        # Nested 403 envelope
        env2 = {
            "code": "403",
            "message": '{"code":"10605","message":"{\\"isQueued\\":true,\\"modelKey\\":\\"qfmodel\\",\\"queueCount\\":0,\\"queueType\\":\\"p3\\",\\"retryAfterSeconds\\":25,\\"serviceAvailable\\":false,\\"waitTime\\":25}"}'
        }
        is_q, wait_sec, q_type = parse_qoder_queue_info(env2)
        self.assertTrue(is_q)
        self.assertEqual(wait_sec, 25)
        self.assertEqual(q_type, "p3")

        # Normal response
        env3 = {"code": "200", "choices": [{"delta": {"content": "hi"}}]}
        is_q, _, _ = parse_qoder_queue_info(env3)
        self.assertFalse(is_q)

    def test_report_queue_status_callback(self):
        reports = []
        client = QoderClient(api_key="pt-test-123", status_callback=lambda s: reports.append(s))
        client._report_queue_status("[Qoder] Model queued (3s)...")
        self.assertEqual(reports, ["[Qoder] Model queued (3s)..."])
        client._report_queue_status("")
        self.assertEqual(reports, ["[Qoder] Model queued (3s)...", ""])

    def test_report_queue_status_agent(self):
        class MockAgent:
            def __init__(self):
                self.notices = []
            def _emit_wait_notice(self, text: str):
                self.notices.append(text)

        agent = MockAgent()
        client = QoderClient(api_key="pt-test-123", agent=agent)
        client._report_queue_status("[Qoder] Model queued (5s)...")
        self.assertEqual(agent.notices, ["[Qoder] Model queued (5s)..."])
        client._report_queue_status("")
        self.assertEqual(agent.notices, ["[Qoder] Model queued (5s)...", ""])

    def test_report_queue_status_stdout_proxy_no_spam(self):
        import sys
        class StdoutProxy:
            def __init__(self):
                self.written = []
            def write(self, s):
                self.written.append(s)
            def flush(self):
                pass
            def isatty(self):
                return True

        fake_proxy = StdoutProxy()
        old_stdout = sys.stdout
        try:
            sys.stdout = fake_proxy
            client = QoderClient(api_key="pt-test-123")
            # Should NOT write to StdoutProxy (prevents terminal spam)
            client._report_queue_status("[Qoder] Model queued (10s)...")
            self.assertEqual(fake_proxy.written, [])
        finally:
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
