import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPT_HOOK_PATH = REPO_ROOT / "extensions" / "python" / "system_prompt" / "_20_telegram_context.py"


class _Extension:
    agent = None


class _LoopData:
    pass


def _install_stubs(*, rich_enabled=False, optimize_mode="off", also_send_text=False):
    helpers = types.ModuleType("helpers")
    helpers.__path__ = []
    sys.modules["helpers"] = helpers

    extension = types.ModuleType("helpers.extension")
    extension.Extension = _Extension
    sys.modules["helpers.extension"] = extension

    agent = types.ModuleType("agent")
    agent.LoopData = _LoopData
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

    speech = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.speech")
    speech.resolve_auto_optimize_mode = lambda bot_cfg, ctx_data: optimize_mode
    speech.effective_also_send_text = lambda bot_cfg, ctx_data: also_send_text
    sys.modules["usr.plugins.telegram_integration_voice.helpers.speech"] = speech

    tc = types.ModuleType("usr.plugins.telegram_integration_voice.helpers.telegram_client")
    tc.rich_messages_settings = lambda bot_cfg: {
        "enabled": rich_enabled,
        "drafts_enabled": False,
    }
    sys.modules["usr.plugins.telegram_integration_voice.helpers.telegram_client"] = tc
    return constants


def _load_prompt_hook(*, rich_enabled=False, optimize_mode="off", also_send_text=False):
    for name in list(sys.modules):
        if name.startswith("usr.plugins.telegram_integration_voice"):
            sys.modules.pop(name, None)
    constants = _install_stubs(
        rich_enabled=rich_enabled,
        optimize_mode=optimize_mode,
        also_send_text=also_send_text,
    )
    module_name = "telegram_system_prompt_under_test"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, PROMPT_HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module, constants


class _Agent:
    def __init__(self, data):
        self.context = types.SimpleNamespace(data=data)
        self.prompts = []

    def read_prompt(self, name, **kwargs):
        self.prompts.append((name, kwargs))
        return name


class TelegramSystemPromptTests(unittest.TestCase):
    def test_rich_prompt_not_loaded_when_disabled(self):
        module, constants = _load_prompt_hook(rich_enabled=False)
        agent = _Agent({
            constants.CTX_TG_BOT: "mainbot",
            constants.CTX_TG_BOT_CFG: {"rich_messages": {"enabled": False}},
        })
        ext = module.TelegramContextPrompt()
        ext.agent = agent
        system_prompt = []

        asyncio.run(ext.execute(system_prompt=system_prompt))

        self.assertEqual(system_prompt, ["fw.telegram.system_context_reply.md"])
        self.assertNotIn("fw.telegram.rich_messages.md", [p[0] for p in agent.prompts])

    def test_rich_prompt_loaded_when_enabled(self):
        module, constants = _load_prompt_hook(rich_enabled=True)
        agent = _Agent({
            constants.CTX_TG_BOT: "mainbot",
            constants.CTX_TG_BOT_CFG: {"rich_messages": {"enabled": True}},
        })
        ext = module.TelegramContextPrompt()
        ext.agent = agent
        system_prompt = []

        asyncio.run(ext.execute(system_prompt=system_prompt))

        self.assertEqual(system_prompt, [
            "fw.telegram.system_context_reply.md",
            "fw.telegram.rich_messages.md",
        ])

    def test_rich_prompt_precedes_text_optimize_prompt(self):
        module, constants = _load_prompt_hook(
            rich_enabled=True,
            optimize_mode="text",
            also_send_text=True,
        )
        agent = _Agent({
            constants.CTX_TG_BOT: "mainbot",
            constants.CTX_TG_BOT_CFG: {"rich_messages": {"enabled": True}},
        })
        ext = module.TelegramContextPrompt()
        ext.agent = agent
        system_prompt = []

        asyncio.run(ext.execute(system_prompt=system_prompt))

        self.assertEqual(system_prompt, [
            "fw.telegram.system_context_reply.md",
            "fw.telegram.rich_messages.md",
            "fw.telegram.optimize_output_text.md",
        ])
        self.assertEqual(
            agent.prompts[-1],
            ("fw.telegram.optimize_output_text.md", {"also_send_text": True}),
        )


if __name__ == "__main__":
    unittest.main()
