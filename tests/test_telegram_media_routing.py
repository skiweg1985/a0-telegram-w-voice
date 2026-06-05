import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
HANDLER_PATH = REPO_ROOT / "helpers" / "handler.py"


class _DummyBot:
    def __init__(self, *args, **kwargs):
        pass


class _DummyDefaultBotProperties:
    def __init__(self, *args, **kwargs):
        pass


class _DummyParseMode:
    HTML = "HTML"


class _DummyMessage:
    pass


class _DummyCallbackQuery:
    pass


class _DummyForceReply:
    def __init__(self, *args, **kwargs):
        pass


class _DummyAgentContext:
    registry = {}

    def __init__(self, config=None, name=""):
        self.id = f"ctx-{len(self.registry) + 1}"
        self.name = name
        self.data = {}
        self.agent0 = types.SimpleNamespace(
            history=types.SimpleNamespace(compress=lambda: False, get_tokens=lambda: 0, counter=0),
            get_data=lambda *args, **kwargs: {},
        )
        self.paused = False
        self.__class__.registry[self.id] = self

    @classmethod
    def get(cls, ctx_id):
        return cls.registry.get(ctx_id)

    def kill_process(self):
        return None

    def communicate(self, *args, **kwargs):
        return None


class _DummyUserMessage:
    def __init__(self, message=None, attachments=None, id=None):
        self.message = message
        self.attachments = attachments or []
        self.id = id


def _install_stub_modules():
    aiogram = types.ModuleType("aiogram")
    aiogram.Bot = _DummyBot
    sys.modules["aiogram"] = aiogram

    aiogram_client_default = types.ModuleType("aiogram.client.default")
    aiogram_client_default.DefaultBotProperties = _DummyDefaultBotProperties
    sys.modules["aiogram.client.default"] = aiogram_client_default

    aiogram_enums = types.ModuleType("aiogram.enums")
    aiogram_enums.ParseMode = _DummyParseMode
    sys.modules["aiogram.enums"] = aiogram_enums

    aiogram_types = types.ModuleType("aiogram.types")
    aiogram_types.Message = _DummyMessage
    aiogram_types.CallbackQuery = _DummyCallbackQuery
    aiogram_types.ForceReply = _DummyForceReply
    sys.modules["aiogram.types"] = aiogram_types

    agent = types.ModuleType("agent")
    agent.Agent = object
    agent.AgentContext = _DummyAgentContext
    agent.UserMessage = _DummyUserMessage
    sys.modules["agent"] = agent

    helpers_pkg = types.ModuleType("helpers")
    helpers_pkg.__path__ = []
    sys.modules["helpers"] = helpers_pkg

    plugins = types.ModuleType("helpers.plugins")
    plugins.get_plugin_config = lambda *args, **kwargs: {}
    sys.modules["helpers.plugins"] = plugins

    files = types.ModuleType("helpers.files")
    files.fix_dev_path = lambda path: str(path)
    files.get_abs_path = lambda *parts: "/" + "/".join(str(p).strip("/") for p in parts if p is not None)
    files.get_abs_path_dockerized = files.get_abs_path
    files.read_file = lambda path: "{}"
    files.make_dirs = lambda path: None
    files.write_file = lambda path, content: None
    sys.modules["helpers.files"] = files

    projects = types.ModuleType("helpers.projects")
    projects.activate_project = lambda *args, **kwargs: None
    projects.get_context_project_name = lambda *args, **kwargs: ""
    sys.modules["helpers.projects"] = projects

    mq = types.ModuleType("helpers.message_queue")
    mq.log_user_message = lambda *args, **kwargs: None
    sys.modules["helpers.message_queue"] = mq

    notification = types.ModuleType("helpers.notification")
    notification.NotificationManager = types.SimpleNamespace(send_notification=lambda *args, **kwargs: None)
    notification.NotificationType = types.SimpleNamespace(INFO="info")
    notification.NotificationPriority = types.SimpleNamespace(NORMAL="normal", HIGH="high")
    sys.modules["helpers.notification"] = notification

    persist_chat = types.ModuleType("helpers.persist_chat")
    persist_chat.save_tmp_chat = lambda ctx: None
    persist_chat._deserialize_context = lambda payload: payload
    sys.modules["helpers.persist_chat"] = persist_chat

    print_style = types.ModuleType("helpers.print_style")
    print_style.PrintStyle = types.SimpleNamespace(
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        success=lambda *args, **kwargs: None,
    )
    sys.modules["helpers.print_style"] = print_style

    errors = types.ModuleType("helpers.errors")
    errors.format_error = lambda e: str(e)
    sys.modules["helpers.errors"] = errors

    initialize = types.ModuleType("initialize")
    initialize.initialize_agent = lambda: {}
    sys.modules["initialize"] = initialize

    usr = types.ModuleType("usr")
    usr.__path__ = []
    sys.modules["usr"] = usr

    usr_plugins = types.ModuleType("usr.plugins")
    usr_plugins.__path__ = []
    sys.modules["usr.plugins"] = usr_plugins

    telegram_pkg = types.ModuleType("usr.plugins.telegram_integration_voice")
    telegram_pkg.__path__ = []
    sys.modules["usr.plugins.telegram_integration_voice"] = telegram_pkg

    telegram_helpers_pkg = types.ModuleType("usr.plugins.telegram_integration_voice.helpers")
    telegram_helpers_pkg.__path__ = []
    sys.modules["usr.plugins.telegram_integration_voice.helpers"] = telegram_helpers_pkg

    tc = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.telegram_client")
    tc.build_reply_keyboard = lambda *args, **kwargs: {"reply_keyboard": True}
    tc.is_animation_file = lambda path: str(path).lower().endswith(".gif")
    tc.is_image_file = lambda path: str(path).lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp"))
    tc.is_video_file = lambda path: str(path).lower().endswith((".mp4", ".mov", ".m4v", ".webm"))
    sys.modules["usr.plugins.telegram_integration_voice.helpers.telegram_client"] = tc

    detail_status = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.detail_status")
    detail_status.effective_detail_level = lambda *args, **kwargs: "info"
    detail_status.detail_level_display = lambda level: level
    detail_status.normalize_detail_level = lambda level: level or "info"
    sys.modules["usr.plugins.telegram_integration_voice.helpers.detail_status"] = detail_status

    speech = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.speech")
    speech.optimize_output_default = lambda *args, **kwargs: "off"
    sys.modules["usr.plugins.telegram_integration_voice.helpers.speech"] = speech

    bot_manager = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.bot_manager")
    bot_manager.get_bot = lambda *args, **kwargs: types.SimpleNamespace(bot=types.SimpleNamespace(token="dummy"))
    sys.modules["usr.plugins.telegram_integration_voice.helpers.bot_manager"] = bot_manager

    command_registry = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.command_registry")
    command_registry.format_help_text = lambda *args, **kwargs: "help"
    sys.modules["usr.plugins.telegram_integration_voice.helpers.command_registry"] = command_registry

    constants_spec = importlib.util.spec_from_file_location(
        "usr.plugins.telegram_integration_voice.helpers.constants",
        REPO_ROOT / "helpers" / "constants.py",
    )
    constants_module = importlib.util.module_from_spec(constants_spec)
    sys.modules[constants_spec.name] = constants_module
    constants_spec.loader.exec_module(constants_module)


