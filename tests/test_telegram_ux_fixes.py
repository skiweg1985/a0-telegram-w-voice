"""Tests for the UI/UX fixes batch.

Covers:
- HTML-tag-aware message splitting (no unbalanced tags at the 4096 boundary)
- entity decoding in the plain-text parse-error fallback
- sentence-boundary TTS truncation (``speech.truncate_for_tts``)
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = REPO_ROOT / "helpers" / "telegram_client.py"
SPEECH_PATH = REPO_ROOT / "helpers" / "speech.py"


def _install_stub_helpers():
    aiogram = types.ModuleType("aiogram")
    aiogram.Bot = object
    sys.modules["aiogram"] = aiogram

    aiogram_exceptions = types.ModuleType("aiogram.exceptions")

    class TelegramBadRequest(Exception):
        pass

    class TelegramRetryAfter(Exception):
        def __init__(self, *args, retry_after=0, **kwargs):
            super().__init__(*args)
            self.retry_after = retry_after

    aiogram_exceptions.TelegramBadRequest = TelegramBadRequest
    aiogram_exceptions.TelegramRetryAfter = TelegramRetryAfter
    sys.modules["aiogram.exceptions"] = aiogram_exceptions

    aiogram_types = types.ModuleType("aiogram.types")

    class _DummyInline:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    aiogram_types.FSInputFile = _DummyInline
    aiogram_types.CopyTextButton = _DummyInline
    aiogram_types.InlineKeyboardButton = _DummyInline
    aiogram_types.InlineKeyboardMarkup = _DummyInline
    aiogram_types.InputMediaDocument = _DummyInline
    aiogram_types.InputMediaPhoto = _DummyInline
    aiogram_types.InputMediaVideo = _DummyInline

    class _DummyReaction:
        def __init__(self, emoji=""):
            self.emoji = emoji

    aiogram_types.ReactionTypeEmoji = _DummyReaction
    sys.modules["aiogram.types"] = aiogram_types

    helpers = types.ModuleType("helpers")
    helpers.__path__ = []
    sys.modules["helpers"] = helpers

    errors = types.ModuleType("helpers.errors")
    errors.format_error = lambda e: str(e)
    sys.modules["helpers.errors"] = errors

    print_style = types.ModuleType("helpers.print_style")

    class _PrintStyle:
        @staticmethod
        def warning(*a, **k):
            pass

        @staticmethod
        def error(*a, **k):
            pass

        @staticmethod
        def info(*a, **k):
            pass

    print_style.PrintStyle = _PrintStyle
    sys.modules["helpers.print_style"] = print_style


def _load_client():
    _install_stub_helpers()
    spec = importlib.util.spec_from_file_location("telegram_ux_client_under_test", CLIENT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_speech():
    _install_stub_helpers()
    spec = importlib.util.spec_from_file_location("telegram_ux_speech_under_test", SPEECH_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _tag_balance(chunk: str, name: str) -> int:
    return chunk.count(f"<{name}") - chunk.count(f"</{name}>")


class SplitTextHtmlAwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = _load_client()

    def test_short_text_untouched(self):
        self.assertEqual(self.client._split_text("hello", 4096), ["hello"])

    def test_plain_text_content_preserved(self):
        text = "\n".join(f"line {i} " + "x" * 60 for i in range(300))
        chunks = self.client._split_text(text, 4096)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 4096)
        self.assertEqual("\n".join(chunks).replace("\n", ""), text.replace("\n", ""))

    def test_pre_block_across_boundary_keeps_tags_balanced(self):
        code_body = "\n".join(f"print({i})  # padding padding padding" for i in range(200))
        text = "Intro line\n<pre>" + code_body + "</pre>\nOutro line"
        chunks = self.client._split_text(text, 4096)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 4096)
            self.assertEqual(_tag_balance(chunk, "pre"), 0, f"unbalanced <pre> in chunk: {chunk[:80]}…")

    def test_nested_tags_reopened_with_attributes(self):
        body = "word " * 2000
        text = '<pre><code class="language-python">' + body + "</code></pre>"
        chunks = self.client._split_text(text, 4096)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertEqual(_tag_balance(chunk, "pre"), 0)
            self.assertEqual(_tag_balance(chunk, "code"), 0)
        # The re-opened tag must keep its attributes so highlighting survives.
        self.assertIn('<code class="language-python">', chunks[1])

    def test_cut_never_lands_inside_a_tag(self):
        # A long run without newlines forces a hard cut; place tags around the
        # boundary region so a naive cut would land inside one.
        text = ("a" * 4000) + "<b>" + ("b" * 500) + "</b>" + ("c" * 500)
        chunks = self.client._split_text(text, 4096)
        for chunk in chunks:
            self.assertNotRegex(chunk, r"<[^>]*$")
            self.assertEqual(_tag_balance(chunk, "b"), 0)

    def test_strip_html_to_plain_decodes_entities(self):
        plain = self.client.strip_html_to_plain("<b>x &lt;= y &amp;&amp; a &gt; b</b>")
        self.assertEqual(plain, "x <= y && a > b")


class EffectiveRichEnabledTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = _load_client()

    def test_defaults_to_bot_config(self):
        self.assertFalse(self.client.effective_rich_enabled({}, {}))
        self.assertTrue(
            self.client.effective_rich_enabled({"rich_messages": {"enabled": True}}, {})
        )

    def test_session_override_wins_both_ways(self):
        cfg_on = {"rich_messages": {"enabled": True}}
        self.assertFalse(
            self.client.effective_rich_enabled(cfg_on, {"telegram_rich_messages_session": "off"})
        )
        self.assertTrue(
            self.client.effective_rich_enabled({}, {"telegram_rich_messages_session": "on"})
        )


class CopyTextKeyboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = _load_client()

    def test_build_inline_keyboard_supports_copy_text(self):
        markup = self.client.build_inline_keyboard([
            [
                {"text": "Copy", "copy_text": "git status"},
                {"text": "More", "callback_data": "m"},
            ],
            [{"text": "Docs", "url": "https://example.test"}],
        ])
        rows = markup.kwargs["inline_keyboard"]
        copy_btn = rows[0][0]
        self.assertEqual(copy_btn.kwargs["text"], "Copy")
        self.assertEqual(copy_btn.kwargs["copy_text"].kwargs["text"], "git status")
        self.assertEqual(rows[0][1].kwargs["callback_data"], "m")
        self.assertEqual(rows[1][0].kwargs["url"], "https://example.test")

    def test_build_inline_keyboard_skips_invalid_copy_text(self):
        markup = self.client.build_inline_keyboard([
            [{"text": "Empty", "copy_text": ""}],
            [{"text": "Long", "copy_text": "x" * 257}],
            [{"text": "OK", "callback_data": "ok"}],
        ])
        rows = markup.kwargs["inline_keyboard"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0].kwargs["callback_data"], "ok")


class MessageReactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = _load_client()

    def test_reactions_enabled_default_and_override(self):
        self.assertTrue(self.client.reactions_enabled({}))
        self.assertFalse(self.client.reactions_enabled({"reactions_enabled": False}))
        self.assertFalse(self.client.reactions_enabled({"reactions_enabled": "off"}))

    def test_set_message_reaction_calls_api(self):
        calls = []

        class _Bot:
            async def set_message_reaction(self, **kwargs):
                calls.append(kwargs)

        ok = asyncio.run(self.client.set_message_reaction(_Bot(), 99, 55, "👀"))
        self.assertTrue(ok)
        self.assertEqual(calls[0]["chat_id"], 99)
        self.assertEqual(calls[0]["message_id"], 55)
        self.assertEqual(calls[0]["reaction"][0].emoji, "👀")

    def test_set_message_reaction_survives_old_bot_api(self):
        ok = asyncio.run(self.client.set_message_reaction(object(), 99, 55, "👀"))
        self.assertFalse(ok)  # no set_message_reaction attr → quiet no-op

    def test_set_message_reaction_swallows_api_errors(self):
        class _Bot:
            async def set_message_reaction(self, **kwargs):
                raise RuntimeError("reactions disabled in this chat")

        ok = asyncio.run(self.client.set_message_reaction(_Bot(), 99, 55, "👍"))
        self.assertFalse(ok)


class TruncateForTtsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.speech = _load_speech()

    def test_short_text_not_truncated(self):
        payload, truncated = self.speech.truncate_for_tts("Hello there.", 700)
        self.assertEqual(payload, "Hello there.")
        self.assertFalse(truncated)

    def test_cuts_at_sentence_boundary(self):
        text = ("First sentence. " * 40) + "Tail without ending"
        payload, truncated = self.speech.truncate_for_tts(text, 200)
        self.assertTrue(truncated)
        self.assertLessEqual(len(payload), 200)
        self.assertTrue(payload.endswith("First sentence."), payload[-40:])

    def test_falls_back_to_whitespace_without_punctuation(self):
        text = "word " * 100
        payload, truncated = self.speech.truncate_for_tts(text, 150)
        self.assertTrue(truncated)
        self.assertLessEqual(len(payload), 150)
        self.assertFalse(payload.endswith("wor"))  # no mid-word cut

    def test_default_max_chars_is_1400(self):
        settings = self.speech.voice_reply_settings({"speech": {"reply": {}}})
        self.assertEqual(settings["max_chars"], 1400)


def _load_i18n():
    spec = importlib.util.spec_from_file_location(
        "telegram_ux_i18n_under_test", REPO_ROOT / "helpers" / "i18n.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class I18nTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.i18n = _load_i18n()

    def test_language_defaults_to_english(self):
        self.assertEqual(self.i18n.bot_language({}), "en")
        self.assertEqual(self.i18n.bot_language({"language": "fr"}), "en")
        self.assertEqual(self.i18n.bot_language({"language": "DE"}), "de")

    def test_translation_with_formatting(self):
        de = self.i18n.t({"language": "de"}, "welcome", name="Ben")
        self.assertIn("Hallo Ben!", de)
        en = self.i18n.t({}, "welcome", name="Ben")
        self.assertIn("Hello Ben!", en)

    def test_unknown_key_falls_back_to_key(self):
        self.assertEqual(self.i18n.t({}, "no_such_key"), "no_such_key")

    def test_all_keys_have_english_and_german(self):
        for key, entry in self.i18n._STRINGS.items():
            self.assertIn("en", entry, f"missing en for {key}")
            self.assertIn("de", entry, f"missing de for {key}")

    def test_unauthorized_contains_user_id(self):
        text = self.i18n.t({"language": "de"}, "unauthorized", user_id=1234)
        self.assertIn("1234", text)


class CommandRegistryI18nTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_stub_helpers()
        aiogram = sys.modules["aiogram"]
        aiogram.Bot = object

        class _BotCommand:
            def __init__(self, command="", description=""):
                self.command = command
                self.description = description

        sys.modules["aiogram.types"].BotCommand = _BotCommand
        spec = importlib.util.spec_from_file_location(
            "telegram_ux_registry_under_test", REPO_ROOT / "helpers" / "command_registry.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        cls.registry = module

    def test_german_menu_covers_every_command(self):
        commands = {cmd for cmd, _, _ in self.registry.COMMAND_ROWS}
        self.assertEqual(commands, set(self.registry.COMMAND_MENU_DE.keys()))

    def test_german_help_text_uses_german_descriptions(self):
        text = self.registry.format_help_text(language="de")
        self.assertIn("Befehle:", text)
        self.assertIn("/clear — Chat zurücksetzen", text)
        english = self.registry.format_help_text()
        self.assertIn("Commands:", english)


if __name__ == "__main__":
    unittest.main()
