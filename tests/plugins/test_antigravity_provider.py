"""Tests for the natively-wired Antigravity provider (credentials + runtime resolution)."""

import unittest
from unittest.mock import patch

from providers import get_provider_profile
from shiina_cli.auth import OAUTH_PROVIDER_FLOWS, PROVIDER_REGISTRY, resolve_provider
from shiina_cli.auth_antigravity import get_antigravity_auth_status, resolve_antigravity_runtime_credentials
from shiina_cli.auth_constants import DEFAULT_ANTIGRAVITY_BASE_URL
from shiina_cli.runtime_provider import resolve_runtime_provider


class TestAntigravityProvider(unittest.TestCase):
    def test_provider_registration(self):
        profile = get_provider_profile("antigravity")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "antigravity")
        self.assertEqual(profile.auth_type, "oauth_external")
        self.assertEqual(profile.base_url, DEFAULT_ANTIGRAVITY_BASE_URL)
        self.assertIn("claude-opus-4-6-thinking", profile.fallback_models)
        self.assertIn("gemini-3.8-flash-tiered", profile.fallback_models)

    def test_auth_registry_is_native_oauth(self):
        self.assertIn("antigravity", PROVIDER_REGISTRY)
        pconfig = PROVIDER_REGISTRY["antigravity"]
        self.assertEqual(pconfig.auth_type, "oauth_external")
        self.assertEqual(pconfig.inference_base_url, DEFAULT_ANTIGRAVITY_BASE_URL)
        self.assertIn("antigravity", OAUTH_PROVIDER_FLOWS)
        self.assertEqual(resolve_provider("antigravity"), "antigravity")
        # Aliases still resolve through the plugin profile (resolve_provider's alias table).
        self.assertEqual(resolve_provider("agy"), "antigravity")
        self.assertEqual(resolve_provider("jetski"), "antigravity")

    def test_not_wired_through_the_agy_subprocess(self):
        """The whole point of native wiring: no external-process / subprocess credential path."""
        profile = get_provider_profile("antigravity")
        self.assertNotEqual(profile.auth_type, "external_process")
        self.assertEqual(profile.process_command, "")
        self.assertNotEqual(PROVIDER_REGISTRY["antigravity"].auth_type, "external_process")

    def test_runtime_resolution_targets_cloud_code_assist(self):
        creds = {
            "provider": "antigravity", "base_url": DEFAULT_ANTIGRAVITY_BASE_URL,
            "api_key": "fake-access-token", "source": "credential_pool", "expires_at": None,
        }
        # Neutralize the pool rung: this asserts the OAuth rung, and the machine running the test
        # may genuinely have an antigravity pool entry.
        with patch("shiina_cli.runtime_provider._resolve_from_pool", return_value=None), \
             patch("shiina_cli.runtime_provider.resolve_antigravity_runtime_credentials", return_value=creds):
            runtime = resolve_runtime_provider(requested="antigravity", target_model="gemini-3.8-flash-tiered")
        self.assertEqual(runtime["provider"], "antigravity")
        self.assertEqual(runtime["base_url"], DEFAULT_ANTIGRAVITY_BASE_URL)
        self.assertEqual(runtime["api_mode"], "chat_completions")
        self.assertEqual(runtime["api_key"], "fake-access-token")

    def test_missing_session_reports_logged_out_without_raising(self):
        with patch(
            "shiina_cli.auth_antigravity.resolve_antigravity_runtime_credentials",
            side_effect=RuntimeError("no session"),
        ):
            status = get_antigravity_auth_status()
        self.assertFalse(status["logged_in"])
        self.assertEqual(status["provider"], "antigravity")
        self.assertIn("pool_entries", status)

    def test_resolver_reports_the_credential_source(self):
        """The resolver surfaces where the session came from, for `shiina auth status`."""
        class _Manager:
            def get_access_token(self, force_refresh=False):
                return "tok"

            def source_label(self):
                return "keyring"

            def expiry_iso(self):
                return "2026-09-29T21:21:32+08:00"

        with patch("shiina_cli.auth_antigravity._token_manager", return_value=_Manager()):
            creds = resolve_antigravity_runtime_credentials()
        self.assertEqual(creds["provider"], "antigravity")
        self.assertEqual(creds["source"], "keyring")
        self.assertEqual(creds["api_key"], "tok")
        self.assertEqual(creds["base_url"], DEFAULT_ANTIGRAVITY_BASE_URL)


if __name__ == "__main__":
    unittest.main()
