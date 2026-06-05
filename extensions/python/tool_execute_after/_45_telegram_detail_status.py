import time

from helpers.extension import Extension
from helpers.errors import format_error
from helpers.print_style import PrintStyle

from usr.plugins.telegram_integration_voice.helpers import detail_status as ds
from usr.plugins.telegram_integration_voice.helpers.constants import (
    CTX_TG_BOT,
    CTX_TG_BOT_CFG,
    CTX_TG_CHAT_ID,
    CTX_TG_DETAIL_LAST_SENT_TS,
)


class TelegramDetailStatus(Extension):
    """Send throttled HTML status lines after each tool (except response) when detail is info/debug."""

    async def execute(self, tool_name: str = "", response=None, **kwargs):
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
                _refresh_progress_status,
                _render_progress_status_html,
                _set_progress_phase,
                schedule_telegram_progress_update,
                send_telegram_progress_update,
            )

            bot_cfg = context.data.get(CTX_TG_BOT_CFG) or {}
            phase_changed = _set_progress_phase(context, None)
            level = ds.effective_detail_level(bot_cfg, context.data)
            if level == "off":
                return
            if name in ds.detail_exclude_set(bot_cfg):
                if phase_changed:
                    await _refresh_progress_status(context, bot_cfg, require_existing_message=True)
                return
            interval = ds.detail_throttle_sec(bot_cfg, level)
            now = time.monotonic()
            last = context.data.get(CTX_TG_DETAIL_LAST_SENT_TS)
            if last is not None and (now - float(last)) < interval:
                if phase_changed:
                    await _refresh_progress_status(context, bot_cfg, require_existing_message=True)
                return

            tool_args = None
            if level == "debug":
                try:
                    current_tool = self.agent.loop_data.current_tool if self.agent else None
                    if current_tool is not None:
                        tool_args = getattr(current_tool, "args", None)
                except Exception:
                    tool_args = None

            line = ds.format_step_html(name, bot_cfg, level=level, tool_args=tool_args)
            _append_progress_line(context, line, bot_cfg)
            html_text = _render_progress_status_html(context, bot_cfg, done=False)
            context.data[CTX_TG_DETAIL_LAST_SENT_TS] = now
            if not schedule_telegram_progress_update(context, html_text, text_is_html=True):
                await send_telegram_progress_update(context, html_text, text_is_html=True)
        except Exception as e:
            PrintStyle.warning(f"Telegram detail status: {format_error(e)}")
