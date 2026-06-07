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
    CTX_TG_DETAIL_ACTIVE_TOOL_LINE_INDEX,
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
                _replace_progress_line,
                _refresh_progress_status,
                _render_progress_status_html,
                _set_progress_phase,
                schedule_telegram_progress_update,
                send_telegram_progress_update,
            )

            bot_cfg = context.data.get(CTX_TG_BOT_CFG) or {}
            phase_changed = _set_progress_phase(context, None)
            level = ds.effective_detail_level(bot_cfg, context.data)
            before_enabled = ds.effective_execute_before_enabled(bot_cfg, context.data)
            active_tool = context.data.get(CTX_TG_DETAIL_ACTIVE_TOOL)
            active_index = context.data.get(CTX_TG_DETAIL_ACTIVE_TOOL_LINE_INDEX)
            if level == "off":
                context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL, None)
                context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL_LINE_INDEX, None)
                return
            if name in ds.detail_exclude_set(bot_cfg):
                if before_enabled and active_tool == name:
                    context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL, None)
                    context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL_LINE_INDEX, None)
                if phase_changed:
                    await _refresh_progress_status(context, bot_cfg, require_existing_message=True)
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

            line = ds.format_step_result_html(
                name,
                bot_cfg,
                level=level,
                tool_args=tool_args,
                response=response,
                known_secret_values=known_secret_values,
                agent=self.agent,
            )
            if inspect.isawaitable(line):
                line = await line
            now = time.monotonic()
            replaced = False
            if before_enabled and active_tool == name:
                replaced = _replace_progress_line(context, active_index, line, bot_cfg)
                context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL, None)
                context.data.pop(CTX_TG_DETAIL_ACTIVE_TOOL_LINE_INDEX, None)
            if not replaced:
                interval = ds.detail_throttle_sec(bot_cfg, level)
                last = context.data.get(CTX_TG_DETAIL_LAST_SENT_TS)
                if last is not None and (now - float(last)) < interval:
                    if phase_changed:
                        await _refresh_progress_status(context, bot_cfg, require_existing_message=True)
                    return
                _append_progress_line(context, line, bot_cfg)
            html_text = _render_progress_status_html(context, bot_cfg, done=False)
            context.data[CTX_TG_DETAIL_LAST_SENT_TS] = now
            if not schedule_telegram_progress_update(context, html_text, text_is_html=True):
                await send_telegram_progress_update(context, html_text, text_is_html=True)
        except Exception as e:
            PrintStyle.warning(f"Telegram detail status: {format_error(e)}")
