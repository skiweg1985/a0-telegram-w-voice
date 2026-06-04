import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_HOOK_PATH = REPO_ROOT / "extensions" / "python" / "tool_execute_after" / "_50_telegram_response.py"
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

    handler = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.handler")
    handler.send_telegram_reply = mock.AsyncMock(return_value=None)
    handler.send_telegram_progress_update = mock.AsyncMock(return_value=None)
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
        )
        self.assertTrue(context.data[constants.CTX_TG_FINAL_REPLY_SENT])
        self.assertNotIn(constants.CTX_TG_ATTACHMENTS, context.data)
        self.assertNotIn(constants.CTX_TG_KEYBOARD, context.data)
        self.assertNotIn(constants.CTX_TG_VOICE_TEXT, context.data)

    def test_break_loop_false_still_uses_inline_progress_update(self):
        constants, handler = _install_stubs()
        module = _load_module(TOOL_HOOK_PATH, "telegram_response_hook_inline_under_test")

        context = types.SimpleNamespace(data={constants.CTX_TG_BOT: "mainbot"})
        response = _Response()
        agent = _fake_agent({"text": "Working", "break_loop": False}, context)
        ext = module.TelegramResponseIntercept()
        ext.agent = agent

        asyncio.run(ext.execute(tool_name="response", response=response))

        handler.send_telegram_progress_update.assert_awaited_once_with(context, "Working", None)
        handler.send_telegram_reply.assert_not_awaited()
        self.assertFalse(response.break_loop)
        self.assertEqual(response.message, "ok")
        agent.hist_add_tool_result.assert_called_once_with("response", "ok")

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


if __name__ == "__main__":
    unittest.main()
