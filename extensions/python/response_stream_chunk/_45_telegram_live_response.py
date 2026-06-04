from helpers.extension import Extension
from usr.plugins.telegram_integration_voice.helpers.constants import CTX_TG_BOT
from usr.plugins.telegram_integration_voice.helpers.dependencies import ensure_dependencies

_HANDLE_STREAM_CHUNK = None


def _get_handle_stream_chunk():
    global _HANDLE_STREAM_CHUNK
    if _HANDLE_STREAM_CHUNK is None:
        ensure_dependencies()
        from usr.plugins.telegram_integration_voice.helpers.handler import (
            handle_telegram_response_stream_chunk,
        )

        _HANDLE_STREAM_CHUNK = handle_telegram_response_stream_chunk
    return _HANDLE_STREAM_CHUNK


class TelegramLiveResponsePreview(Extension):

    async def execute(self, stream_data: dict | None = None, **kwargs):
        if not self.agent:
            return
        context = self.agent.context
        if not context.data.get(CTX_TG_BOT):
            return

        await _get_handle_stream_chunk()(context, stream_data)
