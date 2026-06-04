from helpers.extension import Extension
from usr.plugins.telegram_integration_voice.helpers.constants import CTX_TG_BOT
from usr.plugins.telegram_integration_voice.helpers.dependencies import ensure_dependencies


class TelegramLiveResponsePreview(Extension):

    async def execute(self, stream_data: dict | None = None, **kwargs):
        if not self.agent:
            return
        context = self.agent.context
        if not context.data.get(CTX_TG_BOT):
            return

        ensure_dependencies()
        from usr.plugins.telegram_integration_voice.helpers.handler import (
            handle_telegram_response_stream_chunk,
        )

        await handle_telegram_response_stream_chunk(context, stream_data)
