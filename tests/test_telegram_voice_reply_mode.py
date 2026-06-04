"""Tests for the unified voice reply config mapping in speech.py.

``voice_reply_settings`` must accept the unified WebUI values
(off | auto | voice_only | voice_text | text_only) and the legacy split form
(voice_mode off|auto|force plus a separate also_send_text flag), so configs
written before the /voice consolidation keep working unchanged.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEECH_PATH = REPO_ROOT / "helpers" / "speech.py"


def _load_speech():
    if "helpers" not in sys.modules:
        helpers_pkg = types.ModuleType("helpers")
        helpers_pkg.__path__ = []
        sys.modules["helpers"] = helpers_pkg

    print_style = types.ModuleType("helpers.print_style")

    class _PrintStyle:
        @staticmethod
        def warning(*args, **kwargs):
            return None

    print_style.PrintStyle = _PrintStyle
    sys.modules["helpers.print_style"] = print_style

    spec = importlib.util.spec_from_file_location("speech_under_test", SPEECH_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bot(reply):
    return {"speech": {"reply": reply}}


class VoiceReplySettingsTests(unittest.TestCase):
    def setUp(self):
        self.speech = _load_speech()

    def test_unified_voice_only(self):
        s = self.speech.voice_reply_settings(_bot({"voice_mode": "voice_only"}))
        self.assertEqual(s["voice_mode"], "force")
        self.assertFalse(s["also_send_text"])

    def test_unified_voice_text(self):
        s = self.speech.voice_reply_settings(_bot({"voice_mode": "voice_text"}))
        self.assertEqual(s["voice_mode"], "force")
        self.assertTrue(s["also_send_text"])

    def test_unified_text_only(self):
        s = self.speech.voice_reply_settings(_bot({"voice_mode": "text_only"}))
        self.assertEqual(s["voice_mode"], "off")
        self.assertTrue(s["also_send_text"])

    def test_legacy_force_with_also_text_flag(self):
        s = self.speech.voice_reply_settings(
            _bot({"voice_mode": "force", "also_send_text": False})
        )
        self.assertEqual(s["voice_mode"], "force")
        self.assertFalse(s["also_send_text"])

    def test_auto_keeps_also_text_default(self):
        s = self.speech.voice_reply_settings(_bot({"voice_mode": "auto"}))
        self.assertEqual(s["voice_mode"], "auto")
        self.assertTrue(s["also_send_text"])

    def test_missing_defaults_to_off(self):
        s = self.speech.voice_reply_settings({})
        self.assertEqual(s["voice_mode"], "off")


if __name__ == "__main__":
    unittest.main()
