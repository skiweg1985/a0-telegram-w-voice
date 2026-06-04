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
    MARKDOWN = "MARKDOWN"


class _DummyMessage:
    pass


class _DummyCallbackQuery:
    pass


class _DummyAgentContext:
    registry = {}

    def __init__(self, config=None, name=""):
        self.id = f"ctx-{len(self.registry) + 1}"
        self.name = name
        self.data = {}
        self.paused = False
        self.agent0 = types.SimpleNamespace(history=types.SimpleNamespace(compress=lambda: False))
        self.killed = False
        self.__class__.registry[self.id] = self

    @classmethod
    def get(cls, ctx_id):
        return cls.registry.get(ctx_id)

    def kill_process(self):
        self.killed = True

    def set_data(self, key, value):
        self.data[key] = value

    def communicate(self, *args, **kwargs):
        return None


class _DummyUserMessage:
    def __init__(self, message=None, id=None):
        self.message = message
        self.id = id


class _DummyPrintStyle:
    @staticmethod
    def warning(*args, **kwargs):
        return None

    @staticmethod
    def error(*args, **kwargs):
        return None

    @staticmethod
    def info(*args, **kwargs):
        return None

    @staticmethod
    def success(*args, **kwargs):
        return None


class _DummyNotificationManager:
    @staticmethod
    def get():
        return types.SimpleNamespace(send=lambda *args, **kwargs: None)


class _DummyNotificationType:
    INFO = "info"


class _DummyNotificationPriority:
    LOW = "low"


class _DummyBotInstance:
    def __init__(self):
        self.bot = types.SimpleNamespace(token="dummy")


