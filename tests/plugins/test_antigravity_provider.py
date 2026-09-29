"""Tests for Antigravity provider profile registration and runtime resolution."""

import unittest
from providers import get_provider_profile, list_providers
from shiina_cli.auth import PROVIDER_REGISTRY, resolve_provider, resolve_external_process_provider_credentials
from shiina_cli.runtime_provider import resolve_runtime_provider


class TestAntigravityProvider(unittest.TestCase):
    def test_provider_registration(self):
        profile = get_provider_profile("antigravity")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "antigravity")
        self.assertEqual(profile.auth_type, "external_process")
        self.assertEqual(profile.base_url, "agy://local")
        self.assertIn("claude-opus-4-6-thinking", profile.fallback_models)
        self.assertIn("gemini-3.8-flash-high", profile.fallback_models)

    def test_auth_registry(self):
        self.assertIn("antigravity", PROVIDER_REGISTRY)
        self.assertEqual(PROVIDER_REGISTRY["antigravity"].auth_type, "external_process")
        self.assertEqual(resolve_provider("antigravity"), "antigravity")
        self.assertEqual(resolve_provider("agy"), "antigravity")

    def test_resolve_credentials(self):
        creds = resolve_external_process_provider_credentials("antigravity")
        self.assertEqual(creds["provider"], "antigravity")
        self.assertEqual(creds["base_url"], "agy://local")
        self.assertEqual(creds["source"], "process")
        self.assertIn("agy", creds["command"])

    def test_resolve_runtime_provider(self):
        rt = resolve_runtime_provider(requested="antigravity", target_model="gemini-3.8-flash-high")
        self.assertEqual(rt["provider"], "antigravity")
        self.assertEqual(rt["base_url"], "agy://local")
        self.assertEqual(rt["api_mode"], "chat_completions")
        self.assertEqual(rt["source"], "process")


if __name__ == "__main__":
    unittest.main()
