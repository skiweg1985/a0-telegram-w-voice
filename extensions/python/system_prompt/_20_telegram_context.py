from helpers.extension import Extension
from agent import LoopData
from usr.plugins.telegram_integration_voice.helpers.constants import (
    CTX_TG_BOT,
    CTX_TG_BOT_CFG,
)
from usr.plugins.telegram_integration_voice.helpers import speech


class TelegramContextPrompt(Extension):

    async def execute(
        self,
        system_prompt: list[str] = [],
        loop_data: LoopData = LoopData(),
        **kwargs,
    ):
        if not self.agent:
            return

        if self.agent.context.data.get(CTX_TG_BOT):
            system_prompt.append(
                self.agent.read_prompt("fw.telegram.system_context_reply.md")
            )

            bot_cfg = self.agent.context.data.get(CTX_TG_BOT_CFG, {}) or {}
            mode = speech.effective_output_optimize_mode(
                bot_cfg, self.agent.context.data,
            )
            if mode == "voice":
                system_prompt.append(
                    self.agent.read_prompt("fw.telegram.optimize_output_voice.md")
                )
            elif mode == "text":
                system_prompt.append(
                    self.agent.read_prompt("fw.telegram.optimize_output_text.md")
                )

            # Inject per-bot agent instructions (once in system prompt)
            instructions = bot_cfg.get("agent_instructions", "")
            if instructions:
                system_prompt.append(
                    self.agent.read_prompt(
                        "fw.telegram.user_message_instructions.md",
                        instructions=instructions,
                    )
                )
