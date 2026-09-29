"""Tests for Qoder provider profile registration, credential resolution, and client creation."""

import unittest
from providers import get_provider_profile
from shiina_cli.auth import PROVIDER_REGISTRY, resolve_provider, resolve_api_key_provider_credentials
from shiina_cli.runtime_provider import resolve_runtime_provider


class TestQoderProvider(unittest.TestCase):
    def test_provider_registration(self):
        profile = get_provider_profile("qoder")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "qoder")
        self.assertEqual(profile.auth_type, "api_key")
        self.assertEqual(profile.base_url, "https://api2.qoder.sh")
        self.assertIn("Qwen3.8-Max", profile.fallback_models)
        self.assertIn("Qwen3.8-Flash", profile.fallback_models)
        self.assertIn("Sonus", profile.fallback_models)

    def test_auth_registry(self):
        self.assertIn("qoder", PROVIDER_REGISTRY)
        self.assertEqual(PROVIDER_REGISTRY["qoder"].auth_type, "api_key")
        self.assertEqual(resolve_provider("qoder"), "qoder")
        self.assertEqual(resolve_provider("qoder-ai"), "qoder")
        self.assertEqual(resolve_provider("qoder.com"), "qoder")

    def test_resolve_runtime_provider(self):
        rt = resolve_runtime_provider(requested="qoder", target_model="Qwen3.8-Max")
        self.assertEqual(rt["provider"], "qoder")
        self.assertEqual(rt["base_url"], "https://api2.qoder.sh")
        self.assertEqual(rt["api_mode"], "chat_completions")


if __name__ == "__main__":
    unittest.main()
