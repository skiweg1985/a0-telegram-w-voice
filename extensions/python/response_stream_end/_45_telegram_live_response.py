from helpers.extension import Extension
from usr.plugins.telegram_integration_voice.helpers.constants import CTX_TG_BOT
from usr.plugins.telegram_integration_voice.helpers.dependencies import ensure_dependencies


class TelegramLiveResponsePreviewEnd(Extension):

    async def execute(self, **kwargs):
        if not self.agent:
            return
        context = self.agent.context
        if not context.data.get(CTX_TG_BOT):
            return

        ensure_dependencies()
        from usr.plugins.telegram_integration_voice.helpers.handler import (
            handle_telegram_response_stream_end,
        )

        handle_telegram_response_stream_end(context)
