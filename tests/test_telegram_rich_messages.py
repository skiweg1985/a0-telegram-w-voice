import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = REPO_ROOT / "helpers" / "telegram_client.py"


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
    aiogram_types.InlineKeyboardButton = _DummyInline
    aiogram_types.InlineKeyboardMarkup = _DummyInline
    aiogram_types.InputMediaDocument = _DummyInline
    aiogram_types.InputMediaPhoto = _DummyInline
    aiogram_types.InputMediaVideo = _DummyInline
    sys.modules["aiogram.types"] = aiogram_types

    helpers = types.ModuleType("helpers")
    helpers.__path__ = []
    sys.modules["helpers"] = helpers

    errors = types.ModuleType("helpers.errors")
    errors.format_error = lambda e: str(e)
    sys.modules["helpers.errors"] = errors

    print_style = types.ModuleType("helpers.print_style")

    class _PrintStyle:
        warnings: list[str] = []
        errors: list[str] = []

        @classmethod
        def warning(cls, msg, *a, **k):
            cls.warnings.append(str(msg))

        @classmethod
        def error(cls, msg, *a, **k):
            cls.errors.append(str(msg))

        @classmethod
        def info(cls, msg, *a, **k):
            pass

        @classmethod
        def reset(cls):
            cls.warnings = []
            cls.errors = []

    print_style.PrintStyle = _PrintStyle
    sys.modules["helpers.print_style"] = print_style
    return _PrintStyle


