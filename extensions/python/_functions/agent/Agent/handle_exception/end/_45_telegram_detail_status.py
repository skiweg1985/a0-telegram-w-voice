import inspect
import time

from helpers.extension import Extension
from helpers.errors import format_error
from helpers.print_style import PrintStyle

from usr.plugins.telegram_integration_voice.helpers import detail_status as ds
from usr.plugins.telegram_integration_voice.helpers.constants import (
    CTX_TG_BOT,
    CTX_TG_BOT_CFG,
    CTX_TG_CHAT_ID,
    CTX_TG_DETAIL_ACTIVE_TOOL,
    CTX_TG_DETAIL_ACTIVE_TOOL_LINE_INDEX,
    CTX_TG_DETAIL_LAST_SENT_TS,
)


class TelegramDetailStatusException(Extension):
    """Replace the active tool-start line with a failure line when a tool raises."""

    async def execute(self, data: dict | None = None, **kwargs):
        if not self.agent or self.agent.number != 0:
            return
        context = self.agent.context
        if not context:
            return
        if not context.data.get(CTX_TG_BOT) or not context.data.get(CTX_TG_CHAT_ID):
            return
        active_tool = str(context.data.get(CTX_TG_DETAIL_ACTIVE_TOOL) or "").strip()
        if not active_tool:
            return
        try:
            from usr.plugins.telegram_integration_voice.helpers.handler import (
                _append_progress_line,
                _replace_progress_line,
                _render_progress_status_html,
                _set_progress_phase,
                schedule_telegram_progress_update,
                send_telegram_progress_update,
            )

            bot_cfg = context.data.get(CTX_TG_BOT_CFG) or {}
            level = ds.effective_detail_level(bot_cfg, context.data)
            if level == "off":
                context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL, None)
                context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL_LINE_INDEX, None)
                return

            exc = (data or {}).get("exception")
            error_text = format_error(exc) if exc else "Tool execution failed."
            known_secret_values = None
            if level in {"debug", "smart"}:
                try:
                    known_secret_values = ds.collect_known_secret_values(bot_cfg, self.agent)
                except Exception:
                    known_secret_values = None

            line = ds.format_step_result_html(
                active_tool,
                bot_cfg,
                level=level,
                response=None,
                error_text=error_text,
                known_secret_values=known_secret_values,
                agent=self.agent,
            )
            if inspect.isawaitable(line):
                line = await line

            replaced = _replace_progress_line(
                context,
                context.data.get(CTX_TG_DETAIL_ACTIVE_TOOL_LINE_INDEX),
                line,
                bot_cfg,
            )
            if not replaced:
                _append_progress_line(context, line, bot_cfg)

            _set_progress_phase(context, None)
            context.data[CTX_TG_DETAIL_LAST_SENT_TS] = time.monotonic()
            context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL, None)
            context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL_LINE_INDEX, None)

            html_text = _render_progress_status_html(context, bot_cfg, done=False)
            if not schedule_telegram_progress_update(context, html_text, text_is_html=True):
                await send_telegram_progress_update(context, html_text, text_is_html=True)
        except Exception as e:
            PrintStyle.warning(f"Telegram detail status exception hook failed: {format_error(e)}")
