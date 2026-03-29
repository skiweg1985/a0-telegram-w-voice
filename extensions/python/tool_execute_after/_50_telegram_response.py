from helpers.extension import Extension
from helpers.tool import Response
from usr.plugins.telegram_integration_voice.helpers.constants import (
    CTX_TG_BOT,
    CTX_TG_ATTACHMENTS,
    CTX_TG_KEYBOARD,
    CTX_TG_VOICE_REPLY_MODE,
    CTX_TG_FORCE_VOICE_REPLY,
    CTX_TG_VOICE_TEXT,
)
from usr.plugins.telegram_integration_voice.helpers.dependencies import ensure_dependencies


class TelegramResponseIntercept(Extension):

    async def execute(
        self, tool_name: str = "", response: Response | None = None, **kwargs,
    ):
        if tool_name != "response":
            return
        if not self.agent:
            return
        context = self.agent.context
        if not context.data.get(CTX_TG_BOT):
            return

        tool = self.agent.loop_data.current_tool
        if not tool:
            return

        # Capture attachments for later (process_chain_end) or inline send
        attachments = tool.args.get("attachments", [])
        if attachments:
            context.data[CTX_TG_ATTACHMENTS] = attachments

        # Capture inline keyboard if provided
        keyboard = tool.args.get("keyboard", None)
        if keyboard:
            context.data[CTX_TG_KEYBOARD] = keyboard


        vt = tool.args.get("voice_text")
        if vt is not None and str(vt).strip():
            context.data[CTX_TG_VOICE_TEXT] = str(vt).strip()

        # Optional voice behavior override from agent response tool
        # supported args: voice_mode = off|auto|force, voice = true|false
        voice_mode = str(tool.args.get("voice_mode", "")).strip().lower()
        if voice_mode in {"off", "auto", "force"}:
            context.data[CTX_TG_VOICE_REPLY_MODE] = voice_mode

        if "voice" in tool.args:
            v = tool.args.get("voice")
            v_bool = bool(v) if isinstance(v, bool) else str(v).strip().lower() in {"1", "true", "yes", "on"}
            context.data[CTX_TG_FORCE_VOICE_REPLY] = v_bool

        # Check break_loop arg from agent
        agent_break = tool.args.get("break_loop", True)
        if agent_break is False and response:
            await self._send_inline(context, tool, response)

    async def _send_inline(self, context, tool, response: Response):
        ensure_dependencies()
        from usr.plugins.telegram_integration_voice.helpers.handler import (
            send_telegram_reply,
            send_telegram_progress_update,
        )

        agent = self.agent
        assert agent is not None

        text = tool.args.get("text", tool.args.get("message", ""))
        attachments = context.data.pop(CTX_TG_ATTACHMENTS, [])
        keyboard = context.data.pop(CTX_TG_KEYBOARD, None)
        voice_for_tts = context.data.pop(CTX_TG_VOICE_TEXT, None)

        # Inline progress updates use message editing when possible.
        # If attachments are included, fallback to normal send flow.
        if attachments:
            error = await send_telegram_reply(
                context, text, attachments or None, keyboard, voice_text=voice_for_tts,
            )
        else:
            error = await send_telegram_progress_update(context, text, keyboard)

        if error:
            result = agent.read_prompt("fw.telegram.update_error.md", error=error)
        else:
            result = agent.read_prompt("fw.telegram.update_ok.md")

        # Override response: don't break loop, add result to history
        response.break_loop = False
        response.message = result
        agent.hist_add_tool_result("response", result)
