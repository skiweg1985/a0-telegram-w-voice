PLUGIN_NAME = "telegram_integration_voice"
DOWNLOAD_FOLDER = "usr/uploads"
STATE_FILE = "usr/plugins/telegram_integration_voice/state.json"

# Context data keys
CTX_TG_BOT = "telegram_bot"
CTX_TG_BOT_CFG = "telegram_bot_cfg"
CTX_TG_CHAT_ID = "telegram_chat_id"
CTX_TG_USER_ID = "telegram_user_id"
CTX_TG_USERNAME = "telegram_username"
CTX_TG_TYPING_STOP = "_telegram_typing_stop"
CTX_TG_REPLY_TO = "_telegram_reply_to_message_id"

# Transient
CTX_TG_ATTACHMENTS = "_telegram_response_attachments"
CTX_TG_KEYBOARD = "_telegram_response_keyboard"
CTX_TG_VOICE_REPLY_MODE = "_telegram_response_voice_mode"
CTX_TG_FORCE_VOICE_REPLY = "_telegram_response_voice_force"
CTX_TG_LAST_INPUT_WAS_VOICE = "_telegram_last_input_was_voice"

# Per-session voice behaviour: None (missing) = use plugin config;
# "off" = never send voice; "auto" / "force" = session voice_mode override.
# Key must not start with "_" so persist_chat includes it in chat.json.
CTX_TG_TTS_OVERRIDE = "telegram_tts_voice_session"

# Per-session response style for system prompt: missing = use speech.reply.optimize_output_default;
# "voice" | "text" | explicit "off" (no optimize snippet).
CTX_TG_OUTPUT_OPTIMIZE = "telegram_output_optimize_session"

# Last response tool: optional separate string for TTS only (transient, "_" prefix = not persisted).
CTX_TG_VOICE_TEXT = "_telegram_response_voice_text"

# Inline keyboard callbacks from plugin slash UI (do not use this prefix in agent response tool keyboards).
TG_UI_CALLBACK_PREFIX = "tgx|"
