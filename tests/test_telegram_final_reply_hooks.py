import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_HOOK_PATH = REPO_ROOT / "extensions" / "python" / "tool_execute_after" / "_50_telegram_response.py"
DETAIL_HOOK_PATH = REPO_ROOT / "extensions" / "python" / "tool_execute_after" / "_45_telegram_detail_status.py"
DETAIL_BEFORE_HOOK_PATH = REPO_ROOT / "extensions" / "python" / "tool_execute_before" / "_45_telegram_detail_status.py"
CHAIN_HOOK_PATH = REPO_ROOT / "extensions" / "python" / "process_chain_end" / "_55_telegram_reply.py"


class _Extension:
    agent = None


class _Response:
    def __init__(self):
        self.break_loop = True
        self.message = ""


class _PrintStyle:
    @staticmethod
    def info(*args, **kwargs):
        return None

    @staticmethod
    def warning(*args, **kwargs):
        return None

    @staticmethod
    def error(*args, **kwargs):
        return None


class _UserMessage:
    def __init__(self, message="", system_message=None):
        self.message = message
        self.system_message = system_message or []


class _Log:
    def __init__(self):
        self.logs = []
        self._lock = mock.MagicMock()
        self._lock.__enter__.return_value = None
        self._lock.__exit__.return_value = False

    def log(self, **kwargs):
        self.logs.append(types.SimpleNamespace(**kwargs))


def _install_stubs():
    helpers = types.ModuleType("helpers")
    helpers.__path__ = []
    sys.modules["helpers"] = helpers

    extension = types.ModuleType("helpers.extension")
    extension.Extension = _Extension
    sys.modules["helpers.extension"] = extension

    tool = types.ModuleType("helpers.tool")
    tool.Response = _Response
    sys.modules["helpers.tool"] = tool

    print_style = types.ModuleType("helpers.print_style")
    print_style.PrintStyle = _PrintStyle
    sys.modules["helpers.print_style"] = print_style

    errors = types.ModuleType("helpers.errors")
    errors.format_error = lambda e: str(e)
    sys.modules["helpers.errors"] = errors

    agent = types.ModuleType("agent")
    agent.AgentContext = object
    agent.LoopData = lambda: types.SimpleNamespace()
    agent.UserMessage = _UserMessage
    sys.modules["agent"] = agent

    usr = types.ModuleType("usr")
    usr.__path__ = []
    sys.modules["usr"] = usr

    usr_plugins = types.ModuleType("usr.plugins")
    usr_plugins.__path__ = []
    sys.modules["usr.plugins"] = usr_plugins

    telegram_pkg = types.ModuleType("usr.plugins.telegram_integration_voice")
    telegram_pkg.__path__ = []
    sys.modules["usr.plugins.telegram_integration_voice"] = telegram_pkg

    telegram_helpers = types.ModuleType("usr.plugins.telegram_integration_voice.helpers")
    telegram_helpers.__path__ = []
    sys.modules["usr.plugins.telegram_integration_voice.helpers"] = telegram_helpers

    constants_spec = importlib.util.spec_from_file_location(
        "usr.plugins.telegram_integration_voice.helpers.constants",
        REPO_ROOT / "helpers" / "constants.py",
    )
    constants = importlib.util.module_from_spec(constants_spec)
    sys.modules[constants_spec.name] = constants
    constants_spec.loader.exec_module(constants)

    dependencies = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.dependencies")
    dependencies.ensure_dependencies = lambda: None
    sys.modules["usr.plugins.telegram_integration_voice.helpers.dependencies"] = dependencies

    detail_status = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.detail_status")
    detail_status.effective_detail_level = lambda bot_cfg, ctx_data: "info"
    detail_status.effective_execute_before_enabled = lambda bot_cfg, ctx_data: False
    detail_status.detail_exclude_set = lambda bot_cfg: set()
    detail_status.detail_throttle_sec = lambda bot_cfg, level: 5.0
    detail_status.format_step_html = lambda name, bot_cfg, level="info", tool_args=None, known_secret_values=None, agent=None: f"step:{name}"
    sys.modules["usr.plugins.telegram_integration_voice.helpers.detail_status"] = detail_status

    handler = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.handler")
    handler._append_progress_line = mock.Mock()
    handler.handle_telegram_response_stream_end = mock.Mock()
    handler.send_telegram_inline_response = mock.AsyncMock(return_value=None)
    handler.send_telegram_reply = mock.AsyncMock(return_value=None)
    handler.send_telegram_progress_update = mock.AsyncMock(return_value=None)
    handler._refresh_progress_status = mock.AsyncMock(return_value=None)
    handler._render_progress_status_html = mock.Mock(return_value="<b>status</b>")
    handler.schedule_telegram_progress_update = mock.Mock(return_value=False)
    handler._set_progress_phase = mock.Mock(return_value=True)
    handler._clear_progress_state = mock.Mock()
    sys.modules["usr.plugins.telegram_integration_voice.helpers.handler"] = handler

    return constants, handler


