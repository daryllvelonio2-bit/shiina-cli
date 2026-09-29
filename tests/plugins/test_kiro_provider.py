"""Tests for Kiro provider profile registration and runtime resolution."""

import unittest
from providers import get_provider_profile
from shiina_cli.auth import PROVIDER_REGISTRY, resolve_provider, resolve_external_process_provider_credentials
from shiina_cli.runtime_provider import resolve_runtime_provider


class TestKiroProvider(unittest.TestCase):
    def test_provider_registration(self):
        profile = get_provider_profile("kiro")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "kiro")
        self.assertEqual(profile.auth_type, "external_process")
        self.assertEqual(profile.base_url, "kiro://local")
        self.assertIn("claude-sonnet-4.5", profile.fallback_models)
        self.assertIn("deepseek-3.2", profile.fallback_models)

    def test_auth_registry(self):
        self.assertIn("kiro", PROVIDER_REGISTRY)
        self.assertEqual(PROVIDER_REGISTRY["kiro"].auth_type, "external_process")
        self.assertEqual(resolve_provider("kiro"), "kiro")
        self.assertEqual(resolve_provider("kiro-cli"), "kiro")

    def test_resolve_credentials(self):
        creds = resolve_external_process_provider_credentials("kiro")
        self.assertEqual(creds["provider"], "kiro")
        self.assertEqual(creds["base_url"], "kiro://local")
        self.assertEqual(creds["source"], "process")
        self.assertIn("kiro-cli", creds["command"])

    def test_resolve_runtime_provider(self):
        rt = resolve_runtime_provider(requested="kiro", target_model="claude-sonnet-4.5")
        self.assertEqual(rt["provider"], "kiro")
        self.assertEqual(rt["base_url"], "kiro://local")
        self.assertEqual(rt["api_mode"], "chat_completions")
        self.assertEqual(rt["source"], "process")


if __name__ == "__main__":
    unittest.main()
