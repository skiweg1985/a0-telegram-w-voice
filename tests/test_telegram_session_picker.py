import asyncio
import contextlib
import importlib.util
import json
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


class _DummyForceReply:
    def __init__(self, *args, **kwargs):
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
        self.reset_called = False
        self.removed = False
        self.__class__.registry[self.id] = self

    @classmethod
    def get(cls, ctx_id):
        return cls.registry.get(ctx_id)

    @classmethod
    def remove(cls, ctx_id):
        ctx = cls.registry.pop(ctx_id, None)
        if ctx is not None:
            ctx.removed = True
        return ctx

    def kill_process(self):
        self.killed = True

    def reset(self):
        self.kill_process()
        self.reset_called = True
        self.paused = False

    def set_data(self, key, value):
        self.data[key] = value

    def communicate(self, *args, **kwargs):
        return None

    def is_running(self):
        return False


class _DummyUserMessage:
    def __init__(self, message=None, attachments=None, id=None):
        self.message = message
        self.attachments = attachments
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
    helpers_pkg.plugins = plugins

    files = types.ModuleType("helpers.files")
    files.get_abs_path = lambda *parts: "/" + "/".join(str(p).strip("/") for p in parts if p is not None)
    files.fix_dev_path = lambda path: str(path)
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

    def _persist_chat_remove_chat(ctx_id):
        # Tests verify call count + ctx_id via side_effect below
        return None

    persist_chat.remove_chat = _persist_chat_remove_chat
    sys.modules["helpers.persist_chat"] = persist_chat

    print_style = types.ModuleType("helpers.print_style")
    print_style.PrintStyle = _DummyPrintStyle
    sys.modules["helpers.print_style"] = print_style

    errors = types.ModuleType("helpers.errors")
    errors.format_error = lambda e: str(e)
    sys.modules["helpers.errors"] = errors

    detail_status = types.ModuleType("helpers.detail_status")

    def _redact_secrets_text(value, _known=None):
        if not isinstance(value, str):
            return value
        import re as _re
        text = value
        # Substitutes the secret values from the test, mirroring the regex-based
        # redaction logic in helpers/detail_status.py closely enough for unit tests.
        patterns = [
            (r"(?i)(api[_-]?key\s*=\s*)([^\s,'\"`]+)", r"\1[REDACTED]"),
            (r"(?i)(password\s*=\s*)([^\s,'\"`]+)", r"\1[REDACTED]"),
            (r"(?i)(token\s*=\s*)([^\s,'\"`]+)", r"\1[REDACTED]"),
            (r"(?i)(secret\s*=\s*)([^\s,'\"`]+)", r"\1[REDACTED]"),
        ]
        for pat, repl in patterns:
            text = _re.sub(pat, repl, text)
        return text

    detail_status.redact_sensitive = _redact_secrets_text
    sys.modules["helpers.detail_status"] = detail_status
    helpers_pkg.detail_status = detail_status

    state_monitor = types.ModuleType("helpers.state_monitor_integration")
    state_monitor.mark_dirty_all = lambda *args, **kwargs: None
    sys.modules["helpers.state_monitor_integration"] = state_monitor

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

    chat_rename_pkg = types.ModuleType("usr.plugins.chat_rename")
    chat_rename_pkg.__path__ = []
    sys.modules["usr.plugins.chat_rename"] = chat_rename_pkg

    chat_rename_helpers_pkg = types.ModuleType("usr.plugins.chat_rename.helpers")
    chat_rename_helpers_pkg.__path__ = []
    sys.modules["usr.plugins.chat_rename.helpers"] = chat_rename_helpers_pkg

    chat_rename_constants = types.ModuleType("usr.plugins.chat_rename.helpers.constants")
    chat_rename_constants.MANUAL_LOCK_DATA_KEY = "chat_rename_manual_lock"
    chat_rename_constants.MAX_MANUAL_CHAT_NAME_LENGTH = 120
    sys.modules["usr.plugins.chat_rename.helpers.constants"] = chat_rename_constants

    tc = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.telegram_client")
    tc.send_text_with_keyboard = lambda *args, **kwargs: None
    tc.edit_text_with_keyboard = lambda *args, **kwargs: None
    tc.delete_message = lambda *args, **kwargs: None
    tc.supports_message_draft = lambda *args, **kwargs: False
    tc.send_message_draft = lambda *args, **kwargs: None
    tc.build_inline_keyboard = lambda buttons, *args, **kwargs: {"inline_keyboard": buttons}
    tc.md_to_telegram_html = lambda text: text

    async def _tc_send_typing(*args, **kwargs):
        return None

    tc.send_typing = _tc_send_typing
    tc.send_record_voice = _tc_send_typing
    tc.send_voice = _tc_send_typing
    sys.modules["usr.plugins.telegram_integration_voice.helpers.telegram_client"] = tc

    detail_status = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.detail_status")
    detail_status.render = lambda *args, **kwargs: None
    detail_status.effective_detail_level = lambda bot_cfg, ctx_data: str(ctx_data.get("telegram_detail_level_session", bot_cfg.get("telegram_detail_level", "info")) or "info")
    detail_status.effective_execute_before_enabled = lambda bot_cfg, ctx_data: str(ctx_data.get("telegram_detail_before_session", "") or "").strip().lower() in ("on", "true", "1", "yes")
    detail_status.normalize_execute_before_enabled = lambda value: str(value or "").strip().lower() in ("on", "true", "1", "yes")
    detail_status.detail_level_display = lambda value: "verbose" if str(value) == "debug" else str(value)
    sys.modules["usr.plugins.telegram_integration_voice.helpers.detail_status"] = detail_status

    speech = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.speech")
    speech.optimize_output_default = lambda *args, **kwargs: "auto"
    speech.tts_enabled = lambda *args, **kwargs: False
    speech.voice_reply_settings = lambda *args, **kwargs: {"voice_mode": "off", "also_send_text": True, "max_chars": 700, "quick_actions": {"enabled": True, "show_text": True}}
    speech.quick_actions_settings = lambda *args, **kwargs: {"enabled": True, "show_text": True}
    speech.effective_reply_actions_enabled = lambda bot_cfg, ctx_data: str(ctx_data.get("telegram_reply_actions_session", "") or "").strip().lower() not in ("off", "false", "0", "no")
    speech.synthesize_to_voice_file = lambda *args, **kwargs: ("/tmp/fake.ogg", {})
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

    status_copy_spec = importlib.util.spec_from_file_location(
        "usr.plugins.telegram_integration_voice.helpers.status_copy",
        REPO_ROOT / "helpers" / "status_copy.py",
    )
    status_copy_module = importlib.util.module_from_spec(status_copy_spec)
    sys.modules[status_copy_spec.name] = status_copy_module
    status_copy_spec.loader.exec_module(status_copy_module)



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
        old_stop = mock.Mock()
        old_ctx.data = {handler.CTX_TG_TYPING_STOP: types.SimpleNamespace(set=old_stop)}
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
        old_stop.assert_called_once_with()
        self.assertTrue(old_ctx.killed)
        self.assertEqual(saved_states[-1]["chats"]["mainbot:42:99"], "web")
        self.assertEqual(saved_contexts[-1], target_ctx)

    def test_handle_stop_stops_typing_before_killing_process(self):
        handler = self.handler
        typing_stop = mock.Mock()
        voice_stop = mock.Mock()
        voice_key = getattr(handler, "CTX_TG_RECORD_VOICE_STOP", "_telegram_record_voice_stop")
        ctx = types.SimpleNamespace(
            data={
                handler.CTX_TG_TYPING_STOP: types.SimpleNamespace(set=typing_stop),
                voice_key: types.SimpleNamespace(set=voice_stop),
            },
            kill_process=mock.Mock(),
        )
        message = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji"),
            chat=types.SimpleNamespace(id=99),
        )

        with mock.patch.object(handler, "_is_allowed", return_value=True), \
             mock.patch.object(handler, "_get_existing_context", return_value=ctx), \
             mock.patch.object(handler, "get_bot", return_value=_DummyBotInstance()), \
             mock.patch.object(handler, "save_tmp_chat"), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock()) as send_temp:
            asyncio.run(handler.handle_stop(message, "mainbot", {}))

        typing_stop.assert_called_once_with()
        voice_stop.assert_called_once_with()
        ctx.kill_process.assert_called_once_with()
        self.assertNotIn(handler.CTX_TG_TYPING_STOP, ctx.data)
        self.assertNotIn(voice_key, ctx.data)
        send_temp.assert_awaited_once()

    def test_start_new_session_stops_old_typing_before_kill(self):
        handler = self.handler
        old_stop = mock.Mock()
        old_ctx = types.SimpleNamespace(
            id="old",
            data={handler.CTX_TG_TYPING_STOP: types.SimpleNamespace(set=old_stop)},
            kill_process=mock.Mock(),
        )
        new_ctx = types.SimpleNamespace(id="new", data={})

        with mock.patch.object(handler.AgentContext, "get", return_value=old_ctx), \
             mock.patch.object(handler, "_load_state", return_value={"chats": {"mainbot:42:99": "old"}}), \
             mock.patch.object(handler, "_save_state"), \
             mock.patch.object(handler, "save_tmp_chat"), \
             mock.patch.object(handler, "_get_or_create_context_from_user", new=mock.AsyncMock(return_value=new_ctx)):
            ok, reply, ctx = asyncio.run(
                handler._start_new_session_for_user("mainbot", {}, 42, "benji", 99)
            )

        self.assertTrue(ok)
        self.assertIs(ctx, new_ctx)
        old_stop.assert_called_once_with()
        old_ctx.kill_process.assert_called_once_with()

    def test_dispatch_user_turn_stops_previous_typing_before_replacing_handle(self):
        handler = self.handler
        old_stop = mock.Mock()
        new_stop = types.SimpleNamespace(set=mock.Mock())
        ctx = types.SimpleNamespace(
            data={handler.CTX_TG_TYPING_STOP: types.SimpleNamespace(set=old_stop)},
            is_running=lambda: False,
            agent0=types.SimpleNamespace(read_prompt=lambda *args, **kwargs: "prompt"),
            communicate=mock.Mock(),
        )

        with mock.patch.object(handler, "_start_typing", return_value=new_stop), \
             mock.patch.object(handler, "_clear_progress_state"), \
             mock.patch.object(handler, "_send_initial_progress_status", new=mock.AsyncMock()), \
             mock.patch.object(handler.mq, "log_user_message"), \
             mock.patch.object(handler, "save_tmp_chat"):
            error = asyncio.run(
                handler._dispatch_telegram_user_turn(
                    ctx,
                    bot_token="token",
                    chat_id=99,
                    sender="Benji",
                    body="hello",
                    attachments=None,
                    source="telegram",
                )
            )

        self.assertIsNone(error)
        old_stop.assert_called_once_with()
        self.assertIs(ctx.data[handler.CTX_TG_TYPING_STOP], new_stop)

    def test_handle_message_stops_typing_when_post_registration_step_raises(self):
        handler = self.handler
        typing_stop = mock.Mock()
        ctx = types.SimpleNamespace(
            data={},
            agent0=types.SimpleNamespace(read_prompt=lambda *args, **kwargs: "prompt"),
            communicate=mock.Mock(),
        )
        message = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji", first_name="Benji", last_name=None),
            chat=types.SimpleNamespace(id=99, type="private"),
            text="hello",
            caption=None,
            location=None,
            contact=None,
            sticker=None,
            photo=None,
            document=None,
            audio=None,
            voice=None,
            video=None,
            video_note=None,
            reply_to_message=None,
            message_id=123,
        )

        with mock.patch.object(handler, "_is_allowed", return_value=True), \
             mock.patch.object(handler, "get_bot", return_value=_DummyBotInstance()), \
             mock.patch.object(handler, "_is_session_search_pending", return_value=False), \
             mock.patch.object(handler, "_start_typing", return_value=types.SimpleNamespace(set=typing_stop)), \
             mock.patch.object(handler, "_get_or_create_context", new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(handler, "_clear_progress_state"), \
             mock.patch.object(handler, "_send_initial_progress_status", new=mock.AsyncMock()), \
             mock.patch.object(handler, "_download_attachments", new=mock.AsyncMock(return_value=[])), \
             mock.patch.object(handler.mq, "log_user_message", side_effect=RuntimeError("boom")), \
             mock.patch.object(handler, "save_tmp_chat"), \
             mock.patch.object(handler, "_temp_bot", return_value=_DummyAsyncBotContext()):
            with self.assertRaises(RuntimeError):
                asyncio.run(handler.handle_message(message, "mainbot", {}))

        typing_stop.assert_called_once_with()
        self.assertNotIn(handler.CTX_TG_TYPING_STOP, ctx.data)

    def test_extract_live_response_preview_from_complete_response_tool_json(self):
        handler = self.handler
        payload = json.dumps({
            "tool_name": "response",
            "tool_args": {
                "text": "Hallo **Benji**",
                "break_loop": True,
            },
        })

        preview = handler._extract_live_response_preview(payload)

        self.assertEqual(preview["text"], "Hallo **Benji**")
        self.assertTrue(preview["complete_tool_json"])

    def test_extract_live_response_preview_from_partial_stream_json(self):
        handler = self.handler
        payload = '{"tool_name":"response","tool_args":{"text":"Hallo\nWelt'

        preview = handler._extract_live_response_preview(payload)

        self.assertEqual(preview["text"], "Hallo\nWelt")

    def test_extract_live_response_preview_skips_markdown_only_partial_fragments(self):
        handler = self.handler
        payload = '{"tool_name":"response","tool_args":{"text":"**'

        self.assertIsNone(handler._extract_live_response_preview(payload))

    def test_extract_live_response_preview_skips_inline_progress_updates(self):
        handler = self.handler
        payload = json.dumps({
            "tool_name": "response",
            "tool_args": {
                "text": "working on it",
                "break_loop": False,
            },
        })

        self.assertIsNone(handler._extract_live_response_preview(payload))

    def test_extract_live_response_preview_keeps_partial_preview_for_empty_attachments_array(self):
        handler = self.handler
        payload = '{"tool_name":"response","tool_args":{"text":"Hallo","attachments": []'

        preview = handler._extract_live_response_preview(payload)

        self.assertEqual(preview["text"], "Hallo")

    def test_extract_live_response_preview_skips_when_partial_stream_has_non_empty_attachments_array(self):
        handler = self.handler
        payload = '{"tool_name":"response","tool_args":{"text":"Hallo","attachments": ["/tmp/file.ogg"]'

        self.assertIsNone(handler._extract_live_response_preview(payload))

    def test_render_progress_status_html_uses_in_progress_title(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        html_text = handler._render_progress_status_html(ctx, {}, done=False)

        self.assertIn("⏳ Working on it…", html_text)
        self.assertNotIn("In progress", html_text)

    def test_render_progress_status_html_uses_done_copy_for_completed_state(self):
        handler = self.handler
        ctx = _DummyAgentContext()

        html_text = handler._render_progress_status_html(ctx, {}, done=True)

        self.assertIn("✅ Done", html_text)
        self.assertNotIn("✅ Ready", html_text)

    def test_render_progress_status_html_shows_gen_phase_in_header(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_PROGRESS_PHASE] = "gen"

        html_text = handler._render_progress_status_html(ctx, {}, done=False)

        self.assertIn("🤔 Drafting reply…", html_text)

    def test_render_progress_status_html_shows_stt_phase_in_header(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_PROGRESS_PHASE] = "stt"

        html_text = handler._render_progress_status_html(ctx, {}, done=False)

        self.assertIn("🎤 Transcribing voice…", html_text)

    def test_render_progress_status_html_shows_tts_phase_in_header(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_PROGRESS_PHASE] = "tts"

        html_text = handler._render_progress_status_html(ctx, {}, done=False)

        self.assertIn("🔊 Creating voice reply…", html_text)

    def test_render_progress_status_html_includes_live_preview_block(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_STREAM_PREVIEW] = "Partial answer"
        html_text = handler._render_progress_status_html(ctx, {}, done=False)

        self.assertIn("💬 Draft reply…", html_text)
        self.assertIn("Partial answer", html_text)

    def test_render_progress_status_html_hides_preview_block_when_native_draft_active(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_STREAM_PREVIEW] = "Partial answer"
        ctx.data[handler.CTX_TG_STREAM_DRAFT_ACTIVE] = True

        html_text = handler._render_progress_status_html(ctx, {}, done=False)

        self.assertNotIn("💬 Draft reply…", html_text)

    def test_supports_native_draft_preview_only_for_private_chats_with_bot_capability(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_CHAT_ID] = 123456

        with mock.patch.object(handler.tc, "supports_message_draft", return_value=True):
            self.assertTrue(handler._supports_native_draft_preview(ctx, object()))

        ctx.data[handler.CTX_TG_CHAT_ID] = -100123456
        with mock.patch.object(handler.tc, "supports_message_draft", return_value=True):
            self.assertFalse(handler._supports_native_draft_preview(ctx, object()))

    def test_supports_native_draft_preview_respects_disabled_flag(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_CHAT_ID] = 123456
        ctx.data[handler.CTX_TG_STREAM_DRAFT_DISABLED] = True

        with mock.patch.object(handler.tc, "supports_message_draft", return_value=True):
            self.assertFalse(handler._supports_native_draft_preview(ctx, object()))

    def test_send_live_draft_preview_short_circuits_when_native_drafts_disabled(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_BOT] = "mainbot"
        ctx.data[handler.CTX_TG_CHAT_ID] = 123456
        ctx.data[handler.CTX_TG_STREAM_DRAFT_DISABLED] = True
        ctx.data[handler.CTX_TG_BOT_CFG] = {
            "progress": {
                "edit_throttle_ms": 200,
            }
        }

        async def _should_not_send(*args, **kwargs):
            raise AssertionError("send_message_draft should not be called when drafts are disabled")

        with mock.patch.object(handler.tc, "supports_message_draft", return_value=True), \
             mock.patch.object(handler.tc, "send_message_draft", side_effect=_should_not_send):
            ok = asyncio.run(handler._send_telegram_live_draft_preview(ctx, "Partial answer"))

        self.assertFalse(ok)

    def test_progress_settings_uses_hermes_style_live_preview_defaults(self):
        handler = self.handler

        cfg = handler._progress_settings({})

        self.assertEqual(cfg["live_response_preview_interval_ms"], 800)
        self.assertEqual(cfg["live_response_preview_buffer_threshold"], 24)

    def test_schedule_telegram_progress_update_returns_without_waiting_for_send(self):
        handler = self.handler
        ctx = _DummyAgentContext()

        async def slow_update(*args, **kwargs):
            await asyncio.sleep(0.05)
            return None

        async def scenario():
            with mock.patch.object(handler, "send_telegram_progress_update", new=mock.AsyncMock(side_effect=slow_update)) as send_progress:
                ok = handler.schedule_telegram_progress_update(ctx, "status", text_is_html=True)
                self.assertTrue(ok)
                send_progress.assert_not_awaited()
                await asyncio.sleep(0.01)
                send_progress.assert_awaited_once_with(ctx, "status", None, text_is_html=True)

        asyncio.run(scenario())

    def test_stream_chunk_schedules_worker_without_telegram_io(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_BOT_CFG] = {
            "progress": {
                "live_response_preview_interval_ms": 10000,
                "live_response_preview_buffer_threshold": 9999,
            }
        }
        stream_data = {
            "full": json.dumps({
                "tool_name": "response",
                "tool_args": {"text": "Partial answer", "break_loop": True},
            })
        }

        async def scenario():
            with mock.patch.object(handler, "_send_telegram_live_draft_preview", new=mock.AsyncMock()) as send_draft, \
                 mock.patch.object(handler, "_refresh_progress_status", new=mock.AsyncMock()) as refresh_progress:
                await handler.handle_telegram_response_stream_chunk(ctx, stream_data)
                send_draft.assert_not_awaited()
                refresh_progress.assert_awaited_once_with(ctx, ctx.data[handler.CTX_TG_BOT_CFG])
                self.assertIn(handler.CTX_TG_STREAM_WORKER_TASK, ctx.data)
                self.assertEqual(ctx.data[handler.CTX_TG_STREAM_PENDING_FULL], stream_data["full"])
                self.assertEqual(ctx.data[handler.CTX_TG_PROGRESS_PHASE], "gen")
                handler._cancel_stream_preview_worker(ctx)

        asyncio.run(scenario())

    def test_stream_chunk_coalesces_many_chunks_into_one_worker(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_BOT_CFG] = {
            "progress": {
                "live_response_preview_interval_ms": 10000,
                "live_response_preview_buffer_threshold": 9999,
            }
        }
        first = {"full": '{"tool_name":"response","tool_args":{"text":"First'}
        second = {"full": '{"tool_name":"response","tool_args":{"text":"Second'}

        async def scenario():
            await handler.handle_telegram_response_stream_chunk(ctx, first)
            task = ctx.data.get(handler.CTX_TG_STREAM_WORKER_TASK)
            await handler.handle_telegram_response_stream_chunk(ctx, second)
            self.assertIs(ctx.data.get(handler.CTX_TG_STREAM_WORKER_TASK), task)
            self.assertEqual(ctx.data[handler.CTX_TG_STREAM_PENDING_FULL], second["full"])
            handler._cancel_stream_preview_worker(ctx)

        asyncio.run(scenario())

    def test_stream_worker_flushes_partial_json_to_native_draft_when_buffer_threshold_is_reached(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_BOT_CFG] = {
            "progress": {
                "live_response_preview_interval_ms": 10000,
                "live_response_preview_buffer_threshold": 1,
            }
        }
        stream_data = {
            "full": '{"tool_name":"response","tool_args":{"text":"Threshold answer'
        }

        async def scenario():
            with mock.patch.object(handler, "_send_telegram_live_draft_preview", new=mock.AsyncMock(return_value=True)) as send_draft:
                await handler.handle_telegram_response_stream_chunk(ctx, stream_data)
                await asyncio.sleep(0.01)
                send_draft.assert_awaited_once_with(ctx, "Threshold answer")
                handler._cancel_stream_preview_worker(ctx)

        asyncio.run(scenario())

    def test_flush_live_preview_uses_latest_partial_pending_text_for_native_draft(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        token = "tok"
        ctx.data[handler.CTX_TG_STREAM_WORKER_TOKEN] = token
        ctx.data[handler.CTX_TG_BOT_CFG] = {
            "progress": {}
        }
        ctx.data[handler.CTX_TG_STREAM_PENDING_FULL] = (
            '{"tool_name":"response","tool_args":{"text":"Latest answer'
        )

        with mock.patch.object(handler, "_send_telegram_live_draft_preview", new=mock.AsyncMock(return_value=True)) as send_draft:
            ok = asyncio.run(handler._flush_telegram_live_preview_once(ctx, token))

        self.assertTrue(ok)
        send_draft.assert_awaited_once_with(ctx, "Latest answer")

    def test_flush_live_preview_does_not_use_native_draft_for_complete_tool_json(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        token = "tok"
        ctx.data[handler.CTX_TG_STREAM_WORKER_TOKEN] = token
        ctx.data[handler.CTX_TG_BOT_CFG] = {"progress": {}}
        ctx.data[handler.CTX_TG_STREAM_PENDING_FULL] = json.dumps({
            "tool_name": "response",
            "tool_args": {"text": "Complete tool JSON", "break_loop": True},
        })

        with mock.patch.object(handler, "_send_telegram_live_draft_preview", new=mock.AsyncMock(return_value=True)) as send_draft, \
             mock.patch.object(handler, "send_telegram_progress_update", new=mock.AsyncMock(return_value=None)) as send_progress:
            ok = asyncio.run(handler._flush_telegram_live_preview_once(ctx, token))

        self.assertTrue(ok)
        send_draft.assert_not_awaited()
        send_progress.assert_awaited_once()

    def test_handle_stream_end_clears_gen_phase(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_PROGRESS_PHASE] = "gen"
        ctx.data[handler.CTX_TG_STREAM_ACTIVE] = True
        ctx.data[handler.CTX_TG_BOT_CFG] = {"progress": {}}
        ctx.data[handler.CTX_TG_PROGRESS_MESSAGE_ID] = 777

        with mock.patch.object(handler, "_schedule_progress_status_refresh", return_value=True) as refresh_progress:
            handler.handle_telegram_response_stream_end(ctx)

        self.assertNotIn(handler.CTX_TG_PROGRESS_PHASE, ctx.data)
        refresh_progress.assert_called_once_with(
            ctx,
            ctx.data[handler.CTX_TG_BOT_CFG],
            require_existing_message=True,
        )

    def test_flush_live_preview_ignores_stale_token(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_STREAM_WORKER_TOKEN] = "new"
        ctx.data[handler.CTX_TG_STREAM_PENDING_FULL] = json.dumps({
            "tool_name": "response",
            "tool_args": {"text": "Latest answer", "break_loop": True},
        })

        with mock.patch.object(handler, "_send_telegram_live_draft_preview", new=mock.AsyncMock()) as send_draft:
            ok = asyncio.run(handler._flush_telegram_live_preview_once(ctx, "old"))

        self.assertFalse(ok)
        send_draft.assert_not_awaited()

    def test_send_initial_progress_status_still_sends_tool_info_progress_in_native_draft_mode(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_CHAT_ID] = 123456
        ctx.data[handler.CTX_TG_BOT_CFG] = {"progress": {}}

        with mock.patch.object(handler, "send_telegram_progress_update", new=mock.AsyncMock()) as send_progress, \
             mock.patch.object(handler.tc, "supports_message_draft", return_value=True):
            asyncio.run(handler._send_initial_progress_status(ctx))

        send_progress.assert_awaited_once()

    def test_send_initial_progress_status_skips_when_detail_off(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_CHAT_ID] = 123456
        ctx.data[handler.CTX_TG_BOT_CFG] = {"telegram_detail_level": "off"}

        with mock.patch.object(handler, "send_telegram_progress_update", new=mock.AsyncMock()) as send_progress, \
             mock.patch.object(handler.detail_status, "effective_detail_level", return_value="off"):
            asyncio.run(handler._send_initial_progress_status(ctx))

        send_progress.assert_not_called()

    def test_handle_message_voice_input_refreshes_progress_for_transcription(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.agent0 = types.SimpleNamespace(
            read_prompt=lambda template, sender, body: body,
            history=types.SimpleNamespace(compress=lambda: False),
        )
        communicated = []
        ctx.communicate = lambda msg: communicated.append(msg)
        message = types.SimpleNamespace(
            text=None,
            caption=None,
            photo=None,
            document=None,
            audio=None,
            video=None,
            video_note=None,
            voice=types.SimpleNamespace(file_id="voice1", file_unique_id="uniq1"),
            reply_to_message=None,
            message_id=55,
            chat=types.SimpleNamespace(id=99, type="private"),
            from_user=types.SimpleNamespace(id=42, username="benji", first_name="Benji", last_name=""),
        )

        class _AsyncBotCM:
            async def __aenter__(self):
                return types.SimpleNamespace(token="t")

            async def __aexit__(self, *a):
                return False

        with mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_is_session_search_pending", return_value=False), \
             mock.patch.object(handler, "_start_typing", return_value=object()), \
             mock.patch.object(handler, "_get_or_create_context", new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(handler, "_send_initial_progress_status", new=mock.AsyncMock(return_value=None)), \
             mock.patch.object(handler, "_refresh_progress_status", new=mock.AsyncMock(return_value=None)) as refresh_progress, \
             mock.patch.object(handler, "_temp_bot", return_value=_AsyncBotCM()), \
             mock.patch.object(handler, "_download_attachments", new=mock.AsyncMock(return_value=["/tmp/voice.ogg"])), \
             mock.patch.object(handler, "_extract_message_content", return_value="[Voice message — see attachment]"), \
             mock.patch.object(handler, "_extract_reply_context", return_value=None), \
             mock.patch.object(handler, "_message_has_voice_input", return_value=True), \
             mock.patch.object(handler.speech, "stt_enabled", return_value=True, create=True), \
             mock.patch.object(handler.speech, "transcribe_audio_file", return_value={"text": "Hallo Welt"}, create=True), \
             mock.patch.object(handler.mq, "log_user_message") as log_user_message, \
             mock.patch.object(handler, "save_tmp_chat") as save_tmp_chat:
            asyncio.run(handler.handle_message(message, "mainbot", {}))

        self.assertEqual(refresh_progress.await_count, 2)
        self.assertEqual(refresh_progress.await_args_list[0].args[1], {})
        self.assertEqual(refresh_progress.await_args_list[1].kwargs["require_existing_message"], True)
        self.assertNotIn(handler.CTX_TG_PROGRESS_PHASE, ctx.data)
        self.assertEqual(ctx.data[handler.CTX_TG_LAST_USER_BODY], "[Voice transcript]\nHallo Welt")
        self.assertEqual(len(communicated), 1)
        log_user_message.assert_called_once()
        save_tmp_chat.assert_called()

    def _reply_context(self, progress_cfg=None):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_BOT] = "mainbot"
        ctx.data[handler.CTX_TG_CHAT_ID] = 123456
        ctx.data[handler.CTX_TG_BOT_CFG] = {
            "progress": {
                "edit_throttle_ms": 0,
                **(progress_cfg or {}),
            }
        }
        ctx.data[handler.CTX_TG_PROGRESS_MESSAGE_ID] = 777
        return ctx

    def _patch_reply_dependencies(
        self,
        handler,
        *,
        edit_ok=True,
        voice_mode="off",
        tts_enabled=False,
        also_send_text=True,
        send_voice_result=999,
    ):
        class _AsyncBotCM:
            async def __aenter__(self):
                return types.SimpleNamespace(token="t")

            async def __aexit__(self, *a):
                return False

        patches = [
            mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="token"))),
            mock.patch.object(handler, "_temp_bot", lambda *a, **k: _AsyncBotCM()),
            mock.patch.object(handler.speech, "voice_reply_settings", return_value={"max_chars": 700}, create=True),
            mock.patch.object(handler.speech, "effective_voice_reply_mode", return_value=voice_mode, create=True),
            mock.patch.object(handler.speech, "tts_enabled", return_value=tts_enabled, create=True),
            mock.patch.object(handler.speech, "effective_also_send_text", return_value=also_send_text, create=True),
            mock.patch.object(handler.speech, "quick_actions_settings", return_value={"enabled": True, "show_text": True}, create=True),
            mock.patch.object(handler.speech, "synthesize_to_voice_file", return_value=("/tmp/reply.ogg", {}), create=True),
            mock.patch.object(handler.tc, "md_to_telegram_html", side_effect=lambda text: text, create=True),
            mock.patch.object(handler.tc, "MAX_MESSAGE_LENGTH", 4096, create=True),
            mock.patch.object(handler.tc, "build_inline_keyboard", return_value={"inline_keyboard": True}, create=True),
            mock.patch.object(handler.tc, "edit_text", new=mock.AsyncMock(return_value=edit_ok), create=True),
            mock.patch.object(handler.tc, "edit_text_with_keyboard", new=mock.AsyncMock(return_value=edit_ok), create=True),
            mock.patch.object(handler.tc, "send_text", new=mock.AsyncMock(return_value=888), create=True),
            mock.patch.object(handler.tc, "send_text_with_keyboard", new=mock.AsyncMock(return_value=888), create=True),
            mock.patch.object(handler.tc, "send_photo", new=mock.AsyncMock(return_value=701), create=True),
            mock.patch.object(handler.tc, "send_animation", new=mock.AsyncMock(return_value=702), create=True),
            mock.patch.object(handler.tc, "send_video", new=mock.AsyncMock(return_value=703), create=True),
            mock.patch.object(handler.tc, "send_video_note", new=mock.AsyncMock(return_value=704), create=True),
            mock.patch.object(handler.tc, "send_file", new=mock.AsyncMock(return_value=705), create=True),
            mock.patch.object(handler.tc, "send_media_group", new=mock.AsyncMock(return_value=[801, 802]), create=True),
            mock.patch.object(handler.tc, "send_location", new=mock.AsyncMock(return_value=706), create=True),
            mock.patch.object(handler.tc, "send_contact", new=mock.AsyncMock(return_value=707), create=True),
            mock.patch.object(handler.tc, "send_venue", new=mock.AsyncMock(return_value=708), create=True),
            mock.patch.object(handler.tc, "is_animation_file", side_effect=lambda path: str(path).lower().endswith(".gif"), create=True),
            mock.patch.object(handler.tc, "is_image_file", side_effect=lambda path: str(path).lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp")), create=True),
            mock.patch.object(handler.tc, "is_video_file", side_effect=lambda path: str(path).lower().endswith((".mp4", ".mov", ".m4v", ".webm")), create=True),
            mock.patch.object(handler.tc, "send_record_voice", new=mock.AsyncMock(return_value=None), create=True),
            mock.patch.object(handler.tc, "send_voice", new=mock.AsyncMock(return_value=send_voice_result), create=True),
            mock.patch.object(handler.tc, "delete_message", new=mock.AsyncMock(return_value=True), create=True),
        ]
        @contextlib.contextmanager
        def _cm():
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                yield

        return _cm()

    def test_send_telegram_reply_edits_progress_into_final_without_completed_cleanup(self):
        handler = self.handler
        ctx = self._reply_context()

        with self._patch_reply_dependencies(handler, edit_ok=True):
            result = asyncio.run(handler.send_telegram_reply(ctx, "Final answer"))
            self.assertIsNone(result)
            handler.tc.edit_text.assert_not_awaited()
            handler.tc.edit_text_with_keyboard.assert_awaited_once()
            edit_args = handler.tc.edit_text_with_keyboard.await_args.args
            self.assertEqual(edit_args[3], "Final answer")
            self.assertEqual(
                [btn["text"] for btn in edit_args[4][0]],
                ["⋯ More"],
            )
            handler.tc.send_text.assert_not_awaited()
            handler.tc.send_text_with_keyboard.assert_not_awaited()
            handler.tc.delete_message.assert_not_awaited()
        self.assertNotIn(handler.CTX_TG_PROGRESS_MESSAGE_ID, ctx.data)

    def test_send_telegram_reply_deletes_progress_when_final_sent_separately(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True

        with self._patch_reply_dependencies(handler, edit_ok=True):
            result = asyncio.run(handler.send_telegram_reply(ctx, "Final answer"))
            self.assertIsNone(result)
            handler.tc.send_text.assert_not_awaited()
            handler.tc.send_text_with_keyboard.assert_awaited_once()
            handler.tc.delete_message.assert_awaited_once()
            deleted_args = handler.tc.delete_message.await_args.args
            self.assertEqual(deleted_args[2], 777)
            self.assertFalse(
                any(
                    "Completed" in str(call.args)
                    for call in handler.tc.edit_text.await_args_list
                )
            )

    def test_send_telegram_reply_auto_voice_without_visible_text_adds_show_text_button(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_LAST_INPUT_WAS_VOICE] = True
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True

        with self._patch_reply_dependencies(
            handler,
            edit_ok=True,
            voice_mode="auto",
            tts_enabled=True,
            also_send_text=False,
        ):
            result = asyncio.run(handler.send_telegram_reply(ctx, "Final answer"))
            self.assertIsNone(result)
            handler.tc.send_voice.assert_awaited_once()
            handler.tc.send_text.assert_not_awaited()
            handler.tc.send_text_with_keyboard.assert_not_awaited()

            voice_kwargs = handler.tc.send_voice.await_args.kwargs
            self.assertIsNotNone(voice_kwargs.get("buttons"))
            self.assertEqual(voice_kwargs["buttons"][0][0]["text"], "📝 Show text")
            self.assertTrue(
                voice_kwargs["buttons"][0][0]["callback_data"].startswith(
                    f"{handler.TG_UI_CALLBACK_PREFIX}qa|show_text:"
                )
            )
            self.assertEqual(
                [btn["text"] for btn in voice_kwargs["buttons"][1]],
                ["⋯ More"],
            )

    def test_send_telegram_reply_refreshes_progress_for_tts_phase(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_LAST_INPUT_WAS_VOICE] = True
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True

        with self._patch_reply_dependencies(
            handler,
            edit_ok=True,
            voice_mode="auto",
            tts_enabled=True,
            also_send_text=False,
        ), mock.patch.object(handler, "_refresh_progress_status", new=mock.AsyncMock(return_value=None)) as refresh_progress:
            result = asyncio.run(handler.send_telegram_reply(ctx, "Final answer"))
            self.assertIsNone(result)
            refresh_progress.assert_awaited_once_with(
                ctx,
                ctx.data[handler.CTX_TG_BOT_CFG],
                require_existing_message=True,
            )
            self.assertNotIn(handler.CTX_TG_PROGRESS_PHASE, ctx.data)

    def test_send_telegram_reply_replaces_typing_with_record_voice_worker_during_tts(self):
        handler = self.handler
        voice_key = getattr(handler, "CTX_TG_RECORD_VOICE_STOP", "_telegram_record_voice_stop")
        typing_stop = mock.Mock()
        voice_stop = types.SimpleNamespace(set=mock.Mock())
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_LAST_INPUT_WAS_VOICE] = True
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True
        ctx.data[handler.CTX_TG_TYPING_STOP] = types.SimpleNamespace(set=typing_stop)

        with self._patch_reply_dependencies(
            handler,
            edit_ok=True,
            voice_mode="auto",
            tts_enabled=True,
            also_send_text=False,
        ), mock.patch.object(handler, "_start_record_voice", return_value=voice_stop, create=True) as start_voice:
            result = asyncio.run(handler.send_telegram_reply(ctx, "Final answer"))
            self.assertIsNone(result)
            start_voice.assert_called_once_with("token", 123456)
            typing_stop.assert_called_once_with()
            voice_stop.set.assert_called_once_with()
            self.assertNotIn(handler.CTX_TG_TYPING_STOP, ctx.data)
            self.assertNotIn(voice_key, ctx.data)

    def test_send_telegram_progress_update_does_not_rearm_typing_during_tts(self):
        handler = self.handler
        ctx = self._reply_context()
        voice_key = getattr(handler, "CTX_TG_RECORD_VOICE_STOP", "_telegram_record_voice_stop")
        ctx.data.pop(handler.CTX_TG_PROGRESS_MESSAGE_ID, None)
        ctx.data[handler.CTX_TG_PROGRESS_PHASE] = "tts"
        ctx.data[voice_key] = object()

        class _AsyncBotCM:
            async def __aenter__(self):
                return types.SimpleNamespace(token="t")

            async def __aexit__(self, *a):
                return False

        with mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="token"))), \
             mock.patch.object(handler, "_temp_bot", lambda *a, **k: _AsyncBotCM()), \
             mock.patch.object(handler.tc, "md_to_telegram_html", side_effect=lambda text: text, create=True), \
             mock.patch.object(handler.tc, "MAX_MESSAGE_LENGTH", 4096, create=True), \
             mock.patch.object(handler.tc, "send_text", new=mock.AsyncMock(return_value=888), create=True), \
             mock.patch.object(handler.tc, "send_typing", new=mock.AsyncMock(return_value=None), create=True) as send_typing:
            result = asyncio.run(handler.send_telegram_progress_update(ctx, "Still working"))

        self.assertIsNone(result)
        send_typing.assert_not_awaited()

    def test_send_telegram_reply_voice_only_edits_progress_with_voice_completion_copy(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "edit"})
        ctx.data[handler.CTX_TG_LAST_INPUT_WAS_VOICE] = True
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True

        with self._patch_reply_dependencies(
            handler,
            edit_ok=True,
            voice_mode="auto",
            tts_enabled=True,
            also_send_text=False,
        ):
            result = asyncio.run(handler.send_telegram_reply(ctx, "Final answer"))
            self.assertIsNone(result)
            handler.tc.send_voice.assert_awaited_once()
            handler.tc.send_text.assert_not_awaited()
            handler.tc.send_text_with_keyboard.assert_not_awaited()
            self.assertGreaterEqual(handler.tc.edit_text.await_count, 1)
            self.assertEqual(
                handler.tc.edit_text.await_args_list[-1].args[3],
                "🎙 Voice reply sent",
            )

    def test_send_telegram_reply_auto_voice_with_visible_text_skips_show_text_button(self):
        handler = self.handler
        ctx = self._reply_context()
        ctx.data[handler.CTX_TG_LAST_INPUT_WAS_VOICE] = True

        with self._patch_reply_dependencies(
            handler,
            edit_ok=True,
            voice_mode="auto",
            tts_enabled=True,
            also_send_text=True,
        ):
            result = asyncio.run(handler.send_telegram_reply(ctx, "Final answer"))
            self.assertIsNone(result)
            handler.tc.send_voice.assert_awaited_once()
            self.assertIsNone(handler.tc.send_voice.await_args.kwargs.get("buttons"))
            handler.tc.edit_text_with_keyboard.assert_awaited_once()

    def test_send_telegram_reply_voice_only_still_adds_show_text_button(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True
        ctx.data[handler.CTX_TG_VOICE_CONVERSATION_MODE] = "voice_only"

        with self._patch_reply_dependencies(
            handler,
            edit_ok=True,
            voice_mode="force",
            tts_enabled=True,
            also_send_text=False,
        ):
            result = asyncio.run(handler.send_telegram_reply(ctx, "Final answer"))
            self.assertIsNone(result)
            handler.tc.send_voice.assert_awaited_once()
            self.assertEqual(
                handler.tc.send_voice.await_args.kwargs["buttons"][0][0]["text"],
                "📝 Show text",
            )
            handler.tc.send_text.assert_not_awaited()
            self.assertEqual(
                [btn["text"] for btn in handler.tc.send_voice.await_args.kwargs["buttons"][1]],
                ["⋯ More"],
            )

    def test_send_telegram_reply_empty_text_body_skips_show_text_button(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True
        ctx.data[handler.CTX_TG_LAST_INPUT_WAS_VOICE] = True

        with self._patch_reply_dependencies(
            handler,
            edit_ok=True,
            voice_mode="auto",
            tts_enabled=True,
            also_send_text=False,
        ):
            result = asyncio.run(handler.send_telegram_reply(ctx, ""))
            self.assertIsNone(result)
            handler.tc.send_voice.assert_not_awaited()
            handler.tc.send_text.assert_not_awaited()
            self.assertEqual(ctx.data.get(handler.CTX_TG_LAST_TEXT_RESPONSE, None), "")
            self.assertNotIn(handler.CTX_TG_LAST_TEXT_RESPONSE_TOKEN, ctx.data)
            self.assertFalse(ctx.data.get(handler.CTX_TG_FINAL_REPLY_DELIVERED))

    def test_send_telegram_inline_response_sends_separate_message_without_touching_progress(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})

        with self._patch_reply_dependencies(handler, edit_ok=True):
            result = asyncio.run(
                handler.send_telegram_inline_response(
                    ctx,
                    "Working",
                    keyboard=[[{"text": "Open", "url": "https://example.com"}]],
                )
            )
            self.assertIsNone(result)
            handler.tc.send_text_with_keyboard.assert_awaited_once()
            handler.tc.edit_text.assert_not_awaited()
            handler.tc.delete_message.assert_not_awaited()

        self.assertEqual(ctx.data[handler.CTX_TG_PROGRESS_MESSAGE_ID], 777)

    def test_send_telegram_reply_uses_media_group_for_multiple_visual_attachments(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True

        with self._patch_reply_dependencies(handler, edit_ok=True):
            result = asyncio.run(
                handler.send_telegram_reply(
                    ctx,
                    "",
                    attachments=["/tmp/a.jpg", "/tmp/b.png"],
                )
            )
            self.assertIsNone(result)
            handler.tc.send_media_group.assert_awaited_once()
            handler.tc.send_photo.assert_not_awaited()
            handler.tc.send_file.assert_not_awaited()
            handler.tc.send_text.assert_not_awaited()

    def test_send_telegram_reply_media_group_falls_back_to_single_sends(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True

        with self._patch_reply_dependencies(handler, edit_ok=True), \
             mock.patch.object(handler.tc, "send_media_group", new=mock.AsyncMock(return_value=None), create=True):
            result = asyncio.run(
                handler.send_telegram_reply(
                    ctx,
                    "",
                    attachments=["/tmp/a.jpg", "/tmp/b.png"],
                )
            )
            self.assertIsNone(result)
            self.assertEqual(handler.tc.send_photo.await_count, 2)
            handler.tc.send_file.assert_not_awaited()

    def test_send_telegram_reply_single_photo_uses_caption_without_extra_text_message(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True

        with self._patch_reply_dependencies(handler, edit_ok=True):
            result = asyncio.run(
                handler.send_telegram_reply(
                    ctx,
                    "Here is the preview",
                    attachments=["/tmp/a.jpg"],
                )
            )
            self.assertIsNone(result)
            self.assertEqual(handler.tc.send_photo.await_args.kwargs["caption"], "Here is the preview")
            handler.tc.send_text.assert_not_awaited()
            self.assertEqual(handler.tc.send_photo.await_args.kwargs["reply_markup"], {"inline_keyboard": True})

    def test_send_telegram_reply_attachment_only_edits_progress_with_artifact_completion_copy(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "edit"})
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True

        with self._patch_reply_dependencies(handler, edit_ok=True):
            result = asyncio.run(
                handler.send_telegram_reply(
                    ctx,
                    "",
                    attachments=["/tmp/a.jpg", "/tmp/b.png"],
                )
            )
            self.assertIsNone(result)
            handler.tc.send_media_group.assert_awaited_once()
            handler.tc.send_text.assert_not_awaited()
            handler.tc.edit_text.assert_awaited_once()
            self.assertEqual(
                handler.tc.edit_text.await_args.args[3],
                "📎 Sent 2 attachments",
            )

    def test_send_telegram_reply_single_photo_with_keyboard_uses_media_as_the_keyboard_carrier(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True

        with self._patch_reply_dependencies(handler, edit_ok=True):
            result = asyncio.run(
                handler.send_telegram_reply(
                    ctx,
                    "Open this image",
                    attachments=["/tmp/a.jpg"],
                    keyboard=[[{"text": "Open", "url": "https://example.com"}]],
                )
            )
            self.assertIsNone(result)
            self.assertEqual(handler.tc.send_photo.await_args.kwargs["caption"], "Open this image")
            self.assertEqual(handler.tc.send_photo.await_args.kwargs["reply_markup"], {"inline_keyboard": True})
            handler.tc.send_text.assert_not_awaited()
            handler.tc.send_text_with_keyboard.assert_not_awaited()

    def test_send_telegram_reply_multi_media_keyboard_without_text_uses_short_companion_message(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True

        with self._patch_reply_dependencies(handler, edit_ok=True):
            result = asyncio.run(
                handler.send_telegram_reply(
                    ctx,
                    "",
                    attachments=["/tmp/a.jpg", "/tmp/b.jpg"],
                    keyboard=[[{"text": "Next", "callback_data": "next"}]],
                )
            )
            self.assertIsNone(result)
            handler.tc.send_media_group.assert_awaited_once()
            self.assertEqual(handler.tc.send_text_with_keyboard.await_args.args[2], "Choose an option:")

    def test_handle_callback_query_response_continue_dispatches_follow_up_turn(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data[handler.CTX_TG_LAST_RESPONSE_ACTION_TOKEN] = "resp123"
        ctx.data[handler.CTX_TG_CHAT_ID] = 99
        ctx.data[handler.CTX_TG_BOT] = "mainbot"
        ctx.data[handler.CTX_TG_BOT_CFG] = {}
        ctx.agent0 = types.SimpleNamespace(
            read_prompt=lambda template, sender, body: f"{sender}|{body}",
            history=types.SimpleNamespace(compress=lambda: False),
        )
        communicated = []
        ctx.communicate = lambda msg: communicated.append(msg)
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji", first_name="Benji", last_name=""),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}ra|continue:resp123",
            message=types.SimpleNamespace(
                message_id=77,
                chat=types.SimpleNamespace(id=99, type="private"),
            ),
            answer=mock.AsyncMock(),
        )

        with mock.patch.object(handler, "_load_state", return_value={"chats": {handler._map_key("mainbot", 42, 99): ctx.id}}), \
             mock.patch.object(handler, "_send_initial_progress_status", new=mock.AsyncMock(return_value=None)), \
             mock.patch.object(handler, "_start_typing", return_value=object()), \
             mock.patch.object(handler.mq, "log_user_message") as log_user_message, \
             mock.patch.object(handler, "save_tmp_chat") as save_tmp_chat:
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        query.answer.assert_awaited_once_with("Continuing")
        self.assertEqual(ctx.data[handler.CTX_TG_LAST_USER_BODY], "Continue from here.")
        self.assertEqual(ctx.data[handler.CTX_TG_LAST_INPUT_WAS_VOICE], False)
        self.assertEqual(ctx.data[handler.CTX_TG_REPLY_TO], None)
        self.assertEqual(len(communicated), 1)
        self.assertEqual(communicated[0].message, "Benji (@benji)|Continue from here.")
        log_user_message.assert_called_once()
        save_tmp_chat.assert_called()

    def test_handle_callback_query_response_transform_dispatches_follow_up_turn(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data[handler.CTX_TG_LAST_RESPONSE_ACTION_TOKEN] = "resp123"
        ctx.data[handler.CTX_TG_LAST_TEXT_RESPONSE] = "Use the queue worker and retry policy."
        ctx.data[handler.CTX_TG_CHAT_ID] = 99
        ctx.data[handler.CTX_TG_BOT] = "mainbot"
        ctx.data[handler.CTX_TG_BOT_CFG] = {}
        ctx.agent0 = types.SimpleNamespace(
            read_prompt=lambda template, sender, body: f"{sender}|{body}",
            history=types.SimpleNamespace(compress=lambda: False),
        )
        communicated = []
        ctx.communicate = lambda msg: communicated.append(msg)
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji", first_name="Benji", last_name=""),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}ra|shorter:resp123",
            message=types.SimpleNamespace(
                message_id=77,
                chat=types.SimpleNamespace(id=99, type="private"),
            ),
            answer=mock.AsyncMock(),
        )

        with mock.patch.object(handler, "_load_state", return_value={"chats": {handler._map_key("mainbot", 42, 99): ctx.id}}), \
             mock.patch.object(handler, "_send_initial_progress_status", new=mock.AsyncMock(return_value=None)), \
             mock.patch.object(handler, "_start_typing", return_value=object()), \
             mock.patch.object(handler.mq, "log_user_message") as log_user_message, \
             mock.patch.object(handler, "save_tmp_chat") as save_tmp_chat:
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        expected_body = handler._build_response_transform_body(
            "shorter",
            "Use the queue worker and retry policy.",
        )
        query.answer.assert_awaited_once_with("Shortening")
        self.assertEqual(ctx.data[handler.CTX_TG_LAST_USER_BODY], expected_body)
        self.assertEqual(ctx.data[handler.CTX_TG_LAST_INPUT_WAS_VOICE], False)
        self.assertEqual(ctx.data[handler.CTX_TG_REPLY_TO], None)
        self.assertEqual(len(communicated), 1)
        self.assertEqual(communicated[0].message, f"Benji (@benji)|{expected_body}")
        log_user_message.assert_called_once()
        save_tmp_chat.assert_called()

    def test_handle_callback_query_response_transform_requires_source_text(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data[handler.CTX_TG_LAST_RESPONSE_ACTION_TOKEN] = "resp123"
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji", first_name="Benji", last_name=""),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}ra|longer:resp123",
            message=types.SimpleNamespace(
                message_id=77,
                chat=types.SimpleNamespace(id=99, type="private"),
            ),
            answer=mock.AsyncMock(),
        )

        with mock.patch.object(handler, "_load_state", return_value={"chats": {handler._map_key("mainbot", 42, 99): ctx.id}}), \
             mock.patch.object(handler.mq, "log_user_message") as log_user_message:
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        query.answer.assert_awaited_once_with("Answer is no longer available.")
        log_user_message.assert_not_called()

    def test_handle_callback_query_response_action_rejects_stale_token(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data[handler.CTX_TG_LAST_RESPONSE_ACTION_TOKEN] = "fresh123"
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji"),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}ra|retry:stale999",
            message=types.SimpleNamespace(
                message_id=77,
                chat=types.SimpleNamespace(id=99, type="private"),
            ),
            answer=mock.AsyncMock(),
        )

        with mock.patch.object(handler, "_load_state", return_value={"chats": {handler._map_key("mainbot", 42, 99): ctx.id}}), \
             mock.patch.object(handler.mq, "log_user_message") as log_user_message:
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        query.answer.assert_awaited_once_with("Action is no longer available.")
        log_user_message.assert_not_called()

    def test_handle_actions_without_arg_shows_inline_picker(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data = {}
        message = types.SimpleNamespace(
            text="/actions",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji"),
        )
        sent = []
        saved = []

        with mock.patch.object(handler, "_get_or_create_context", new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "save_tmp_chat", side_effect=lambda current: saved.append(current)), \
             mock.patch.object(handler.speech, "effective_reply_actions_enabled", return_value=True), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *args, **kwargs: sent.append((args, kwargs)))):
            asyncio.run(handler.handle_actions(message, "mainbot", {}))

        self.assertEqual(saved, [ctx])
        self.assertIn("Reply actions: on", sent[-1][0][2])
        keyboard = sent[-1][1]["keyboard"]
        self.assertEqual(keyboard[0][0]["callback_data"], f"{handler.TG_UI_CALLBACK_PREFIX}a|on")
        self.assertEqual(keyboard[0][1]["callback_data"], f"{handler.TG_UI_CALLBACK_PREFIX}a|off")

    def test_handle_actions_sets_session_toggle(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data = {}
        message = types.SimpleNamespace(
            text="/actions off",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji"),
        )
        sent = []
        saved = []

        with mock.patch.object(handler, "_get_or_create_context", new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "save_tmp_chat", side_effect=lambda current: saved.append(current)), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *args, **kwargs: sent.append((args, kwargs)))):
            asyncio.run(handler.handle_actions(message, "mainbot", {}))

        self.assertEqual(ctx.data[handler.CTX_TG_REPLY_ACTIONS_SESSION], "off")
        self.assertEqual(saved, [ctx])
        self.assertIn("Reply actions: off", sent[-1][0][2])

    def test_handle_callback_query_actions_toggle_sets_session_override(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data = {}
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji"),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}a|off",
            message=types.SimpleNamespace(
                message_id=77,
                chat=types.SimpleNamespace(id=99, type="private"),
            ),
            answer=mock.AsyncMock(),
        )
        sent = []
        saved = []

        with mock.patch.object(handler, "_load_state", return_value={"chats": {handler._map_key("mainbot", 42, 99): ctx.id}}), \
             mock.patch.object(handler, "save_tmp_chat", side_effect=lambda current: saved.append(current)), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *args, **kwargs: sent.append((args, kwargs)))):
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        self.assertEqual(ctx.data[handler.CTX_TG_REPLY_ACTIONS_SESSION], "off")
        self.assertEqual(saved, [ctx])
        query.answer.assert_awaited_once_with("OK")
        self.assertIn("Reply actions: off", sent[-1][0][2])

    def test_handle_detail_without_arg_shows_smart_inline_picker(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data = {handler.CTX_TG_DETAIL_LEVEL_SESSION: "smart"}
        message = types.SimpleNamespace(
            text="/detail",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji"),
        )
        sent = []
        saved = []

        with mock.patch.object(handler, "_get_or_create_context", new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "save_tmp_chat", side_effect=lambda current: saved.append(current)), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *args, **kwargs: sent.append((args, kwargs)))):
            asyncio.run(handler.handle_detail(message, "mainbot", {}))

        self.assertEqual(saved, [ctx])
        self.assertIn("Tool detail: smart", sent[-1][0][2])
        keyboard = sent[-1][1]["keyboard"]
        self.assertEqual(keyboard[0][0]["callback_data"], f"{handler.TG_UI_CALLBACK_PREFIX}d|off")
        self.assertEqual(keyboard[0][1]["callback_data"], f"{handler.TG_UI_CALLBACK_PREFIX}d|info")
        self.assertEqual(keyboard[0][2]["callback_data"], f"{handler.TG_UI_CALLBACK_PREFIX}d|smart")
        self.assertEqual(keyboard[0][3]["callback_data"], f"{handler.TG_UI_CALLBACK_PREFIX}d|debug")

    def test_handle_detail_sets_smart_session_level(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data = {}
        message = types.SimpleNamespace(
            text="/detail smart",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji"),
        )
        sent = []
        saved = []

        with mock.patch.object(handler, "_get_or_create_context", new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "save_tmp_chat", side_effect=lambda current: saved.append(current)), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *args, **kwargs: sent.append((args, kwargs)))):
            asyncio.run(handler.handle_detail(message, "mainbot", {}))

        self.assertEqual(ctx.data[handler.CTX_TG_DETAIL_LEVEL_SESSION], "smart")
        self.assertEqual(saved, [ctx])
        self.assertIn("Detail level: smart.", sent[-1][0][2])

    def test_handle_callback_query_detail_smart_sets_session_override(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data = {}
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji"),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}d|smart",
            message=types.SimpleNamespace(
                message_id=77,
                chat=types.SimpleNamespace(id=99, type="private"),
            ),
            answer=mock.AsyncMock(),
        )
        sent = []
        saved = []

        with mock.patch.object(handler, "_load_state", return_value={"chats": {handler._map_key("mainbot", 42, 99): ctx.id}}), \
             mock.patch.object(handler, "save_tmp_chat", side_effect=lambda current: saved.append(current)), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *args, **kwargs: sent.append((args, kwargs)))):
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        self.assertEqual(ctx.data[handler.CTX_TG_DETAIL_LEVEL_SESSION], "smart")
        self.assertEqual(saved, [ctx])
        query.answer.assert_awaited_once_with("OK")
        self.assertIn("Detail level: smart.", sent[-1][0][2])

    def test_handle_detail_before_without_arg_shows_inline_picker(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data = {handler.CTX_TG_DETAIL_BEFORE_SESSION: "on"}
        message = types.SimpleNamespace(
            text="/detail_before",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji"),
        )
        sent = []
        saved = []

        with mock.patch.object(handler, "_get_or_create_context", new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "save_tmp_chat", side_effect=lambda current: saved.append(current)), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *args, **kwargs: sent.append((args, kwargs)))):
            asyncio.run(handler.handle_detail_before(message, "mainbot", {}))

        self.assertEqual(saved, [ctx])
        self.assertIn("Tool start updates: on", sent[-1][0][2])
        keyboard = sent[-1][1]["keyboard"]
        self.assertEqual(keyboard[0][0]["callback_data"], f"{handler.TG_UI_CALLBACK_PREFIX}db|on")
        self.assertEqual(keyboard[0][1]["callback_data"], f"{handler.TG_UI_CALLBACK_PREFIX}db|off")

    def test_handle_detail_before_sets_session_toggle(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data = {}
        message = types.SimpleNamespace(
            text="/detail_before off",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji"),
        )
        sent = []
        saved = []

        with mock.patch.object(handler, "_get_or_create_context", new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "save_tmp_chat", side_effect=lambda current: saved.append(current)), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *args, **kwargs: sent.append((args, kwargs)))):
            asyncio.run(handler.handle_detail_before(message, "mainbot", {}))

        self.assertEqual(ctx.data[handler.CTX_TG_DETAIL_BEFORE_SESSION], "off")
        self.assertEqual(saved, [ctx])
        self.assertIn("Tool start updates: off", sent[-1][0][2])

    def test_handle_callback_query_detail_before_toggle_sets_session_override(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data = {}
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji"),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}db|on",
            message=types.SimpleNamespace(
                message_id=77,
                chat=types.SimpleNamespace(id=99, type="private"),
            ),
            answer=mock.AsyncMock(),
        )
        sent = []
        saved = []

        with mock.patch.object(handler, "_load_state", return_value={"chats": {handler._map_key("mainbot", 42, 99): ctx.id}}), \
             mock.patch.object(handler, "save_tmp_chat", side_effect=lambda current: saved.append(current)), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *args, **kwargs: sent.append((args, kwargs)))):
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        self.assertEqual(ctx.data[handler.CTX_TG_DETAIL_BEFORE_SESSION], "on")
        self.assertEqual(saved, [ctx])
        query.answer.assert_awaited_once_with("OK")
        self.assertIn("Tool start updates: on", sent[-1][0][2])

    def test_handle_callback_query_more_open_replaces_keyboard_with_transform_menu(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data[handler.CTX_TG_LAST_RESPONSE_ACTION_TOKEN] = "resp123"
        ctx.data[handler.CTX_TG_LAST_TEXT_RESPONSE] = "Use the queue worker and retry policy."
        edit_reply_markup = mock.AsyncMock()
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji"),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}rm|open:resp123:1",
            message=types.SimpleNamespace(
                message_id=77,
                chat=types.SimpleNamespace(id=99, type="private"),
                edit_reply_markup=edit_reply_markup,
            ),
            answer=mock.AsyncMock(),
        )

        with mock.patch.object(handler, "_load_state", return_value={"chats": {handler._map_key("mainbot", 42, 99): ctx.id}}):
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        query.answer.assert_awaited_once_with("More")
        keyboard = edit_reply_markup.await_args.kwargs["reply_markup"]
        rows = keyboard["inline_keyboard"]
        self.assertEqual(rows[0][0]["text"], "📝 Show text")
        self.assertEqual(rows[1][0]["text"], "✂️ Shorter")
        self.assertEqual(rows[1][1]["text"], "📏 Longer")
        self.assertEqual(rows[2][0]["text"], "🎙 To voice")
        self.assertEqual(rows[3][0]["text"], "⬅ Back")

    def test_handle_callback_query_to_voice_sends_voice_reply(self):
        handler = self.handler
        voice_key = getattr(handler, "CTX_TG_RECORD_VOICE_STOP", "_telegram_record_voice_stop")
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data[handler.CTX_TG_LAST_RESPONSE_ACTION_TOKEN] = "resp123"
        ctx.data[handler.CTX_TG_LAST_TEXT_RESPONSE] = "Use the queue worker and retry policy."
        ctx.data[handler.CTX_TG_BOT] = "mainbot"
        ctx.data[handler.CTX_TG_BOT_CFG] = {}
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji"),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}ra|to_voice:resp123",
            message=types.SimpleNamespace(
                message_id=77,
                chat=types.SimpleNamespace(id=99, type="private"),
            ),
            answer=mock.AsyncMock(),
        )

        class _BotCtx:
            async def __aenter__(self):
                return types.SimpleNamespace()
            async def __aexit__(self, exc_type, exc, tb):
                return False

        voice_stop = types.SimpleNamespace(set=mock.Mock())

        with mock.patch.object(handler, "_load_state", return_value={"chats": {handler._map_key("mainbot", 42, 99): ctx.id}}), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_temp_bot", return_value=_BotCtx()), \
             mock.patch.object(handler.speech, "tts_enabled", return_value=True), \
             mock.patch.object(handler.speech, "voice_reply_settings", return_value={"max_chars": 700}), \
             mock.patch.object(handler, "_start_record_voice", return_value=voice_stop, create=True) as start_voice, \
             mock.patch.object(handler.tc, "send_voice", new=mock.AsyncMock(return_value=900)) as send_voice, \
             mock.patch.object(handler.asyncio, "to_thread", new=mock.AsyncMock(return_value=("/tmp/fake.ogg", {}))), \
             mock.patch.object(handler.os.path, "isfile", return_value=False):
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        query.answer.assert_awaited_once_with("Sent as voice")
        start_voice.assert_called_once_with("tok", 99)
        voice_stop.set.assert_called_once_with()
        send_voice.assert_awaited_once()
        self.assertEqual(send_voice.await_args.kwargs["reply_to_message_id"], 77)
        self.assertNotIn(voice_key, ctx.data)

    def test_handle_title_sets_manual_chat_title_and_lock(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Old title")
        ctx.data = {}
        message = types.SimpleNamespace(
            text="/title Shipping dashboard",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji"),
        )
        sent = []
        saved = []
        dirty = []

        state_monitor = sys.modules["helpers.state_monitor_integration"]
        state_monitor.mark_dirty_all = lambda **kwargs: dirty.append(kwargs)

        with mock.patch.object(handler, "_get_or_create_context", new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "save_tmp_chat", side_effect=lambda current: saved.append(current)), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *args, **kwargs: sent.append((args, kwargs)))):
            asyncio.run(handler.handle_title(message, "mainbot", {}))

        self.assertEqual(ctx.name, "Shipping dashboard")
        self.assertTrue(ctx.data["chat_rename_manual_lock"])
        self.assertEqual(saved, [ctx])
        self.assertEqual(dirty[-1]["reason"], "plugins.telegram_integration_voice.title.set")
        self.assertIn("Session title set to: Shipping dashboard", sent[-1][0][2])

    def test_handle_title_auto_clears_manual_title_and_lock(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data = {"chat_rename_manual_lock": True}
        message = types.SimpleNamespace(
            text="/title auto",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji"),
        )
        sent = []
        saved = []
        dirty = []

        state_monitor = sys.modules["helpers.state_monitor_integration"]
        state_monitor.mark_dirty_all = lambda **kwargs: dirty.append(kwargs)

        with mock.patch.object(handler, "_get_or_create_context", new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "save_tmp_chat", side_effect=lambda current: saved.append(current)), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *args, **kwargs: sent.append((args, kwargs)))):
            asyncio.run(handler.handle_title(message, "mainbot", {}))

        self.assertIsNone(ctx.name)
        self.assertNotIn("chat_rename_manual_lock", ctx.data)
        self.assertEqual(saved, [ctx])
        self.assertEqual(dirty[-1]["reason"], "plugins.telegram_integration_voice.title.clear")
        self.assertIn("Session title reset to automatic naming.", sent[-1][0][2])

    def test_handle_title_without_argument_reports_current_manual_title(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="Shipping dashboard")
        ctx.data = {"chat_rename_manual_lock": True}
        message = types.SimpleNamespace(
            text="/title",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji"),
        )
        sent = []

        with mock.patch.object(handler, "_get_or_create_context", new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *args, **kwargs: sent.append((args, kwargs)))):
            asyncio.run(handler.handle_title(message, "mainbot", {}))

        self.assertIn("Current title: Shipping dashboard", sent[-1][0][2])
        self.assertIn("/title auto", sent[-1][0][2])

    # --- Session delete (button-driven) ----------------------------------

    def test_session_details_keyboard_includes_delete_button(self):
        """Details keyboard now exposes a button-driven delete flow."""
        handler = self.handler
        meta = {
            "id": "abc",
            "display_name": "Old chat",
            "telegram_binding": "bound",
            "last_message": "2026-01-01T00:00:00",
            "data": {},
        }
        keyboard = handler._session_details_keyboard(meta, active_ctx_id="other")
        flat = [btn for row in keyboard for btn in row]
        delete_buttons = [b for b in flat if b["text"] == "🗑 Delete"]
        self.assertEqual(len(delete_buttons), 1)
        self.assertTrue(delete_buttons[0]["callback_data"].endswith("|abc"))

    def test_session_delete_confirm_keyboard_has_yes_and_cancel(self):
        handler = self.handler
        keyboard = handler._session_delete_confirm_keyboard("abc")
        flat = [btn for row in keyboard for btn in row]
        texts = [b["text"] for b in flat]
        self.assertEqual(texts, ["🗑 Yes, delete", "⬅️ Cancel"])
        cb_datas = [b["callback_data"] for b in flat]
        self.assertTrue(any("|abc" in c for c in cb_datas))
        # Yes callback must be sdy|, cancel must be sdn|
        yes_btn = next(b for b in flat if b["text"] == "🗑 Yes, delete")
        cancel_btn = next(b for b in flat if b["text"] == "⬅️ Cancel")
        self.assertIn("sdy|", yes_btn["callback_data"])
        self.assertIn("sdn|", cancel_btn["callback_data"])

    def test_session_delete_confirm_text_warns_about_new_chat_when_active(self):
        handler = self.handler
        meta = {
            "id": "active",
            "display_name": "Current chat",
            "telegram_binding": "bound",
            "last_message": "2026-01-01T00:00:00",
            "data": {},
        }
        text = handler._session_delete_confirm_text(meta, active_ctx_id="active")
        self.assertIn("Current chat", text)
        self.assertIn("new session", text.lower())
        self.assertIn("cannot be undone", text.lower())

    def test_session_delete_confirm_text_is_short_for_inactive_sessions(self):
        handler = self.handler
        meta = {
            "id": "old",
            "display_name": "Old chat",
            "telegram_binding": "bound",
            "last_message": "2026-01-01T00:00:00",
            "data": {},
        }
        text = handler._session_delete_confirm_text(meta)
        self.assertIn("Old chat", text)
        self.assertNotIn("new session", text.lower())

    def test_delete_session_for_user_bound_active_removes_file_and_clears_state(self):
        """Deleting the active bound session removes the file, drops the in-memory context and clears the state mapping."""
        handler = self.handler
        ctx = _DummyAgentContext(name="Active chat")
        _DummyAgentContext.registry[ctx.id] = ctx
        meta = {
            "id": ctx.id,
            "display_name": "Active chat",
            "telegram_binding": "bound",
            "last_message": "2026-01-01T00:00:00",
            "data": {
                handler.CTX_TG_BOT: "mainbot",
                handler.CTX_TG_USER_ID: 42,
                handler.CTX_TG_CHAT_ID: 99,
            },
        }
        saved_states = []
        removed_ids = []
        dirty = []

        with mock.patch.object(handler, "_list_switchable_sessions", return_value=[meta]), \
             mock.patch.object(handler, "_read_persisted_chat_meta", return_value=meta), \
             mock.patch.object(handler, "_mapped_context_id", return_value=ctx.id), \
             mock.patch.object(handler, "_load_state", return_value={"chats": {"mainbot:42:99": ctx.id}}), \
             mock.patch.object(handler, "_save_state", side_effect=lambda s: saved_states.append(s.copy())), \
             mock.patch.object(handler, "remove_chat", side_effect=lambda cid: removed_ids.append(cid)) as remove_chat_mock, \
             mock.patch.object(handler, "_mark_chat_state_dirty", side_effect=lambda r: dirty.append(r)):
            ok, msg, was_active = handler._delete_session_for_user("mainbot", 42, 99, ctx.id)

        self.assertTrue(ok)
        self.assertTrue(was_active)
        self.assertIn("Active chat", msg)
        # In-memory context was reset and removed from the AgentContext registry
        self.assertTrue(ctx.reset_called)
        self.assertTrue(ctx.killed)
        self.assertTrue(ctx.removed)
        self.assertNotIn(ctx.id, _DummyAgentContext.registry)
        # persist_chat.remove_chat was called for the right ctx_id
        remove_chat_mock.assert_called_once_with(ctx.id)
        self.assertEqual(removed_ids, [ctx.id])
        # state.json chats mapping was cleared for this (bot, user, chat)
        self.assertEqual(saved_states[-1]["chats"], {})
        # State monitor was notified so A0's WebUI refreshes
        self.assertEqual(dirty, ["plugins.telegram_integration_voice.session.delete"])

    def test_delete_session_for_user_unbound_owned_removes_file(self):
        """Unbound web session whose CTX_TG_USER_ID matches the current user is deletable."""
        handler = self.handler
        meta = {
            "id": "web-1",
            "display_name": "Web chat",
            "telegram_binding": "unbound",
            "last_message": "2026-01-01T00:00:00",
            "data": {
                handler.CTX_TG_BOT: "mainbot",
                handler.CTX_TG_USER_ID: 42,
                handler.CTX_TG_CHAT_ID: 0,
            },
        }
        saved_states = []
        removed_ids = []
        dirty = []

        with mock.patch.object(handler, "_list_switchable_sessions", return_value=[meta]), \
             mock.patch.object(handler, "_read_persisted_chat_meta", return_value=meta), \
             mock.patch.object(handler, "_mapped_context_id", return_value="other"), \
             mock.patch.object(handler, "_load_state", return_value={"chats": {"mainbot:42:99": "other"}}), \
             mock.patch.object(handler, "_save_state", side_effect=lambda s: saved_states.append(s.copy())), \
             mock.patch.object(handler, "remove_chat", side_effect=lambda cid: removed_ids.append(cid)) as remove_chat_mock, \
             mock.patch.object(handler, "_mark_chat_state_dirty", side_effect=lambda r: dirty.append(r)):
            ok, msg, was_active = handler._delete_session_for_user("mainbot", 42, 99, "web-1")

        self.assertTrue(ok)
        self.assertFalse(was_active)
        # Active mapping was NOT touched (we are not the active session)
        self.assertEqual(saved_states, [])
        # persist_chat.remove_chat was called for the right ctx_id
        remove_chat_mock.assert_called_once_with("web-1")
        self.assertEqual(removed_ids, ["web-1"])
        # State monitor was notified
        self.assertEqual(dirty, ["plugins.telegram_integration_voice.session.delete"])

    def test_delete_session_for_user_unbound_other_user_refused(self):
        """Unbound web session belonging to a different user is refused."""
        handler = self.handler
        meta = {
            "id": "web-other",
            "display_name": "Other user",
            "telegram_binding": "unbound",
            "last_message": "2026-01-01T00:00:00",
            "data": {
                handler.CTX_TG_BOT: "mainbot",
                handler.CTX_TG_USER_ID: 999,
                handler.CTX_TG_CHAT_ID: 0,
            },
        }
        removed_paths = []

        with mock.patch.object(handler, "_list_switchable_sessions", return_value=[meta]), \
             mock.patch.object(handler, "_read_persisted_chat_meta", return_value=meta), \
             mock.patch.object(handler, "_mapped_context_id", return_value="other"), \
             mock.patch.object(handler, "_load_state", return_value={"chats": {}}), \
             mock.patch.object(handler.os.path, "isfile", return_value=True), \
             mock.patch.object(handler.os, "remove", side_effect=lambda p: removed_paths.append(p)):
            ok, msg, was_active = handler._delete_session_for_user("mainbot", 42, 99, "web-other")

        self.assertFalse(ok)
        self.assertFalse(was_active)
        self.assertIn("not allowed", msg.lower())
        self.assertEqual(removed_paths, [])

    def test_delete_session_for_user_unknown_session_refused(self):
        """Sessions not visible in the picker cannot be deleted."""
        handler = self.handler
        with mock.patch.object(handler, "_list_switchable_sessions", return_value=[]), \
             mock.patch.object(handler, "_load_state", return_value={"chats": {}}), \
             mock.patch.object(handler.os, "remove") as remove_mock:
            ok, msg, was_active = handler._delete_session_for_user("mainbot", 42, 99, "missing")

        self.assertFalse(ok)
        self.assertFalse(was_active)
        self.assertIn("not found", msg.lower())
        remove_mock.assert_not_called()

    def test_handle_callback_query_session_delete_shows_confirm(self):
        """sd| callback edits the message with the confirm screen; file untouched."""
        handler = self.handler
        meta = {
            "id": "abc",
            "display_name": "Old chat",
            "telegram_binding": "bound",
            "last_message": "2026-01-01T00:00:00",
            "data": {},
        }
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji"),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}sd|abc",
            message=types.SimpleNamespace(message_id=55, chat=types.SimpleNamespace(id=99, type="private")),
            answer=mock.AsyncMock(),
        )
        removed = []

        class _BotCtx:
            async def __aenter__(self):
                return types.SimpleNamespace()
            async def __aexit__(self, exc_type, exc, tb):
                return False

        with mock.patch.object(handler, "_list_switchable_sessions", return_value=[meta]), \
             mock.patch.object(handler, "_mapped_context_id", return_value="other"), \
             mock.patch.object(handler, "_load_state", return_value={"chats": {}}), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_temp_bot", return_value=_BotCtx()), \
             mock.patch.object(handler.tc, "edit_text_with_keyboard", new=mock.AsyncMock(return_value=True)) as edit_kb, \
             mock.patch.object(handler.os, "remove", side_effect=lambda p: removed.append(p)):
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        query.answer.assert_awaited()
        edit_kb.assert_awaited_once()
        args = edit_kb.await_args.args
        self.assertEqual(args[2], 55)  # message_id
        self.assertIn("Delete session", args[3])
        self.assertIn("Old chat", args[3])
        keyboard = args[4]
        flat_texts = [b["text"] for row in keyboard for b in row]
        self.assertIn("🗑 Yes, delete", flat_texts)
        self.assertIn("⬅️ Cancel", flat_texts)
        self.assertEqual(removed, [])

    def test_handle_callback_query_session_delete_confirm_executes(self):
        """sdy| callback removes the file and re-renders the picker with the existing active id."""
        handler = self.handler
        meta = {
            "id": "abc",
            "display_name": "Old chat",
            "telegram_binding": "bound",
            "last_message": "2026-01-01T00:00:00",
            "data": {
                handler.CTX_TG_BOT: "mainbot",
                handler.CTX_TG_USER_ID: 42,
                handler.CTX_TG_CHAT_ID: 99,
            },
        }
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji"),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}sdy|abc",
            message=types.SimpleNamespace(message_id=55, chat=types.SimpleNamespace(id=99, type="private")),
            answer=mock.AsyncMock(),
        )
        removed_ids = []
        sent = []
        saved_states = []
        dirty = []

        class _BotCtx:
            async def __aenter__(self):
                return types.SimpleNamespace()
            async def __aexit__(self, exc_type, exc, tb):
                return False

        with mock.patch.object(handler, "_list_switchable_sessions", return_value=[meta]), \
             mock.patch.object(handler, "_read_persisted_chat_meta", return_value=meta), \
             mock.patch.object(handler, "_mapped_context_id", return_value="other"), \
             mock.patch.object(handler, "_load_state", return_value={"chats": {"mainbot:42:99": "other"}}), \
             mock.patch.object(handler, "_save_state", side_effect=lambda s: saved_states.append(s.copy())), \
             mock.patch.object(handler, "remove_chat", side_effect=lambda cid: removed_ids.append(cid)) as remove_chat_mock, \
             mock.patch.object(handler, "_mark_chat_state_dirty", side_effect=lambda r: dirty.append(r)), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_temp_bot", return_value=_BotCtx()), \
             mock.patch.object(handler, "_show_session_picker", new=mock.AsyncMock()) as show_picker, \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *a, **k: sent.append((a, k)))):
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        remove_chat_mock.assert_called_once_with("abc")
        self.assertEqual(removed_ids, ["abc"])
        # state.json untouched (not the active session)
        self.assertEqual(saved_states, [])
        # Picker was re-rendered with the existing active id
        show_picker.assert_awaited_once()
        self.assertEqual(show_picker.await_args.kwargs["bot_name"], "mainbot")
        self.assertEqual(show_picker.await_args.kwargs["user_id"], 42)
        self.assertEqual(show_picker.await_args.kwargs["active_ctx_id"], "other")
        # State monitor was notified
        self.assertEqual(dirty, ["plugins.telegram_integration_voice.session.delete"])
        # Notice was sent
        self.assertTrue(any("Deleted session" in str(a) for a, _ in sent))

    def test_handle_callback_query_session_delete_confirm_active_triggers_newchat(self):
        """When the deleted session is the active one, a fresh session is started and the picker shows it."""
        handler = self.handler
        meta = {
            "id": "active",
            "display_name": "Active chat",
            "telegram_binding": "bound",
            "last_message": "2026-01-01T00:00:00",
            "data": {
                handler.CTX_TG_BOT: "mainbot",
                handler.CTX_TG_USER_ID: 42,
                handler.CTX_TG_CHAT_ID: 99,
            },
        }
        active_ctx = _DummyAgentContext(name="Active chat")
        _DummyAgentContext.registry[active_ctx.id] = active_ctx
        # Make sure the in-memory context is the active one for the lookup
        meta["id"] = active_ctx.id
        new_ctx = _DummyAgentContext(name="Fresh chat")
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji"),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}sdy|{active_ctx.id}",
            message=types.SimpleNamespace(message_id=55, chat=types.SimpleNamespace(id=99, type="private")),
            answer=mock.AsyncMock(),
        )
        removed_ids = []
        sent = []
        saved_states = []
        dirty = []

        class _BotCtx:
            async def __aenter__(self):
                return types.SimpleNamespace()
            async def __aexit__(self, exc_type, exc, tb):
                return False

        async def _fake_start_new_session(bot, bot_cfg, user_id, username, chat_id):
            return True, "New chat started.", new_ctx

        with mock.patch.object(handler, "_list_switchable_sessions", return_value=[meta]), \
             mock.patch.object(handler, "_read_persisted_chat_meta", return_value=meta), \
             mock.patch.object(handler, "_mapped_context_id", return_value=active_ctx.id), \
             mock.patch.object(handler, "_load_state", return_value={"chats": {"mainbot:42:99": active_ctx.id}}), \
             mock.patch.object(handler, "_save_state", side_effect=lambda s: saved_states.append(s.copy())), \
             mock.patch.object(handler, "remove_chat", side_effect=lambda cid: removed_ids.append(cid)) as remove_chat_mock, \
             mock.patch.object(handler, "_mark_chat_state_dirty", side_effect=lambda r: dirty.append(r)), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_temp_bot", return_value=_BotCtx()), \
             mock.patch.object(handler, "_start_new_session_for_user", new=mock.AsyncMock(side_effect=_fake_start_new_session)) as start_new, \
             mock.patch.object(handler, "_show_session_picker", new=mock.AsyncMock()) as show_picker, \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *a, **k: sent.append((a, k)))):
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        # state.json was cleared for the active mapping
        self.assertEqual(saved_states[0]["chats"], {})
        # In-memory context was reset and removed
        self.assertTrue(active_ctx.reset_called)
        self.assertTrue(active_ctx.removed)
        self.assertNotIn(active_ctx.id, _DummyAgentContext.registry)
        # New session was started
        start_new.assert_awaited_once()
        # persist_chat.remove_chat was called for the right ctx_id
        remove_chat_mock.assert_called_once_with(active_ctx.id)
        self.assertEqual(removed_ids, [active_ctx.id])
        # Picker was re-rendered with the new active id
        show_picker.assert_awaited_once()
        self.assertEqual(show_picker.await_args.kwargs["active_ctx_id"], new_ctx.id)
        # State monitor was notified
        self.assertEqual(dirty, ["plugins.telegram_integration_voice.session.delete"])
        # Notice was sent
        self.assertTrue(any("Deleted session" in str(a) for a, _ in sent))

    def test_handle_callback_query_session_delete_confirm_unauthorized_notifies(self):
        """When the helper refuses (e.g. cross-user), the callback answers with the error and does not touch the file."""
        handler = self.handler
        meta = {
            "id": "web-other",
            "display_name": "Other user",
            "telegram_binding": "unbound",
            "last_message": "2026-01-01T00:00:00",
            "data": {
                handler.CTX_TG_BOT: "mainbot",
                handler.CTX_TG_USER_ID: 999,
                handler.CTX_TG_CHAT_ID: 0,
            },
        }
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji"),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}sdy|web-other",
            message=types.SimpleNamespace(message_id=55, chat=types.SimpleNamespace(id=99, type="private")),
            answer=mock.AsyncMock(),
        )
        removed = []

        class _BotCtx:
            async def __aenter__(self):
                return types.SimpleNamespace()
            async def __aexit__(self, exc_type, exc, tb):
                return False

        with mock.patch.object(handler, "_list_switchable_sessions", return_value=[meta]), \
             mock.patch.object(handler, "_read_persisted_chat_meta", return_value=meta), \
             mock.patch.object(handler, "_mapped_context_id", return_value="other"), \
             mock.patch.object(handler, "_load_state", return_value={"chats": {}}), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_temp_bot", return_value=_BotCtx()), \
             mock.patch.object(handler, "_show_session_picker", new=mock.AsyncMock()) as show_picker, \
             mock.patch.object(handler.os, "remove", side_effect=lambda p: removed.append(p)):
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        query.answer.assert_awaited_once()
        self.assertIn("not allowed", query.answer.await_args.args[0].lower())
        show_picker.assert_not_awaited()
        self.assertEqual(removed, [])

    def test_handle_callback_query_session_delete_cancel_returns_to_details(self):
        """sdn| callback shows details again, leaving the file untouched."""
        handler = self.handler
        meta = {
            "id": "abc",
            "display_name": "Old chat",
            "telegram_binding": "bound",
            "last_message": "2026-01-01T00:00:00",
            "data": {},
        }
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji"),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}sdn|abc",
            message=types.SimpleNamespace(message_id=55, chat=types.SimpleNamespace(id=99, type="private")),
            answer=mock.AsyncMock(),
        )
        removed = []

        class _BotCtx:
            async def __aenter__(self):
                return types.SimpleNamespace()
            async def __aexit__(self, exc_type, exc, tb):
                return False

        with mock.patch.object(handler, "_list_switchable_sessions", return_value=[meta]), \
             mock.patch.object(handler, "_mapped_context_id", return_value="other"), \
             mock.patch.object(handler, "_load_state", return_value={"chats": {}}), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_temp_bot", return_value=_BotCtx()), \
             mock.patch.object(handler, "_show_session_details", new=mock.AsyncMock()) as show_details, \
             mock.patch.object(handler.os, "remove", side_effect=lambda p: removed.append(p)):
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))

        show_details.assert_awaited_once()
        kwargs = show_details.await_args.kwargs
        self.assertEqual(kwargs["meta"]["id"], "abc")
        self.assertEqual(removed, [])

    # --- Response transform + /shortcut + picker summary -----------------

    def test_response_transform_specs_only_contain_shorter_and_longer(self):
        """Hard migration: no more 'technical' or 'step_by_step'."""
        handler = self.handler
        actions = set(handler._RESPONSE_TRANSFORM_SPECS.keys())
        self.assertEqual(actions, {"shorter", "longer"})
        self.assertEqual(handler._RESPONSE_TRANSFORM_SPECS["shorter"]["button"], "✂️ Shorter")
        self.assertEqual(handler._RESPONSE_TRANSFORM_SPECS["longer"]["button"], "📏 Longer")
        self.assertIn("shorter", handler._RESPONSE_TRANSFORM_SPECS["shorter"]["instruction"].lower())
        self.assertIn("longer", handler._RESPONSE_TRANSFORM_SPECS["longer"]["instruction"].lower())
        # Spec lookup case-insensitive
        self.assertIsNotNone(handler._response_transform_spec("LONGER"))
        self.assertIsNotNone(handler._response_transform_spec("shorter"))
        # Old actions must not be available anymore
        self.assertIsNone(handler._response_transform_spec("technical"))
        self.assertIsNone(handler._response_transform_spec("step_by_step"))
        self.assertIsNone(handler._response_transform_spec("more_technical"))

    def test_response_more_keyboard_contains_shorter_and_longer_only(self):
        """More-menu keyboard: Shorter + Longer + To voice + Back, no Step by step / More technical."""
        handler = self.handler
        rows = handler._response_more_keyboard("tok123", include_show_text=False)
        flat = [btn for row in rows for btn in row]
        texts = [b["text"] for b in flat]
        # Expected order: Shorter, Longer, To voice, Back
        self.assertEqual(texts, ["✂️ Shorter", "📏 Longer", "🎙 To voice", "⬅ Back"])
        # The Shorter + Longer callbacks must point to the new spec names
        shorter_btn = next(b for b in flat if b["text"] == "✂️ Shorter")
        longer_btn = next(b for b in flat if b["text"] == "📏 Longer")
        self.assertIn("shorter:tok123", shorter_btn["callback_data"])
        self.assertIn("longer:tok123", longer_btn["callback_data"])
        # Make sure no legacy transform leaked into the keyboard
        for b in flat:
            self.assertNotIn("technical", b["callback_data"])
            self.assertNotIn("step_by_step", b["callback_data"])

    def test_session_transcript_text_uses_history_output_and_redacts(self):
        """Transcript comes from history.output_text, with secrets redacted."""
        handler = self.handler

        class _Hist:
            def output_text(self, human_label="user", ai_label="assistant"):
                return (
                    f"{human_label}: My api_key=sk-LIVE-SECRET-1234567 broke\n"
                    f"{ai_label}: Try resetting it."
                )

        agent = types.SimpleNamespace(history=_Hist())
        ctx = types.SimpleNamespace(id="ctx-1", name="PRTG debug", agent0=agent)
        text = handler._session_transcript_text(ctx)
        self.assertIn("user:", text)
        self.assertIn("assistant:", text)
        self.assertIn("api_key=[REDACTED]", text)
        self.assertNotIn("sk-LIVE-SECRET-1234567", text)

    def test_session_transcript_text_falls_back_to_output_list(self):
        """When output_text is unavailable, iterate the OutputMessage list."""
        handler = self.handler

        class _Hist:
            def output_text(self, **kwargs):
                raise RuntimeError("no helper")

            def output(self):
                return [
                    {"ai": False, "content": "Hello there"},
                    {"ai": True, "content": [{"type": "text", "text": "Hi back"}]},
                ]

        agent = types.SimpleNamespace(history=_Hist())
        ctx = types.SimpleNamespace(id="ctx-1", name="X", agent0=agent)
        text = handler._session_transcript_text(ctx)
        self.assertIn("user: Hello there", text)
        self.assertIn("assistant: Hi back", text)

    def test_session_transcript_text_empty_when_no_history(self):
        handler = self.handler
        ctx = types.SimpleNamespace(id="ctx-1", name="X", agent0=types.SimpleNamespace())
        self.assertEqual(handler._session_transcript_text(ctx), "")
        self.assertEqual(handler._session_transcript_text(None), "")

    def test_session_details_text_includes_summary_when_provided(self):
        """Picker details view: 📝 Summary: block replaces the old Topic: line."""
        handler = self.handler
        meta = {
            "id": "abc",
            "display_name": "Old chat",
            "telegram_binding": "bound",
            "created_at": "2026-01-01T00:00:00",
            "last_message": "2026-01-02T00:00:00",
            "message_count": 5,
            "data": {},
        }
        text = handler._session_details_text(
            meta, active_ctx_id=None, summary="Topic: printer debug\nState: blocked on network"
        )
        self.assertIn("📝 Summary:", text)
        self.assertIn("printer debug", text)
        self.assertNotIn("Topic: {", text)
        # No summary → no summary block
        text2 = handler._session_details_text(meta, active_ctx_id=None, summary="")
        self.assertNotIn("📝 Summary:", text2)

    def test_session_llm_summary_calls_utility_model_and_redacts_secrets(self):
        """`/shortcut summary` must use the utility LLM and redact secrets before sending."""
        handler = self.handler
        seen = {}

        async def call_utility_model(**kwargs):
            seen.update(kwargs)
            return "TL;DR — user asked about X, agent helped, currently blocked on Y."

        class _Hist:
            def output_text(self, human_label="user", ai_label="assistant"):
                return f"{human_label}: My api_key=sk-LIVE-SECRET-1234567 is broken"

        agent = types.SimpleNamespace(history=_Hist(), call_utility_model=call_utility_model)
        ctx = types.SimpleNamespace(id="ctx-1", name="PRTG debug", agent0=agent)

        summary = asyncio.run(handler._session_llm_summary(ctx, detailed=True))

        self.assertIn("TL;DR", summary)
        self.assertIn("system", seen)
        self.assertIn("message", seen)
        self.assertIn("api_key=[REDACTED]", seen["message"])
        self.assertNotIn("sk-LIVE-SECRET-1234567", seen["message"])
        self.assertIn("PRTG debug", seen["message"])

    def test_session_llm_summary_detailed_vs_short_prompts_differ(self):
        handler = self.handler
        seen = {}

        async def call_utility_model(**kwargs):
            seen.setdefault("systems", []).append(kwargs.get("system", ""))
            return "ok"

        class _Hist:
            def output_text(self, human_label="user", ai_label="assistant"):
                return "user: hi\nassistant: hello"

        agent = types.SimpleNamespace(history=_Hist(), call_utility_model=call_utility_model)
        ctx = types.SimpleNamespace(id="c", name="n", agent0=agent)
        asyncio.run(handler._session_llm_summary(ctx, detailed=True))
        asyncio.run(handler._session_llm_summary(ctx, detailed=False))
        self.assertIn("multi-paragraph", seen["systems"][0])
        self.assertIn("3-4 short", seen["systems"][1])

    def test_session_llm_summary_returns_empty_when_no_history(self):
        handler = self.handler
        called = {"n": 0}

        async def call_utility_model(**kwargs):
            called["n"] += 1
            return "should not be called"

        agent = types.SimpleNamespace(call_utility_model=call_utility_model)
        ctx = types.SimpleNamespace(id="ctx-1", name="empty", agent0=agent)

        summary = asyncio.run(handler._session_llm_summary(ctx, detailed=True))

        self.assertEqual(summary, "")
        self.assertEqual(called["n"], 0)

    def test_shortcut_inline_keyboard_has_three_action_buttons(self):
        handler = self.handler
        rows = handler._shortcut_inline_keyboard()
        flat = [b for row in rows for b in row]
        texts = [b["text"] for b in flat]
        self.assertEqual(texts, ["✂️ Shorter", "📏 Longer", "📝 Summary"])
        for b in flat:
            self.assertTrue(b["callback_data"].startswith(handler.TG_UI_CALLBACK_PREFIX + "sx|"))
        cbs = [b["callback_data"] for b in flat]
        self.assertIn(handler.TG_UI_CALLBACK_PREFIX + "sx|shorter", cbs)
        self.assertIn(handler.TG_UI_CALLBACK_PREFIX + "sx|longer", cbs)
        self.assertIn(handler.TG_UI_CALLBACK_PREFIX + "sx|summary", cbs)

    def test_handle_shortcut_without_subcommand_shows_inline_buttons(self):
        handler = self.handler
        message = types.SimpleNamespace(
            text="/shortcut",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji"),
        )
        sent = []
        with mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *a, **k: sent.append((a, k)))):
            asyncio.run(handler.handle_shortcut(message, "mainbot", {}))
        # An inline keyboard was attached
        self.assertTrue(any(k.get("keyboard") for _, k in sent))
        kb = next(k["keyboard"] for _, k in sent if k.get("keyboard"))
        flat = [b for row in kb for b in row]
        self.assertEqual([b["text"] for b in flat], ["✂️ Shorter", "📏 Longer", "📝 Summary"])

    def test_handle_shortcut_shorter_triggers_transform_with_last_answer(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="PRTG debug")
        ctx.data = {handler.CTX_TG_LAST_TEXT_RESPONSE: "Long answer here."}
        message = types.SimpleNamespace(
            text="/shortcut shorter",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji", first_name="Benji", last_name=""),
        )
        dispatched = []

        async def _fake_dispatch(c, **kwargs):
            dispatched.append((c, kwargs))
            return None

        sent = []
        with mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_get_existing_context", return_value=ctx), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *a, **k: sent.append((a, k)))), \
             mock.patch.object(handler, "_dispatch_telegram_user_turn", new=mock.AsyncMock(side_effect=_fake_dispatch)) as dispatch:
            asyncio.run(handler.handle_shortcut(message, "mainbot", {}))

        # A turn was dispatched against the active context
        dispatch.assert_awaited_once()
        kwargs = dispatch.await_args.kwargs
        self.assertIs(kwargs["bot_token"], "tok")
        self.assertEqual(kwargs["chat_id"], 99)
        self.assertIn("Long answer here.", kwargs["body"])
        self.assertIn("Instruction:", kwargs["body"])
        self.assertIn("shorter", kwargs["source"])
        # Ack notice was sent
        self.assertTrue(any("Shortening" in str(a[2]) for a, _ in sent))

    def test_handle_shortcut_longer_triggers_transform(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="X")
        ctx.data = {handler.CTX_TG_LAST_TEXT_RESPONSE: "Short answer."}
        message = types.SimpleNamespace(
            text="/shortcut longer",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji", first_name="Benji", last_name=""),
        )
        sent = []
        with mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_get_existing_context", return_value=ctx), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *a, **k: sent.append((a, k)))), \
             mock.patch.object(handler, "_dispatch_telegram_user_turn", new=mock.AsyncMock()) as dispatch:
            asyncio.run(handler.handle_shortcut(message, "mainbot", {}))
        dispatch.assert_awaited_once()
        self.assertIn("Short answer.", dispatch.await_args.kwargs["body"])
        self.assertIn("longer", dispatch.await_args.kwargs["source"])
        self.assertTrue(any("Expanding" in str(a[2]) for a, _ in sent))

    def test_handle_shortcut_shorter_without_last_answer_replies(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="X")
        ctx.data = {}
        message = types.SimpleNamespace(
            text="/shortcut shorter",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji", first_name="Benji", last_name=""),
        )
        sent = []
        with mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_get_existing_context", return_value=ctx), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *a, **k: sent.append((a, k)))), \
             mock.patch.object(handler, "_dispatch_telegram_user_turn", new=mock.AsyncMock()) as dispatch:
            asyncio.run(handler.handle_shortcut(message, "mainbot", {}))
        # No dispatch, friendly notice instead
        dispatch.assert_not_awaited()
        self.assertTrue(any("No previous answer" in str(a[2]) for a, _ in sent))

    def test_handle_shortcut_summary_sends_llm_summary_as_separate_message(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="PRTG debug")
        ctx.data = {}
        message = types.SimpleNamespace(
            text="/shortcut summary",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji", first_name="Benji", last_name=""),
        )
        sent = []

        async def _fake_summary(_ctx, **kwargs):
            return "TL;DR: agent helped with PRTG; current state: printer back online."

        with mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_get_existing_context", return_value=ctx), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *a, **k: sent.append((a, k)))), \
             mock.patch.object(handler, "_session_llm_summary", new=mock.AsyncMock(side_effect=_fake_summary)):
            asyncio.run(handler.handle_shortcut(message, "mainbot", {}))

        # Two messages: "summarizing…" notice + the actual summary
        texts = [str(a[2]) for a, _ in sent]
        self.assertEqual(len(texts), 2)
        self.assertIn("Summarizing", texts[0])
        self.assertIn("Session summary", texts[1])
        self.assertIn("TL;DR: agent helped with PRTG", texts[1])

    def test_handle_shortcut_summary_without_context_replies(self):
        handler = self.handler
        message = types.SimpleNamespace(
            text="/shortcut summary",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji", first_name="Benji", last_name=""),
        )
        sent = []
        with mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_get_existing_context", return_value=None), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *a, **k: sent.append((a, k)))):
            asyncio.run(handler.handle_shortcut(message, "mainbot", {}))
        self.assertTrue(any("No active session" in str(a[2]) for a, _ in sent))

    def test_handle_shortcut_unknown_subcommand_replies_with_usage(self):
        handler = self.handler
        ctx = _DummyAgentContext(name="X")
        message = types.SimpleNamespace(
            text="/shortcut banana",
            chat=types.SimpleNamespace(id=99),
            from_user=types.SimpleNamespace(id=42, username="benji", first_name="Benji", last_name=""),
        )
        sent = []
        with mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="tok"))), \
             mock.patch.object(handler, "_get_existing_context", return_value=ctx), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *a, **k: sent.append((a, k)))):
            asyncio.run(handler.handle_shortcut(message, "mainbot", {}))
        self.assertTrue(any("Unknown shortcut" in str(a[2]) for a, _ in sent))

    def test_callback_sh_summary_runs_llm_summary(self):
        """tgx|sx|summary callback generates an LLM summary against the active session."""
        handler = self.handler
        ctx = _DummyAgentContext(name="PRTG debug")
        ctx.data = {}
        sent = []

        async def _fake_summary(_ctx, **kwargs):
            return "TL;DR via button: printer fixed."

        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji", first_name="Benji", last_name=""),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}sx|summary",
            message=types.SimpleNamespace(
                message_id=77,
                chat=types.SimpleNamespace(id=99, type="private"),
            ),
            answer=mock.AsyncMock(),
        )
        with mock.patch.object(handler, "_get_or_create_context_from_user", new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *a, **k: sent.append((a, k)))), \
             mock.patch.object(handler, "_session_llm_summary", new=mock.AsyncMock(side_effect=_fake_summary)):
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))
        query.answer.assert_awaited()
        texts = [str(a[2]) for a, _ in sent]
        self.assertTrue(any("Session summary" in t for t in texts))
        self.assertTrue(any("TL;DR via button" in t for t in texts))

    def test_callback_sh_shorter_dispatches_transform(self):
        """tgx|sx|shorter callback re-runs the shorter transform against the active session."""
        handler = self.handler
        ctx = _DummyAgentContext(name="X")
        ctx.data = {handler.CTX_TG_LAST_TEXT_RESPONSE: "A long answer to shorten."}
        sent = []
        query = types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=42, username="benji", first_name="Benji", last_name=""),
            data=f"{handler.TG_UI_CALLBACK_PREFIX}sx|shorter",
            message=types.SimpleNamespace(
                message_id=77,
                chat=types.SimpleNamespace(id=99, type="private"),
            ),
            answer=mock.AsyncMock(),
        )
        with mock.patch.object(handler, "_get_or_create_context_from_user", new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock(side_effect=lambda *a, **k: sent.append((a, k)))), \
             mock.patch.object(handler, "_dispatch_telegram_user_turn", new=mock.AsyncMock()) as dispatch:
            asyncio.run(handler.handle_callback_query(query, "mainbot", {}))
        dispatch.assert_awaited_once()
        self.assertIn("A long answer to shorten.", dispatch.await_args.kwargs["body"])
        self.assertIn("shorter", dispatch.await_args.kwargs["source"])


if __name__ == "__main__":
    unittest.main()