def _load_module(path: Path, name: str):
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fake_agent(args, context):
    tool = types.SimpleNamespace(args=args)
    return types.SimpleNamespace(
        context=context,
        number=0,
        loop_data=types.SimpleNamespace(current_tool=tool),
        read_prompt=lambda name, **kwargs: "ok",
        call_utility_model=mock.AsyncMock(return_value="smart summary"),
        hist_add_tool_result=mock.Mock(),
    )


class TelegramFinalReplyHookTests(unittest.TestCase):
    def test_break_loop_true_final_response_sends_from_tool_execute_after(self):
        constants, handler = _install_stubs()
        module = _load_module(TOOL_HOOK_PATH, "telegram_response_hook_under_test")

        context = types.SimpleNamespace(
            data={
                constants.CTX_TG_BOT: "mainbot",
                constants.CTX_TG_CHAT_ID: 123,
            },
            log=_Log(),
            agent0=types.SimpleNamespace(read_prompt=lambda *a, **k: "retry"),
            communicate=mock.Mock(),
        )
        ext = module.TelegramResponseIntercept()
        ext.agent = _fake_agent(
            {
                "text": "Final answer",
                "attachments": ["/tmp/a.txt"],
                "keyboard": [[{"text": "Open", "url": "https://example.com"}]],
                "voice_text": "Final voice",
                "voice_mode": "off",
                "break_loop": True,
            },
            context,
        )

        asyncio.run(ext.execute(tool_name="response", response=_Response()))

        handler.send_telegram_reply.assert_awaited_once_with(
            context,
            "Final answer",
            ["/tmp/a.txt"],
            [[{"text": "Open", "url": "https://example.com"}]],
            voice_text="Final voice",
            telegram_items=None,
        )
        self.assertTrue(context.data[constants.CTX_TG_FINAL_REPLY_SENT])
        self.assertNotIn(constants.CTX_TG_ATTACHMENTS, context.data)
        self.assertNotIn(constants.CTX_TG_KEYBOARD, context.data)
        self.assertNotIn(constants.CTX_TG_VOICE_TEXT, context.data)

    def test_break_loop_false_sends_persistent_inline_message(self):
        constants, handler = _install_stubs()
        module = _load_module(TOOL_HOOK_PATH, "telegram_response_hook_inline_under_test")

        context = types.SimpleNamespace(data={constants.CTX_TG_BOT: "mainbot"})
        response = _Response()
        agent = _fake_agent({"text": "Working", "break_loop": False}, context)
        ext = module.TelegramResponseIntercept()
        ext.agent = agent

        asyncio.run(ext.execute(tool_name="response", response=response))

        handler.handle_telegram_response_stream_end.assert_called_once_with(context)
        handler.send_telegram_inline_response.assert_awaited_once_with(
            context,
            "Working",
            None,
            None,
            telegram_items=None,
        )
        handler.send_telegram_progress_update.assert_not_awaited()
        handler.send_telegram_reply.assert_not_awaited()
        self.assertFalse(response.break_loop)
        self.assertEqual(response.message, "ok")
        agent.hist_add_tool_result.assert_called_once_with("response", "ok")

    def test_telegram_items_are_forwarded_for_final_and_inline_replies(self):
        constants, handler = _install_stubs()
        module = _load_module(TOOL_HOOK_PATH, "telegram_response_hook_items_under_test")

        final_context = types.SimpleNamespace(
            data={
                constants.CTX_TG_BOT: "mainbot",
                constants.CTX_TG_CHAT_ID: 123,
            },
            log=_Log(),
            agent0=types.SimpleNamespace(read_prompt=lambda *a, **k: "retry"),
            communicate=mock.Mock(),
        )
        final_ext = module.TelegramResponseIntercept()
        final_ext.agent = _fake_agent(
            {
                "text": "Pinned",
                "telegram_items": [
                    {"type": "location", "latitude": 1, "longitude": 2},
                ],
                "break_loop": True,
            },
            final_context,
        )

        asyncio.run(final_ext.execute(tool_name="response", response=_Response()))

        handler.send_telegram_reply.assert_awaited_once_with(
            final_context,
            "Pinned",
            None,
            None,
            voice_text=None,
            telegram_items=[{"type": "location", "latitude": 1, "longitude": 2}],
        )
        self.assertNotIn(constants.CTX_TG_ITEMS, final_context.data)

        handler.send_telegram_reply.reset_mock()
        handler.send_telegram_inline_response.reset_mock()
        handler.handle_telegram_response_stream_end.reset_mock()

        inline_context = types.SimpleNamespace(data={constants.CTX_TG_BOT: "mainbot"})
        inline_response = _Response()
        inline_ext = module.TelegramResponseIntercept()
        inline_ext.agent = _fake_agent(
            {
                "text": "Map",
                "telegram_items": [
                    {"type": "venue", "latitude": 1, "longitude": 2, "title": "HQ", "address": "Street"},
                ],
                "break_loop": False,
            },
            inline_context,
        )

        asyncio.run(inline_ext.execute(tool_name="response", response=inline_response))

        handler.send_telegram_inline_response.assert_awaited_once_with(
            inline_context,
            "Map",
            None,
            None,
            telegram_items=[{"type": "venue", "latitude": 1, "longitude": 2, "title": "HQ", "address": "Street"}],
        )

    def test_break_loop_true_clears_gen_phase_before_final_reply(self):
        constants, handler = _install_stubs()
        module = _load_module(TOOL_HOOK_PATH, "telegram_response_hook_final_phase_under_test")

        context = types.SimpleNamespace(
            data={
                constants.CTX_TG_BOT: "mainbot",
                constants.CTX_TG_CHAT_ID: 123,
            },
            log=_Log(),
            agent0=types.SimpleNamespace(read_prompt=lambda *a, **k: "retry"),
            communicate=mock.Mock(),
        )
        ext = module.TelegramResponseIntercept()
        ext.agent = _fake_agent({"text": "Final answer", "break_loop": True}, context)

        asyncio.run(ext.execute(tool_name="response", response=_Response()))

        handler._set_progress_phase.assert_called_once_with(context, None)

    def test_process_chain_end_skips_when_final_response_already_sent(self):
        constants, handler = _install_stubs()
        module = _load_module(CHAIN_HOOK_PATH, "telegram_chain_end_hook_under_test")

        context = types.SimpleNamespace(
            data={
                constants.CTX_TG_BOT: "mainbot",
                constants.CTX_TG_FINAL_REPLY_SENT: True,
                constants.CTX_TG_TYPING_STOP: types.SimpleNamespace(set=mock.Mock()),
            },
            log=_Log(),
        )
        ext = module.TelegramAutoReply()
        ext.agent = types.SimpleNamespace(context=context, number=0)
        ext._send_reply = mock.AsyncMock()

        asyncio.run(ext.execute())

        ext._send_reply.assert_not_awaited()
        self.assertNotIn(constants.CTX_TG_FINAL_REPLY_SENT, context.data)
        handler._clear_progress_state.assert_called_once_with(context)

    def test_detail_status_clears_gen_phase_even_when_tool_line_is_throttled(self):
        constants, handler = _install_stubs()
        module = _load_module(DETAIL_HOOK_PATH, "telegram_detail_hook_under_test")

        context = types.SimpleNamespace(
            data={
                constants.CTX_TG_BOT: "mainbot",
                constants.CTX_TG_CHAT_ID: 123,
                constants.CTX_TG_BOT_CFG: {},
                constants.CTX_TG_DETAIL_LAST_SENT_TS: 0.0,
            },
            log=_Log(),
        )
        ext = module.TelegramDetailStatus()
        ext.agent = types.SimpleNamespace(
            context=context,
            number=0,
            loop_data=types.SimpleNamespace(current_tool=types.SimpleNamespace(args={})),
        )

        with mock.patch.object(module.time, "monotonic", return_value=1.0):
            asyncio.run(ext.execute(tool_name="search_engine"))

        handler._set_progress_phase.assert_called_once_with(context, None)
        handler._refresh_progress_status.assert_awaited_once_with(
            context,
            {},
            require_existing_message=True,
        )
        handler.send_telegram_progress_update.assert_not_awaited()

    def test_detail_before_hook_sends_progress_line_when_enabled(self):
        constants, handler = _install_stubs()
        sys.modules["usr.plugins.telegram_integration_voice.helpers.detail_status"].effective_execute_before_enabled = (
            lambda bot_cfg, ctx_data: True
        )
        module = _load_module(DETAIL_BEFORE_HOOK_PATH, "telegram_detail_before_hook_under_test")

        context = types.SimpleNamespace(
            data={
                constants.CTX_TG_BOT: "mainbot",
                constants.CTX_TG_CHAT_ID: 123,
                constants.CTX_TG_BOT_CFG: {},
            },
            log=_Log(),
        )
        ext = module.TelegramDetailStatusBefore()
        ext.agent = types.SimpleNamespace(
            context=context,
            number=0,
            loop_data=types.SimpleNamespace(current_tool=types.SimpleNamespace(args={})),
        )

        with mock.patch.object(module.time, "monotonic", return_value=10.0):
            asyncio.run(ext.execute(tool_name="search_engine"))

        handler._append_progress_line.assert_called_once_with(context, "step:search_engine", {})
        handler.send_telegram_progress_update.assert_awaited_once_with(
            context,
            "<b>status</b>",
            text_is_html=True,
        )
        self.assertEqual(context.data[constants.CTX_TG_DETAIL_ACTIVE_TOOL], "search_engine")

    def test_detail_hook_smart_uses_utility_model_summary(self):
        constants, handler = _install_stubs()
        detail_status = sys.modules["usr.plugins.telegram_integration_voice.helpers.detail_status"]
        detail_status.effective_detail_level = lambda bot_cfg, ctx_data: "smart"
        detail_status.format_step_html = mock.AsyncMock(return_value="step:smart")
        module = _load_module(DETAIL_HOOK_PATH, "telegram_detail_hook_smart_under_test")

        context = types.SimpleNamespace(
            data={
                constants.CTX_TG_BOT: "mainbot",
                constants.CTX_TG_CHAT_ID: 123,
                constants.CTX_TG_BOT_CFG: {},
            },
            log=_Log(),
        )
        ext = module.TelegramDetailStatus()
        ext.agent = _fake_agent({"url": "https://example.com"}, context)

        with mock.patch.object(module.time, "monotonic", return_value=10.0):
            asyncio.run(ext.execute(tool_name="browser:navigate"))

        detail_status.format_step_html.assert_awaited()
        call = detail_status.format_step_html.await_args
        self.assertEqual(call.kwargs["level"], "smart")
        self.assertEqual(call.kwargs["tool_args"], {"url": "https://example.com"})
        handler._append_progress_line.assert_called_once_with(context, "step:smart", {})

    def test_detail_before_hook_smart_passes_tool_args(self):
        constants, handler = _install_stubs()
        detail_status = sys.modules["usr.plugins.telegram_integration_voice.helpers.detail_status"]
        detail_status.effective_execute_before_enabled = lambda bot_cfg, ctx_data: True
        detail_status.effective_detail_level = lambda bot_cfg, ctx_data: "smart"
        detail_status.format_step_html = mock.AsyncMock(return_value="step:smart-before")
        module = _load_module(DETAIL_BEFORE_HOOK_PATH, "telegram_detail_before_hook_smart_under_test")

        context = types.SimpleNamespace(
            data={
                constants.CTX_TG_BOT: "mainbot",
                constants.CTX_TG_CHAT_ID: 123,
                constants.CTX_TG_BOT_CFG: {},
            },
            log=_Log(),
        )
        ext = module.TelegramDetailStatusBefore()
        ext.agent = _fake_agent({"query": "status page"}, context)

        with mock.patch.object(module.time, "monotonic", return_value=10.0):
            asyncio.run(ext.execute(tool_name="web_search"))

        call = detail_status.format_step_html.await_args
        self.assertEqual(call.kwargs["level"], "smart")
        self.assertEqual(call.kwargs["tool_args"], {"query": "status page"})
        handler._append_progress_line.assert_called_once_with(context, "step:smart-before", {})

    def test_detail_before_hook_throttle_does_not_set_dedupe_marker(self):
        constants, handler = _install_stubs()
        sys.modules["usr.plugins.telegram_integration_voice.helpers.detail_status"].effective_execute_before_enabled = (
            lambda bot_cfg, ctx_data: True
        )
        module = _load_module(DETAIL_BEFORE_HOOK_PATH, "telegram_detail_before_hook_throttle_under_test")

        context = types.SimpleNamespace(
            data={
                constants.CTX_TG_BOT: "mainbot",
                constants.CTX_TG_CHAT_ID: 123,
                constants.CTX_TG_BOT_CFG: {},
                constants.CTX_TG_DETAIL_LAST_SENT_TS: 9.5,
                constants.CTX_TG_DETAIL_ACTIVE_TOOL: "previous_tool",
            },
            log=_Log(),
        )
        ext = module.TelegramDetailStatusBefore()
        ext.agent = types.SimpleNamespace(
            context=context,
            number=0,
            loop_data=types.SimpleNamespace(current_tool=types.SimpleNamespace(args={})),
        )

        with mock.patch.object(module.time, "monotonic", return_value=10.0):
            asyncio.run(ext.execute(tool_name="search_engine"))

        handler._append_progress_line.assert_not_called()
        handler.send_telegram_progress_update.assert_not_awaited()
        self.assertNotIn(constants.CTX_TG_DETAIL_ACTIVE_TOOL, context.data)

    def test_detail_after_hook_skips_duplicate_line_when_before_hook_already_emitted_it(self):
        constants, handler = _install_stubs()
        sys.modules["usr.plugins.telegram_integration_voice.helpers.detail_status"].effective_execute_before_enabled = (
            lambda bot_cfg, ctx_data: True
        )
        module = _load_module(DETAIL_HOOK_PATH, "telegram_detail_hook_dedupe_under_test")

        context = types.SimpleNamespace(
            data={
                constants.CTX_TG_BOT: "mainbot",
                constants.CTX_TG_CHAT_ID: 123,
                constants.CTX_TG_BOT_CFG: {},
                constants.CTX_TG_DETAIL_ACTIVE_TOOL: "search_engine",
            },
            log=_Log(),
        )
        ext = module.TelegramDetailStatus()
        ext.agent = types.SimpleNamespace(
            context=context,
            number=0,
            loop_data=types.SimpleNamespace(current_tool=types.SimpleNamespace(args={})),
        )

        asyncio.run(ext.execute(tool_name="search_engine"))

        handler._append_progress_line.assert_not_called()
        handler._refresh_progress_status.assert_awaited_once_with(
            context,
            {},
            require_existing_message=True,
        )
        self.assertNotIn(constants.CTX_TG_DETAIL_ACTIVE_TOOL, context.data)


if __name__ == "__main__":
    unittest.main()