def _load_client():
    _install_stub_helpers()
    spec = importlib.util.spec_from_file_location(
        "telegram_rich_client_under_test", CLIENT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeRichBot:
    def __init__(self, response=None, exc: Exception | None = None):
        self.response = response or types.SimpleNamespace(message_id=123)
        self.exc = exc
        self.calls = []

    async def send_rich_message(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.response


class TelegramRichMessageClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = _load_client()
        cls.print_style = sys.modules["helpers.print_style"].PrintStyle

    def setUp(self):
        self.print_style.reset()

    def test_settings_default_off_and_accept_strings(self):
        settings = self.client.rich_messages_settings({})
        self.assertEqual(settings, {"enabled": False, "drafts_enabled": False})

        settings = self.client.rich_messages_settings({
            "rich_messages": {
                "enabled": "true",
                "drafts_enabled": "false",
            }
        })
        self.assertTrue(settings["enabled"])
        self.assertFalse(settings["drafts_enabled"])

    def test_eligibility_detects_rich_structures_but_not_plain_text(self):
        self.assertFalse(self.client.rich_message_eligible("Just a normal answer."))
        self.assertTrue(self.client.rich_message_eligible("# Heading\n\nBody"))
        self.assertTrue(self.client.rich_message_eligible("- [x] done\n- [ ] todo"))
        self.assertTrue(self.client.rich_message_eligible("A | B\n--- | ---\n1 | 2"))
        self.assertTrue(self.client.rich_message_eligible("<details><summary>x</summary>y</details>"))
        self.assertTrue(self.client.rich_message_eligible("$$a^2 + b^2$$"))

    def test_send_rich_text_sends_raw_markdown_with_reply_parameters(self):
        bot = _FakeRichBot()
        markup = {"inline_keyboard": [[{"text": "More"}]]}

        result = asyncio.run(
            self.client.send_rich_text(
                bot,
                42,
                "A | B\n--- | ---\n1 | 2",
                reply_to_message_id=99,
                reply_markup=markup,
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.message_id, 123)
        self.assertEqual(bot.calls[0]["rich_message"]["markdown"], "A | B\n--- | ---\n1 | 2")
        self.assertEqual(bot.calls[0]["reply_parameters"], {"message_id": 99})
        self.assertIs(bot.calls[0]["reply_markup"], markup)

    def test_missing_support_allows_legacy_fallback_and_marks_capability(self):
        result = asyncio.run(
            self.client.send_rich_text(types.SimpleNamespace(), 42, "# Heading")
        )

        self.assertFalse(result.success)
        self.assertTrue(result.fallback_allowed)
        self.assertTrue(result.capability_error)

    def test_bad_request_allows_legacy_fallback_without_capability_latch(self):
        from aiogram.exceptions import TelegramBadRequest

        bot = _FakeRichBot(exc=TelegramBadRequest("can't parse rich message"))

        result = asyncio.run(self.client.send_rich_text(bot, 42, "# Heading"))

        self.assertFalse(result.success)
        self.assertTrue(result.fallback_allowed)
        self.assertFalse(result.capability_error)
        self.assertEqual(len(bot.calls), 1)

    def test_method_not_found_latches_as_capability_error(self):
        bot = _FakeRichBot(exc=RuntimeError("Method not found"))

        result = asyncio.run(self.client.send_rich_text(bot, 42, "# Heading"))

        self.assertFalse(result.success)
        self.assertTrue(result.fallback_allowed)
        self.assertTrue(result.capability_error)

    def test_transient_error_does_not_allow_legacy_resend(self):
        bot = _FakeRichBot(exc=TimeoutError("network timeout"))

        result = asyncio.run(self.client.send_rich_text(bot, 42, "# Heading"))

        self.assertFalse(result.success)
        self.assertFalse(result.fallback_allowed)
        self.assertFalse(result.capability_error)
        self.assertEqual(len(bot.calls), 1)
        self.assertTrue(any("not legacy-resending" in e for e in self.print_style.errors))

    def test_handler_final_text_uses_rich_and_latches_capability_failure(self):
        handler = _load_handler_for_rich_tests()
        ctx_data = {}
        bot = _FakeRichBot()

        msg_id = asyncio.run(
            handler._send_telegram_text_message(
                bot,
                42,
                "A | B\n--- | ---\n1 | 2",
                [[{"text": "More", "callback_data": "m"}]],
                99,
                bot_cfg={"rich_messages": {"enabled": True}},
                ctx_data=ctx_data,
            )
        )

        self.assertEqual(msg_id, 123)
        self.assertEqual(bot.calls[0]["reply_parameters"], {"message_id": 99})
        handler.tc.send_text_with_keyboard.assert_not_awaited()

        cap_result = types.SimpleNamespace(
            success=False,
            message_id=None,
            fallback_allowed=True,
            capability_error=True,
            error="Method not found",
        )
        with mock.patch.object(handler.tc, "send_rich_text", new=mock.AsyncMock(return_value=cap_result)):
            msg_id = asyncio.run(
                handler._send_telegram_text_message(
                    types.SimpleNamespace(),
                    42,
                    "A | B\n--- | ---\n1 | 2",
                    None,
                    None,
                    bot_cfg={"rich_messages": {"enabled": True}},
                    ctx_data=ctx_data,
                )
            )

        self.assertEqual(msg_id, 888)
        self.assertTrue(ctx_data[handler.CTX_TG_RICH_SEND_DISABLED])
        handler.tc.send_text.assert_awaited_once()


def _load_handler_for_rich_tests():
    module_name = "telegram_rich_handler_under_test"
    sys.modules.pop(module_name, None)

    for name in list(sys.modules):
        if name.startswith("usr.plugins.telegram_integration_voice"):
            sys.modules.pop(name, None)

    usr = types.ModuleType("usr")
    usr.__path__ = []
    sys.modules["usr"] = usr
    usr_plugins = types.ModuleType("usr.plugins")
    usr_plugins.__path__ = []
    sys.modules["usr.plugins"] = usr_plugins
    telegram_pkg = types.ModuleType("usr.plugins.telegram_integration_voice")
    telegram_pkg.__path__ = []
    sys.modules["usr.plugins.telegram_integration_voice"] = telegram_pkg
    helpers_pkg = types.ModuleType("usr.plugins.telegram_integration_voice.helpers")
    helpers_pkg.__path__ = []
    sys.modules["usr.plugins.telegram_integration_voice.helpers"] = helpers_pkg

    constants_spec = importlib.util.spec_from_file_location(
        "usr.plugins.telegram_integration_voice.helpers.constants",
        REPO_ROOT / "helpers" / "constants.py",
    )
    constants = importlib.util.module_from_spec(constants_spec)
    sys.modules[constants_spec.name] = constants
    constants_spec.loader.exec_module(constants)

    tc = _load_client()
    tc.send_text = mock.AsyncMock(return_value=888)
    tc.send_text_with_keyboard = mock.AsyncMock(return_value=889)
    sys.modules["usr.plugins.telegram_integration_voice.helpers.telegram_client"] = tc

    for mod_name, attrs in {
        "usr.plugins.telegram_integration_voice.helpers.detail_status": {},
        "usr.plugins.telegram_integration_voice.helpers.speech": {},
        "usr.plugins.telegram_integration_voice.helpers.status_copy": {},
        "usr.plugins.telegram_integration_voice.helpers.command_registry": {"format_help_text": lambda *a, **k: "help"},
        "usr.plugins.telegram_integration_voice.helpers.bot_manager": {"get_bot": lambda *a, **k: None},
    }.items():
        mod = types.ModuleType(mod_name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        sys.modules[mod_name] = mod

    aiogram_client_default = types.ModuleType("aiogram.client.default")
    aiogram_client_default.DefaultBotProperties = object
    sys.modules["aiogram.client.default"] = aiogram_client_default
    aiogram_enums = types.ModuleType("aiogram.enums")
    aiogram_enums.ParseMode = type("ParseMode", (), {"HTML": "HTML"})
    sys.modules["aiogram.enums"] = aiogram_enums
    aiogram_types = sys.modules["aiogram.types"]
    aiogram_types.Message = object
    aiogram_types.CallbackQuery = object
    aiogram_types.ForceReply = object

    agent = types.ModuleType("agent")
    agent.Agent = object
    agent.AgentContext = object
    agent.UserMessage = object
    sys.modules["agent"] = agent

    for mod_name in [
        "helpers.plugins",
        "helpers.files",
        "helpers.projects",
        "helpers.message_queue",
        "helpers.notification",
        "helpers.persist_chat",
    ]:
        sys.modules[mod_name] = types.ModuleType(mod_name)
    sys.modules["helpers.notification"].NotificationManager = object
    sys.modules["helpers.notification"].NotificationType = object
    sys.modules["helpers.notification"].NotificationPriority = object
    sys.modules["helpers.persist_chat"].save_tmp_chat = lambda *a, **k: None
    sys.modules["helpers.persist_chat"]._deserialize_context = lambda x: x
    sys.modules["helpers.persist_chat"].remove_chat = lambda *a, **k: None
    sys.modules["initialize"] = types.ModuleType("initialize")
    sys.modules["initialize"].initialize_agent = lambda: {}

    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / "helpers" / "handler.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
