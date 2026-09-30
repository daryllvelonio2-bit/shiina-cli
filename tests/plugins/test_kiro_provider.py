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

    def test_pool_entry_without_base_url_keeps_provider_endpoint(self):
        """A local-store-seeded credential (token only, no endpoint — what
        ``_seed_kiro_singleton`` writes) must not blank the provider's base_url.

        The credential-pool rung sits above the external-process rung, so before this a
        logged-in Kiro account resolved to provider 'kiro' with an EMPTY base_url and the
        CLI died with \"Provider resolver returned an empty base URL\".
        """
        from agent.credential_pool import write_credential_pool

        write_credential_pool("kiro", [{
            "id": "kiro-test", "label": "Kiro (google)", "auth_type": "api_key",
            "priority": 0, "source": "sqlite", "access_token": "kiro-access-token",
        }])
        rt = resolve_runtime_provider(requested="kiro", target_model="claude-sonnet-4.5")
        self.assertEqual(rt["provider"], "kiro")
        self.assertEqual(rt["base_url"], "kiro://local")


if __name__ == "__main__":
    unittest.main()
