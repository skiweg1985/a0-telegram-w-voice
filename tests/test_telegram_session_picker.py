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
    tc.delete_message = lambda *args, **kwargs: None
    tc.supports_message_draft = lambda *args, **kwargs: False
    tc.send_message_draft = lambda *args, **kwargs: None
    tc.build_reply_keyboard = lambda *args, **kwargs: {"reply_keyboard": True}
    tc.build_inline_keyboard = lambda *args, **kwargs: {"inline_keyboard": True}
    tc.md_to_telegram_html = lambda text: text

    async def _tc_send_typing(*args, **kwargs):
        return None

    tc.send_typing = _tc_send_typing
    sys.modules["usr.plugins.telegram_integration_voice.helpers.telegram_client"] = tc

    detail_status = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.detail_status")
    detail_status.render = lambda *args, **kwargs: None
    detail_status.effective_detail_level = lambda *args, **kwargs: "info"
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

        self.assertIn("🔄 In progress…", html_text)
        self.assertNotIn("Working", html_text)

    def test_render_progress_status_html_shows_gen_phase_in_header(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_PROGRESS_PHASE] = "gen"

        html_text = handler._render_progress_status_html(ctx, {}, done=False)

        self.assertIn("🔄 In progress… [GEN…]", html_text)

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

    def test_stream_worker_flushes_when_buffer_threshold_is_reached(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_BOT_CFG] = {
            "progress": {
                "live_response_preview_interval_ms": 10000,
                "live_response_preview_buffer_threshold": 1,
            }
        }
        stream_data = {
            "full": json.dumps({
                "tool_name": "response",
                "tool_args": {"text": "Threshold answer", "break_loop": True},
            })
        }

        async def scenario():
            with mock.patch.object(handler, "_send_telegram_live_draft_preview", new=mock.AsyncMock(return_value=True)) as send_draft:
                await handler.handle_telegram_response_stream_chunk(ctx, stream_data)
                await asyncio.sleep(0.01)
                send_draft.assert_awaited_once_with(ctx, "Threshold answer")
                handler._cancel_stream_preview_worker(ctx)

        asyncio.run(scenario())

    def test_flush_live_preview_uses_latest_pending_text(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        token = "tok"
        ctx.data[handler.CTX_TG_STREAM_WORKER_TOKEN] = token
        ctx.data[handler.CTX_TG_BOT_CFG] = {
            "progress": {}
        }
        ctx.data[handler.CTX_TG_STREAM_PENDING_FULL] = json.dumps({
            "tool_name": "response",
            "tool_args": {"text": "Latest answer", "break_loop": True},
        })

        with mock.patch.object(handler, "_send_telegram_live_draft_preview", new=mock.AsyncMock(return_value=True)) as send_draft:
            ok = asyncio.run(handler._flush_telegram_live_preview_once(ctx, token))

        self.assertTrue(ok)
        send_draft.assert_awaited_once_with(ctx, "Latest answer")

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
            mock.patch.object(handler.tc, "build_reply_keyboard", return_value={"reply_keyboard": True}, create=True),
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
            handler.tc.edit_text.assert_awaited_once()
            edit_args = handler.tc.edit_text.await_args.args
            self.assertEqual(edit_args[3], "Final answer")
            handler.tc.send_text.assert_not_awaited()
            handler.tc.delete_message.assert_not_awaited()
        self.assertNotIn(handler.CTX_TG_PROGRESS_MESSAGE_ID, ctx.data)

    def test_send_telegram_reply_deletes_progress_when_final_sent_separately(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True

        with self._patch_reply_dependencies(handler, edit_ok=True):
            result = asyncio.run(handler.send_telegram_reply(ctx, "Final answer"))
            self.assertIsNone(result)
            handler.tc.send_text.assert_awaited_once()
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
            handler.tc.edit_text.assert_not_awaited()

            voice_kwargs = handler.tc.send_voice.await_args.kwargs
            self.assertIsNotNone(voice_kwargs.get("buttons"))
            self.assertEqual(voice_kwargs["buttons"][0][0]["text"], "📝 Show text")
            self.assertTrue(
                voice_kwargs["buttons"][0][0]["callback_data"].startswith(
                    f"{handler.TG_UI_CALLBACK_PREFIX}qa|show_text:"
                )
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
            handler.tc.edit_text.assert_awaited_once()

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

    def test_reply_keyboard_action_routes_private_control_pad_buttons(self):
        handler = self.handler
        message = types.SimpleNamespace(
            text="🎙 Voice",
            chat=types.SimpleNamespace(type="private", id=1),
            from_user=types.SimpleNamespace(id=1, username="alice"),
        )

        with mock.patch.object(handler, "handle_voice", new=mock.AsyncMock()) as handle_voice:
            handled = asyncio.run(
                handler._handle_reply_keyboard_action(
                    message,
                    "mainbot",
                    {"reply_keyboard": {"enabled": True}},
                )
            )

        self.assertTrue(handled)
        handle_voice.assert_awaited_once_with(message, "mainbot", {"reply_keyboard": {"enabled": True}})

    def test_reply_keyboard_action_is_ignored_when_not_enabled_or_not_private(self):
        handler = self.handler
        disabled = types.SimpleNamespace(
            text="📂 Session",
            chat=types.SimpleNamespace(type="private", id=1),
            from_user=types.SimpleNamespace(id=1, username="alice"),
        )
        group_msg = types.SimpleNamespace(
            text="📂 Session",
            chat=types.SimpleNamespace(type="group", id=1),
            from_user=types.SimpleNamespace(id=1, username="alice"),
        )

        with mock.patch.object(handler, "handle_session", new=mock.AsyncMock()) as handle_session:
            self.assertFalse(asyncio.run(handler._handle_reply_keyboard_action(disabled, "mainbot", {})))
            self.assertFalse(
                asyncio.run(
                    handler._handle_reply_keyboard_action(
                        group_msg,
                        "mainbot",
                        {"reply_keyboard": {"enabled": True}},
                    )
                )
            )

        handle_session.assert_not_awaited()

    def test_handle_start_attaches_reply_keyboard_in_private_chat(self):
        handler = self.handler
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=7, type="private"),
            from_user=types.SimpleNamespace(id=42, username="alice", first_name="Alice"),
            reply=mock.AsyncMock(),
        )

        with mock.patch.object(handler, "_is_allowed", return_value=True), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="token"))), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock()) as send_temp, \
             mock.patch.object(handler, "_get_or_create_context", new=mock.AsyncMock(return_value=object())), \
             mock.patch.object(handler.tc, "build_reply_keyboard", return_value={"reply_keyboard": True}, create=True):
            asyncio.run(handler.handle_start(message, "mainbot", {"reply_keyboard": {"enabled": True}}))

        self.assertEqual(send_temp.await_args.kwargs["reply_markup"], {"reply_keyboard": True})

    def test_handle_clear_and_newchat_refresh_reply_keyboard(self):
        handler = self.handler
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=7, type="private"),
            from_user=types.SimpleNamespace(id=42, username="alice"),
        )
        ctx = types.SimpleNamespace(data={}, reset=mock.Mock())

        with mock.patch.object(handler, "_is_allowed", return_value=True), \
             mock.patch.object(handler, "_load_state", return_value={"chats": {"mainbot:42:7": "ctx-1"}}), \
             mock.patch.object(handler.AgentContext, "get", return_value=ctx), \
             mock.patch.object(handler, "save_tmp_chat"), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="token"))), \
             mock.patch.object(handler, "_send_with_temp_bot", new=mock.AsyncMock()) as send_temp, \
             mock.patch.object(handler.tc, "build_reply_keyboard", return_value={"reply_keyboard": True}, create=True):
            asyncio.run(handler.handle_clear(message, "mainbot", {"reply_keyboard": {"enabled": True}}))

        self.assertEqual(send_temp.await_args.kwargs["reply_markup"], {"reply_keyboard": True})
        ctx.reset.assert_called_once()

        send_temp.reset_mock()
        with mock.patch.object(handler, "_is_allowed", return_value=True), \
             mock.patch.object(handler, "get_bot", return_value=types.SimpleNamespace(bot=types.SimpleNamespace(token="token"))), \
             mock.patch.object(
                 handler,
                 "_start_new_session_for_user",
                 new=mock.AsyncMock(return_value=(True, "Started a fresh chat.", object())),
             ), \
             mock.patch.object(handler, "_send_with_temp_bot", new=send_temp), \
             mock.patch.object(handler.tc, "build_reply_keyboard", return_value={"reply_keyboard": True}, create=True):
            asyncio.run(handler.handle_newchat(message, "mainbot", {"reply_keyboard": {"enabled": True}}))

        self.assertEqual(send_temp.await_args.kwargs["reply_markup"], {"reply_keyboard": True})

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

    def test_send_telegram_reply_voice_only_refreshes_reply_keyboard_when_no_text_is_visible(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True
        ctx.data[handler.CTX_TG_CHAT_TYPE] = "private"
        ctx.data[handler.CTX_TG_BOT_CFG]["reply_keyboard"] = {"enabled": True}

        with self._patch_reply_dependencies(
            handler,
            edit_ok=True,
            voice_mode="force",
            tts_enabled=True,
            also_send_text=False,
        ), mock.patch.object(
            handler.speech,
            "quick_actions_settings",
            return_value={"enabled": False, "show_text": False},
            create=True,
        ):
            result = asyncio.run(handler.send_telegram_reply(ctx, "Voice only"))
            self.assertIsNone(result)
            self.assertEqual(handler.tc.send_voice.await_args.kwargs["reply_markup"], {"reply_keyboard": True})
            self.assertIsNone(handler.tc.send_voice.await_args.kwargs.get("buttons"))
            handler.tc.send_text.assert_not_awaited()

    def test_send_telegram_reply_video_note_falls_back_to_video(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True

        with self._patch_reply_dependencies(handler, edit_ok=True), \
             mock.patch.object(handler.tc, "send_video_note", new=mock.AsyncMock(return_value=None), create=True):
            result = asyncio.run(
                handler.send_telegram_reply(
                    ctx,
                    "",
                    telegram_items=[{"type": "video_note", "path": "/tmp/videonote_123.mp4"}],
                )
            )
            self.assertIsNone(result)
            handler.tc.send_video_note.assert_awaited_once()
            handler.tc.send_video.assert_awaited_once()
            handler.tc.send_file.assert_not_awaited()

    def test_send_telegram_reply_dispatches_structured_telegram_items(self):
        handler = self.handler
        ctx = self._reply_context({"completed_mode": "delete"})
        ctx.data[handler.CTX_TG_STREAM_DRAFT_USED] = True

        with self._patch_reply_dependencies(handler, edit_ok=True):
            result = asyncio.run(
                handler.send_telegram_reply(
                    ctx,
                    "",
                    telegram_items=[
                        {"type": "location", "latitude": 1.0, "longitude": 2.0},
                        {
                            "type": "contact",
                            "phone_number": "+491234",
                            "first_name": "Alex",
                            "last_name": "Meyer",
                        },
                        {
                            "type": "venue",
                            "latitude": 3.0,
                            "longitude": 4.0,
                            "title": "HQ",
                            "address": "Street 1",
                        },
                    ],
                )
            )
            self.assertIsNone(result)
            handler.tc.send_location.assert_awaited_once()
            handler.tc.send_contact.assert_awaited_once()
            handler.tc.send_venue.assert_awaited_once()

    def test_stream_chunk_does_not_fallback_to_old_progress_bubble_with_detail_off(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_CHAT_ID] = 123456
        ctx.data[handler.CTX_TG_BOT_CFG] = {"progress": {}}

        stream_data = {
            "full": json.dumps({
                "tool_name": "response",
                "tool_args": {"text": "Partial answer", "break_loop": True},
            })
        }

        with mock.patch.object(handler, "_send_telegram_live_draft_preview", new=mock.AsyncMock(return_value=False)) as send_draft, \
             mock.patch.object(handler, "send_telegram_progress_update", new=mock.AsyncMock()) as send_progress, \
             mock.patch.object(handler.detail_status, "effective_detail_level", return_value="off"), \
             mock.patch.object(handler.tc, "supports_message_draft", return_value=True):
            token = "tok"
            ctx.data[handler.CTX_TG_STREAM_WORKER_TOKEN] = token
            ctx.data[handler.CTX_TG_STREAM_PENDING_FULL] = stream_data["full"]
            asyncio.run(handler._flush_telegram_live_preview_once(ctx, token))

        send_draft.assert_awaited_once()
        send_progress.assert_not_called()

    def test_stream_chunk_falls_back_to_progress_when_native_draft_fails_with_detail_info(self):
        handler = self.handler
        ctx = _DummyAgentContext()
        ctx.data[handler.CTX_TG_CHAT_ID] = 123456
        ctx.data[handler.CTX_TG_BOT_CFG] = {"progress": {}}

        stream_data = {
            "full": json.dumps({
                "tool_name": "response",
                "tool_args": {"text": "Partial answer", "break_loop": True},
            })
        }

        with mock.patch.object(handler, "_send_telegram_live_draft_preview", new=mock.AsyncMock(return_value=False)) as send_draft, \
             mock.patch.object(handler, "send_telegram_progress_update", new=mock.AsyncMock()) as send_progress, \
             mock.patch.object(handler.detail_status, "effective_detail_level", return_value="info"), \
             mock.patch.object(handler.tc, "supports_message_draft", return_value=True):
            token = "tok"
            ctx.data[handler.CTX_TG_STREAM_WORKER_TOKEN] = token
            ctx.data[handler.CTX_TG_STREAM_PENDING_FULL] = stream_data["full"]
            asyncio.run(handler._flush_telegram_live_preview_once(ctx, token))

        send_draft.assert_awaited_once()
        send_progress.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
