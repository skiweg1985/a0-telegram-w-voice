"""Regression tests for the tool-detail default level.

New chats and bots without an explicit ``telegram_detail_level`` should resolve
to ``info`` (throttled tool-step lines), while an explicitly configured ``off``
must still be respected. ``normalize_detail_level`` is the single source of this
behavior and has no plugin-namespace imports at module level, so it can be
loaded directly from its file path.
"""

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
