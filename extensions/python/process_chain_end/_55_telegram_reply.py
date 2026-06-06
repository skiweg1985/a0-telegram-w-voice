from helpers.extension import Extension
from helpers.print_style import PrintStyle
from helpers.errors import format_error
from agent import AgentContext, LoopData, UserMessage
from usr.plugins.telegram_integration_voice.helpers.constants import (
    CTX_TG_BOT,
    CTX_TG_ATTACHMENTS,
    CTX_TG_ITEMS,
    CTX_TG_KEYBOARD,
    CTX_TG_TYPING_STOP,
    CTX_TG_REPLY_TO,
    CTX_TG_REPLY_CONTEXT,
    CTX_TG_VOICE_TEXT,
    CTX_TG_FINAL_REPLY_SENT,
)
from usr.plugins.telegram_integration_voice.helpers.dependencies import ensure_dependencies

MAX_SEND_RETRIES: int = 2
CTX_SEND_FAILURES: str = "_telegram_send_failures"


class TelegramAutoReply(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return
        if self.agent.number != 0:
            PrintStyle.warning(
                f"Telegram auto-reply skipped: agent.number={self.agent.number} "
                "(chain-end Telegram send and TTS only run for agent 0)."
            )
            return

        context = self.agent.context
        if not context.data.get(CTX_TG_BOT):
            return

        try:
            if context.data.get(CTX_TG_FINAL_REPLY_SENT):
                PrintStyle.info("Telegram auto-reply skipped: final response already sent.")
                return

            response_text = _extract_last_response(context)
            if not response_text:
                PrintStyle.info(
                    "Telegram auto-reply skipped: no response content in context log."
                )
                return

            attachments = context.data.pop(CTX_TG_ATTACHMENTS, [])
            telegram_items = context.data.pop(CTX_TG_ITEMS, [])
            keyboard = context.data.pop(CTX_TG_KEYBOARD, None)
            voice_text = context.data.pop(CTX_TG_VOICE_TEXT, None)

            await self._send_reply(
                context,
                response_text,
                attachments,
                telegram_items,
                keyboard,
                voice_text,
            )
        except Exception as e:
            PrintStyle.error(f"Telegram auto-reply error: {format_error(e)}")
        finally:
            # Cancel typing and clean up reply_to after final send
            typing_stop = context.data.pop(CTX_TG_TYPING_STOP, None)
            if typing_stop:
                typing_stop.set()
            context.data.pop(CTX_TG_REPLY_TO, None)
            context.data.pop(CTX_TG_REPLY_CONTEXT, None)
            context.data.pop(CTX_TG_ATTACHMENTS, None)
            context.data.pop(CTX_TG_ITEMS, None)
            context.data.pop(CTX_TG_KEYBOARD, None)
            context.data.pop(CTX_TG_VOICE_TEXT, None)
            context.data.pop(CTX_TG_FINAL_REPLY_SENT, None)
            _clear_telegram_progress_state(context)

    async def _send_reply(
        self,
        context: AgentContext,
        response_text: str,
        attachments: list[str],
        telegram_items: list[dict],
        keyboard: list[list[dict]] | None,
        voice_text: str | None = None,
    ):
        ensure_dependencies()
        from usr.plugins.telegram_integration_voice.helpers.handler import send_telegram_reply

        error = await send_telegram_reply(
            context,
            response_text,
            attachments or None,
            keyboard,
            voice_text=voice_text,
            telegram_items=telegram_items or None,
        )
        if not error:
            context.data[CTX_SEND_FAILURES] = 0
            context.data[CTX_TG_FINAL_REPLY_SENT] = True
            return

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

# Helpers

def _extract_last_response(context: AgentContext) -> str:
    with context.log._lock:
        logs = list(context.log.logs)
    if not logs:
        return ""
    for item in reversed(logs):
        if item.type == "response":
            return item.content or ""
    return ""


def _notify_agent_of_failure(
    context: AgentContext, error: str, attempt: int,
):
    msg = context.agent0.read_prompt(
        "fw.telegram.send_failed.md",
        error=error,
        attempt=str(attempt),
        max_retries=str(MAX_SEND_RETRIES),
    )
    context.log.log(type="error", heading="Telegram send failed", content=error)
    context.communicate(UserMessage(message="", system_message=[msg]))


def _clear_telegram_progress_state(context: AgentContext):
    try:
        from usr.plugins.telegram_integration_voice.helpers.handler import _clear_progress_state

        _clear_progress_state(context)
    except Exception as e:
        PrintStyle.warning(f"Telegram progress cleanup failed: {format_error(e)}")
