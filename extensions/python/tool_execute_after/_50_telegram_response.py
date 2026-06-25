from helpers.extension import Extension
from helpers.print_style import PrintStyle
from helpers.tool import Response
from agent import UserMessage
from usr.plugins.telegram_integration_voice.helpers.constants import (
    CTX_TG_BOT,
    CTX_TG_ATTACHMENTS,
    CTX_TG_ITEMS,
    CTX_TG_KEYBOARD,
    CTX_TG_VOICE_REPLY_MODE,
    CTX_TG_VOICE_TEXT,
    CTX_TG_FINAL_REPLY_SENT,
    CTX_TG_FINAL_REPLY_DELIVERED,
    CTX_TG_STREAM_RESPONSE_TEXT,
)
from usr.plugins.telegram_integration_voice.helpers.dependencies import ensure_dependencies

MAX_SEND_RETRIES: int = 2
CTX_SEND_FAILURES: str = "_telegram_send_failures"


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

        tool = getattr(getattr(self.agent, "loop_data", None), "current_tool", None)
        tool_args = _tool_args(tool)
        if not tool and not response:
            return

        # Capture attachments for later (process_chain_end) or inline send
        attachments = tool_args.get("attachments", [])
        if attachments:
            context.data[CTX_TG_ATTACHMENTS] = attachments

        telegram_items = tool_args.get("telegram_items", [])
        if telegram_items:
            context.data[CTX_TG_ITEMS] = telegram_items

        # Capture inline keyboard if provided
        keyboard = tool_args.get("keyboard", None)
        if keyboard:
            context.data[CTX_TG_KEYBOARD] = keyboard


        vt = tool_args.get("voice_text")
        if vt is not None and str(vt).strip():
            context.data[CTX_TG_VOICE_TEXT] = str(vt).strip()

        # voice_mode from agent response (handler enforces de-escalation only)
        voice_mode = str(tool_args.get("voice_mode", "")).strip().lower()
        if voice_mode in {"off", "auto", "force"}:
            context.data[CTX_TG_VOICE_REPLY_MODE] = voice_mode

        agent_break = _normalize_break_loop(tool_args.get("break_loop", getattr(response, "break_loop", True)))

        if (not agent_break) and response:
            await self._send_inline(context, tool, response)
            return

        if agent_break:
            await self._send_final(context, tool, response)

    async def _send_inline(self, context, tool, response: Response):
        ensure_dependencies()
        from usr.plugins.telegram_integration_voice.helpers.handler import (
            handle_telegram_response_stream_end,
            send_telegram_inline_response,
        )

        agent = self.agent
        assert agent is not None

        tool_args = _tool_args(tool)
        text = _response_text_from_tool(tool, response, context)
        attachments = context.data.pop(CTX_TG_ATTACHMENTS, [])
        telegram_items = context.data.pop(CTX_TG_ITEMS, [])
        keyboard = context.data.pop(CTX_TG_KEYBOARD, None)
        context.data.pop(CTX_TG_VOICE_TEXT, None)
        handle_telegram_response_stream_end(context)
        error = await send_telegram_inline_response(
            context,
            text,
            attachments or None,
            keyboard,
            telegram_items=telegram_items or None,
        )

        if error:
            result = agent.read_prompt("fw.telegram.update_error.md", error=error)
        else:
            result = agent.read_prompt("fw.telegram.update_ok.md")

        # Override response: don't break loop, add result to history
        response.break_loop = False
        response.message = result
        agent.hist_add_tool_result("response", result)

    async def _send_final(self, context, tool, response: Response | None = None):
        ensure_dependencies()
        from usr.plugins.telegram_integration_voice.helpers.handler import (
            _set_progress_phase,
            send_telegram_reply,
        )

        text = _response_text_from_tool(tool, response, context)
        attachments = context.data.get(CTX_TG_ATTACHMENTS, [])
        telegram_items = context.data.get(CTX_TG_ITEMS, [])
        keyboard = context.data.get(CTX_TG_KEYBOARD, None)
        voice_for_tts = context.data.get(CTX_TG_VOICE_TEXT, None)
        voice_mode = context.data.get(CTX_TG_VOICE_REPLY_MODE, None)
        _set_progress_phase(context, None)

        error = await send_telegram_reply(
            context,
            text,
            attachments or None,
            keyboard,
            voice_text=voice_for_tts,
            telegram_items=telegram_items or None,
        )

        delivered = bool(context.data.get(CTX_TG_FINAL_REPLY_DELIVERED))
        if not error and delivered:
            context.data[CTX_SEND_FAILURES] = 0
            context.data[CTX_TG_FINAL_REPLY_SENT] = True
            context.data.pop(CTX_TG_ATTACHMENTS, None)
            context.data.pop(CTX_TG_ITEMS, None)
            context.data.pop(CTX_TG_KEYBOARD, None)
            context.data.pop(CTX_TG_VOICE_TEXT, None)
            return

        if not error:
            if voice_mode is not None:
                context.data[CTX_TG_VOICE_REPLY_MODE] = voice_mode
            PrintStyle.warning(
                "Telegram final response hook did not confirm visible delivery; "
                "chain-end fallback remains enabled."
            )
            return

        if voice_mode is not None:
            context.data[CTX_TG_VOICE_REPLY_MODE] = voice_mode

        failures = context.data.get(CTX_SEND_FAILURES, 0) + 1
        context.data[CTX_SEND_FAILURES] = failures
        if failures <= MAX_SEND_RETRIES:
            _notify_agent_of_failure(context, error, failures)
        else:
            PrintStyle.error(
                f"Telegram send failed {failures} times, giving up: {error}"
            )
            context.log.log(
                type="error",
                heading="Telegram send failed (max retries reached)",
                content=error,
            )


def _normalize_break_loop(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    v = str(value).strip().lower()
    if v in {"false", "0", "no", "off"}:
        return False
    if v in {"true", "1", "yes", "on"}:
        return True
    return True


def _tool_args(tool) -> dict:
    args = getattr(tool, "args", None)
    return args if isinstance(args, dict) else {}


def _response_text_from_tool(tool, response: Response | None, context) -> str:
    args = _tool_args(tool)
    for value in (
        args.get("text"),
        args.get("message"),
        getattr(response, "message", None),
        context.data.get(CTX_TG_STREAM_RESPONSE_TEXT),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _notify_agent_of_failure(context, error: str, attempt: int):
    msg = context.agent0.read_prompt(
        "fw.telegram.send_failed.md",
        error=error,
        attempt=str(attempt),
        max_retries=str(MAX_SEND_RETRIES),
    )
    context.log.log(type="error", heading="Telegram send failed", content=error)
    context.communicate(UserMessage(message="", system_message=[msg]))
