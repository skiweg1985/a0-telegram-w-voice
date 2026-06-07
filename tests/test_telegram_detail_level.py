"""Regression tests for the tool-detail default level.

New chats and bots without an explicit ``telegram_detail_level`` should resolve
to ``info`` (throttled tool-step lines), while an explicitly configured ``off``
must still be respected. ``normalize_detail_level`` is the single source of this
behavior and has no plugin-namespace imports at module level, so it can be
loaded directly from its file path.
"""

import importlib.util
import os
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DETAIL_STATUS_PATH = REPO_ROOT / "helpers" / "detail_status.py"


def _load_detail_status():
    spec = importlib.util.spec_from_file_location(
        "detail_status_under_test", DETAIL_STATUS_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NormalizeDetailLevelTests(unittest.TestCase):
    def setUp(self):
        self.ds = _load_detail_status()

    def test_missing_value_defaults_to_info(self):
        self.assertEqual(self.ds.normalize_detail_level(None), "info")

    def test_explicit_off_is_respected(self):
        self.assertEqual(self.ds.normalize_detail_level("off"), "off")

    def test_known_levels_pass_through(self):
        self.assertEqual(self.ds.normalize_detail_level("info"), "info")
        self.assertEqual(self.ds.normalize_detail_level("debug"), "debug")

    def test_verbose_alias_maps_to_debug(self):
        self.assertEqual(self.ds.normalize_detail_level("verbose"), "debug")

    def test_unknown_value_falls_back_to_off(self):
        self.assertEqual(self.ds.normalize_detail_level("nonsense"), "off")


class DetailStatusRedactionTests(unittest.TestCase):
    def setUp(self):
        self.ds = _load_detail_status()

    def test_debug_render_redacts_sensitive_keys(self):
        html = self.ds.format_step_html(
            "browser:navigate",
            {},
            level="debug",
            tool_args={
                "url": "https://example.com",
                "headers": {
                    "Authorization": "Bearer super-secret-token",
                    "x-api-key": "abcdef1234567890",
                },
                "password": "hunter2!secret",
            },
        )
        self.assertIn("[REDACTED]", html)
        self.assertNotIn("super-secret-token", html)
        self.assertNotIn("abcdef1234567890", html)
        self.assertNotIn("hunter2!secret", html)

    def test_known_agent_zero_secret_values_are_force_masked_in_free_text(self):
        os.environ["TEST_A0_SECRET"] = "ultra-secret-value-123"
        try:
            known = self.ds.collect_known_secret_values(
                {
                    "speech": {"api_key": "${TEST_A0_SECRET}"},
                    "webhook_secret": "hook-secret-987654",
                }
            )
            html = self.ds.format_step_html(
                "code_execution",
                {},
                level="debug",
                tool_args={
                    "code": (
                        "curl -H 'Authorization: Bearer ultra-secret-value-123' "
                        "https://user:hook-secret-987654@example.com && "
                        "A0_TOKEN=ultra-secret-value-123"
                    )
                },
                known_secret_values=known,
            )
        finally:
            os.environ.pop("TEST_A0_SECRET", None)

        self.assertIn("[REDACTED]", html)
        self.assertNotIn("ultra-secret-value-123", html)
        self.assertNotIn("hook-secret-987654", html)

    def test_basic_auth_is_redacted_in_free_text(self):
        html = self.ds.format_step_html(
            "code_execution",
            {},
            level="debug",
            tool_args={"command": "curl -u elastic:VerySecret123 https://example.com"},
        )
        self.assertIn("elastic:[REDACTED]", html)
        self.assertNotIn("VerySecret123", html)

    def test_non_json_serializable_fallback_keeps_sensitive_values_redacted(self):
        html = self.ds.format_step_html(
            "code_execution",
            {},
            level="debug",
            tool_args={
                "password": "FallbackSecret999",
                "command": "PASSWORD=FallbackSecret999 python3 -c 'print(1)'",
                "opaque": object(),
            },
        )
        self.assertIn("[REDACTED]", html)
        self.assertNotIn("FallbackSecret999", html)


if __name__ == "__main__":
    unittest.main()
