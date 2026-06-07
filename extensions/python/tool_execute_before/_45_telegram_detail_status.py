import time
import inspect

from helpers.extension import Extension
from helpers.errors import format_error
from helpers.print_style import PrintStyle

from usr.plugins.telegram_integration_voice.helpers import detail_status as ds
from usr.plugins.telegram_integration_voice.helpers.constants import (
    CTX_TG_BOT,
    CTX_TG_BOT_CFG,
    CTX_TG_CHAT_ID,
    CTX_TG_DETAIL_ACTIVE_TOOL,
    CTX_TG_DETAIL_LAST_SENT_TS,
)


class TelegramDetailStatusBefore(Extension):
    """Optionally send throttled HTML status lines when a tool starts (except response)."""

    async def execute(self, tool_name: str = "", **kwargs):
        if not self.agent or self.agent.number != 0:
            return
        name = (tool_name or "").strip()
        if not name or name == "response":
            return
        context = self.agent.context
        if not context:
            return
        if not context.data.get(CTX_TG_BOT) or not context.data.get(CTX_TG_CHAT_ID):
            return
        try:
            from usr.plugins.telegram_integration_voice.helpers.handler import (
                _append_progress_line,
                _render_progress_status_html,
                schedule_telegram_progress_update,
                send_telegram_progress_update,
            )

            bot_cfg = context.data.get(CTX_TG_BOT_CFG) or {}
            level = ds.effective_detail_level(bot_cfg, context.data)
            if level == "off":
                context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL, None)
                return
            if not ds.effective_execute_before_enabled(bot_cfg, context.data):
                context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL, None)
                return
            if name in ds.detail_exclude_set(bot_cfg):
                context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL, None)
                return
            interval = ds.detail_throttle_sec(bot_cfg, level)
            now = time.monotonic()
            last = context.data.get(CTX_TG_DETAIL_LAST_SENT_TS)
            if last is not None and (now - float(last)) < interval:
                context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL, None)
                return

            tool_args = None
            known_secret_values = None
            if level in {"debug", "smart"}:
                try:
                    current_tool = self.agent.loop_data.current_tool if self.agent else None
                    if current_tool is not None:
                        tool_args = getattr(current_tool, "args", None)
                except Exception:
                    tool_args = None
                try:
                    known_secret_values = ds.collect_known_secret_values(bot_cfg, self.agent)
                except Exception:
                    known_secret_values = None

            line = ds.format_step_html(
                name,
                bot_cfg,
                level=level,
                tool_args=tool_args,
                known_secret_values=known_secret_values,
                agent=self.agent,
            )
            if inspect.isawaitable(line):
                line = await line
            _append_progress_line(context, line, bot_cfg)
            html_text = _render_progress_status_html(context, bot_cfg, done=False)
            context.data[CTX_TG_DETAIL_LAST_SENT_TS] = now
            context.data[CTX_TG_DETAIL_ACTIVE_TOOL] = name
            if not schedule_telegram_progress_update(context, html_text, text_is_html=True):
                await send_telegram_progress_update(context, html_text, text_is_html=True)
        except Exception as e:
            PrintStyle.warning(f"Telegram detail status before: {format_error(e)}")