def _load_handler_module():
    _install_stub_modules()
    module_name = "telegram_media_test_handler"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class TelegramMediaRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handler = _load_handler_module()

    def setUp(self):
        _DummyAgentContext.registry = {}

    def test_normalize_outbound_items_preserves_order_and_classifies_types(self):
        handler = self.handler
        items = handler._normalize_outbound_items(
            ["/tmp/a.jpg", "/tmp/b.gif", "/tmp/c.mp4", "/tmp/d.bin"],
            telegram_items=[
                {"type": "location", "latitude": 1.0, "longitude": 2.0},
                {"type": "video_note", "path": "/tmp/videonote_1.mp4"},
            ],
        )

        self.assertEqual(
            [item["type"] for item in items],
            ["location", "video_note", "photo", "animation", "video", "document"],
        )
        self.assertEqual(items[0]["latitude"], 1.0)
        self.assertEqual(items[1]["path"], "/tmp/videonote_1.mp4")

    def test_group_outbound_items_only_groups_contiguous_compatible_runs(self):
        handler = self.handler
        groups = handler._group_outbound_items(
            [
                {"type": "photo", "path": "/tmp/a.jpg"},
                {"type": "video", "path": "/tmp/b.mp4"},
                {"type": "animation", "path": "/tmp/c.gif"},
                {"type": "document", "path": "/tmp/d.pdf"},
                {"type": "document", "path": "/tmp/e.pdf"},
                {"type": "photo", "path": "/tmp/f.jpg"},
            ]
        )

        self.assertEqual(
            [[item["type"] for item in group] for group in groups],
            [["photo", "video"], ["animation"], ["document", "document"], ["photo"]],
        )

    def test_build_reply_keyboard_is_private_only(self):
        handler = self.handler

        with mock.patch.object(handler.tc, "build_reply_keyboard", return_value={"ok": True}) as build_keyboard:
            self.assertEqual(
                handler._build_reply_keyboard({"reply_keyboard": {"enabled": True}}, "private"),
                {"ok": True},
            )
            self.assertIsNone(handler._build_reply_keyboard({"reply_keyboard": {"enabled": True}}, "group"))
            self.assertIsNone(handler._build_reply_keyboard({}, "private"))

        build_keyboard.assert_called_once()


if __name__ == "__main__":
    unittest.main()