class _DummyAsyncBotContext:
    async def __aenter__(self):
        return types.SimpleNamespace()

    async def __aexit__(self, exc_type, exc, tb):
        return False


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
    helpers_pkg.plugins = plugins

    files = types.ModuleType("helpers.files")
    files.get_abs_path = lambda *parts: "/" + "/".join(str(p).strip("/") for p in parts if p is not None)
    files.read_file = lambda path: "{}"
    files.make_dirs = lambda path: None
    files.write_file = lambda path, content: None
    sys.modules["helpers.files"] = files
    helpers_pkg.files = files

    projects = types.ModuleType("helpers.projects")
    projects.activate_project = lambda *args, **kwargs: None
    projects.get_project = lambda *args, **kwargs: None
    sys.modules["helpers.projects"] = projects
    helpers_pkg.projects = projects

    mq = types.ModuleType("helpers.message_queue")
    mq.log_user_message = lambda *args, **kwargs: None
    sys.modules["helpers.message_queue"] = mq
    helpers_pkg.message_queue = mq

    notification = types.ModuleType("helpers.notification")
    notification.NotificationManager = _DummyNotificationManager
    notification.NotificationType = _DummyNotificationType
    notification.NotificationPriority = _DummyNotificationPriority
    sys.modules["helpers.notification"] = notification

    persist_chat = types.ModuleType("helpers.persist_chat")
    persist_chat.save_tmp_chat = lambda ctx: None
    persist_chat._deserialize_context = lambda payload: payload
    sys.modules["helpers.persist_chat"] = persist_chat

    print_style = types.ModuleType("helpers.print_style")
    print_style.PrintStyle = _DummyPrintStyle
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
    tc.send_text_with_keyboard = lambda *args, **kwargs: None
    tc.edit_text_with_keyboard = lambda *args, **kwargs: None
    sys.modules["usr.plugins.telegram_integration_voice.helpers.telegram_client"] = tc

    detail_status = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.detail_status")
    detail_status.render = lambda *args, **kwargs: None
    sys.modules["usr.plugins.telegram_integration_voice.helpers.detail_status"] = detail_status

    speech = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.speech")
    speech.optimize_output_default = lambda *args, **kwargs: "auto"
    sys.modules["usr.plugins.telegram_integration_voice.helpers.speech"] = speech

    bot_manager = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.bot_manager")
    bot_manager.get_bot = lambda *args, **kwargs: _DummyBotInstance()
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
    module_name = "telegram_test_handler"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class TelegramSessionPickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handler = _load_handler_module()

    def setUp(self):
        _DummyAgentContext.registry = {}

    def test_list_switchable_sessions_includes_matching_and_unbound_only(self):
        handler = self.handler
        meta = {
            "bound": {
                "id": "bound",
                "display_name": "Bound session",
                "created_at": "2026-01-01T00:00:00",
                "last_message": "2026-01-03T00:00:00",
                "data": {
                    handler.CTX_TG_BOT: "mainbot",
                    handler.CTX_TG_USER_ID: 42,
                    handler.CTX_TG_CHAT_ID: 99,
                },
            },
            "web": {
                "id": "web",
                "display_name": "Web session",
                "created_at": "2026-01-01T00:00:00",
                "last_message": "2026-01-02T00:00:00",
                "data": {},
            },
            "foreign": {
                "id": "foreign",
                "display_name": "Foreign session",
                "created_at": "2026-01-01T00:00:00",
                "last_message": "2026-01-04T00:00:00",
                "data": {
                    handler.CTX_TG_BOT: "otherbot",
                    handler.CTX_TG_USER_ID: 999,
                    handler.CTX_TG_CHAT_ID: 1000,
                },
            },
        }

        with mock.patch.object(handler.files, "get_abs_path", return_value="/tmp/chats"), \
             mock.patch.object(handler.os.path, "isdir", return_value=True), \
             mock.patch.object(handler.os, "listdir", return_value=["bound", "web", "foreign"]), \
             mock.patch.object(handler, "_read_persisted_chat_meta", side_effect=lambda ctx_id: meta[ctx_id]):
            sessions = handler._list_switchable_sessions("mainbot", 42, 99)

        self.assertEqual([s["id"] for s in sessions], ["bound", "web"])
        self.assertEqual(sessions[0]["telegram_binding"], "bound")
        self.assertEqual(sessions[1]["telegram_binding"], "unbound")

    def test_session_details_and_keyboard_mark_unbound_sessions(self):
        handler = self.handler
        meta = {
            "id": "web",
            "display_name": "Web session",
            "created_at": "2026-01-01T00:00:00",
            "last_message": "2026-01-02T00:00:00",
            "message_count": 3,
            "telegram_binding": "unbound",
            "data": {},
        }

        text = handler._session_details_text(meta, active_ctx_id=None)
        keyboard = handler._session_details_keyboard(meta, active_ctx_id=None)

        self.assertIn("🔓 unbound web session", text)
        self.assertIn("Opening this session will bind it to this Telegram chat.", text)
        self.assertEqual(keyboard[0][0]["text"], "✅ Open and bind to this chat")

    def test_activate_existing_unbound_session_binds_it_to_current_telegram_chat(self):
        handler = self.handler
        old_ctx = types.SimpleNamespace(id="old", killed=False)
        old_ctx.kill_process = lambda: setattr(old_ctx, "killed", True)
        saved_contexts = []
        saved_states = []
        target_ctx = types.SimpleNamespace(id="web", data={})

        with mock.patch.object(handler, "_list_switchable_sessions", return_value=[
            {
                "id": "web",
                "display_name": "Web session",
                "telegram_binding": "unbound",
                "last_message": "2026-01-02T00:00:00",
                "data": {},
            }
        ]), \
             mock.patch.object(handler, "_load_persisted_context", return_value=target_ctx) as load_ctx, \
             mock.patch.object(handler.AgentContext, "get", side_effect=lambda ctx_id: old_ctx if ctx_id == "old" else None), \
             mock.patch.object(handler, "_load_state", return_value={"chats": {"mainbot:42:99": "old"}}), \
             mock.patch.object(handler, "_save_state", side_effect=lambda state: saved_states.append(state.copy())), \
             mock.patch.object(handler, "save_tmp_chat", side_effect=lambda ctx: saved_contexts.append(ctx)):
            ok, reply, ctx = handler._activate_existing_session("mainbot", {"foo": "bar"}, 42, 99, "web")

        self.assertTrue(ok)
        self.assertIs(ctx, target_ctx)
        self.assertIn("Bound to this Telegram chat", reply)
        self.assertEqual(load_ctx.call_args.kwargs, {})
        self.assertEqual(target_ctx.data[handler.CTX_TG_BOT], "mainbot")
        self.assertEqual(target_ctx.data[handler.CTX_TG_USER_ID], 42)
        self.assertEqual(target_ctx.data[handler.CTX_TG_CHAT_ID], 99)
        self.assertTrue(old_ctx.killed)
        self.assertEqual(saved_states[-1]["chats"]["mainbot:42:99"], "web")
        self.assertEqual(saved_contexts[-1], target_ctx)


if __name__ == "__main__":
    unittest.main()
