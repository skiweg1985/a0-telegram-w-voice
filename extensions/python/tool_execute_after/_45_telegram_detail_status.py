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
        bot_cfg = context.data.get(CTX_TG_BOT_CFG) or {}
        level = ds.effective_detail_level(bot_cfg, context.data)
        if level == "off":
            return
        if name in ds.detail_exclude_set(bot_cfg):
            return
        interval = ds.detail_throttle_sec(bot_cfg, level)
        now = time.monotonic()
        last = context.data.get(CTX_TG_DETAIL_LAST_SENT_TS)
        if last is not None and (now - float(last)) < interval:
            return
        try:
            from usr.plugins.telegram_integration_voice.helpers.handler import (
                send_telegram_ephemeral_status,
            )

            html_line = ds.format_step_html(name, bot_cfg)
            await send_telegram_ephemeral_status(context, html_line)
            context.data[CTX_TG_DETAIL_LAST_SENT_TS] = now
        except Exception as e:
            PrintStyle.warning(f"Telegram detail status: {format_error(e)}")
