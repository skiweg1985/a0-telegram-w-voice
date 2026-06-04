PLUGIN_NAME = "telegram_integration_voice"
DOWNLOAD_FOLDER = "usr/uploads"
STATE_FILE = "usr/plugins/telegram_integration_voice/state.json"
PERSISTED_CHATS_FOLDER = "usr/chats"
PERSISTED_CHAT_FILE_NAME = "chat.json"

# Context data keys
CTX_TG_BOT = "telegram_bot"
CTX_TG_BOT_CFG = "telegram_bot_cfg"
CTX_TG_CHAT_ID = "telegram_chat_id"
CTX_TG_USER_ID = "telegram_user_id"
CTX_TG_USERNAME = "telegram_username"
CTX_TG_TYPING_STOP = "_telegram_typing_stop"
CTX_TG_REPLY_TO = "_telegram_reply_to_message_id"
CTX_TG_REPLY_CONTEXT = "_telegram_reply_context"

# Transient
CTX_TG_ATTACHMENTS = "_telegram_response_attachments"
CTX_TG_KEYBOARD = "_telegram_response_keyboard"
CTX_TG_VOICE_REPLY_MODE = "_telegram_response_voice_mode"
CTX_TG_FORCE_VOICE_REPLY = "_telegram_response_voice_force"
CTX_TG_LAST_INPUT_WAS_VOICE = "_telegram_last_input_was_voice"
CTX_TG_PROGRESS_MESSAGE_ID = "_telegram_progress_message_id"
CTX_TG_PROGRESS_LAST_HASH = "_telegram_progress_last_hash"
CTX_TG_PROGRESS_LAST_TS = "_telegram_progress_last_ts"
CTX_TG_PROGRESS_LINES = "_telegram_progress_lines"
CTX_TG_PROGRESS_HEADER = "_telegram_progress_header"
CTX_TG_STREAM_PREVIEW = "_telegram_stream_preview"
CTX_TG_STREAM_ACTIVE = "_telegram_stream_active"
CTX_TG_STREAM_DRAFT_ID = "_telegram_stream_draft_id"
CTX_TG_STREAM_DRAFT_LAST_TS = "_telegram_stream_draft_last_ts"
CTX_TG_STREAM_DRAFT_ACTIVE = "_telegram_stream_draft_active"
CTX_TG_STREAM_DRAFT_USED = "_telegram_stream_draft_used"
CTX_TG_STREAM_DRAFT_DISABLED = "_telegram_stream_draft_disabled"
CTX_TG_STREAM_PENDING_FULL = "_telegram_stream_pending_full"
CTX_TG_STREAM_WORKER_TASK = "_telegram_stream_worker_task"
CTX_TG_STREAM_WORKER_EVENT = "_telegram_stream_worker_event"
CTX_TG_STREAM_WORKER_TOKEN = "_telegram_stream_worker_token"
CTX_TG_STREAM_LAST_FLUSH_RAW_LEN = "_telegram_stream_last_flush_raw_len"
CTX_TG_STREAM_LAST_FLUSH_TS = "_telegram_stream_last_flush_ts"
CTX_TG_FINAL_REPLY_SENT = "_telegram_final_reply_sent"

# Last text reply + reveal-button token for the voice_only "Text anzeigen" action.
# Persisted (no leading underscore) so the button survives bot restarts / context reloads.
CTX_TG_LAST_TEXT_RESPONSE = "telegram_last_text_response"
CTX_TG_LAST_TEXT_RESPONSE_TOKEN = "telegram_last_text_response_token"

# Per-session voice behaviour: None (missing) = use plugin config;
# "off" = never send voice; "auto" / "force" = session voice_mode override.
# Key must not start with "_" so persist_chat includes it in chat.json.
CTX_TG_TTS_OVERRIDE = "telegram_tts_voice_session"

# Per-session walkie-talkie mode: off | voice_only | voice_text | text_only.
# Persisted (no leading underscore) so Telegram sessions remember the preferred conversation mode.
CTX_TG_VOICE_CONVERSATION_MODE = "telegram_voice_conversation_session"

# Per-session response style for system prompt: missing = use speech.reply.optimize_output_default;
# "auto" | "voice" | "text" | explicit "off" (no optimize snippet).
CTX_TG_OUTPUT_OPTIMIZE = "telegram_output_optimize_session"

# Per-session also_send_text override: None = use plugin config; "on" / "off".
# Key without "_" prefix so persist_chat includes it in chat.json.
CTX_TG_ALSO_SEND_TEXT_OVERRIDE = "telegram_also_send_text_session"

# Per-session tool-status detail: missing = use bot telegram_detail_level; off | info | debug.
CTX_TG_DETAIL_LEVEL_SESSION = "telegram_detail_level_session"

# Throttle for Telegram detail status lines (transient; reset on new user message).
CTX_TG_DETAIL_LAST_SENT_TS = "_telegram_detail_last_sent_ts"

# Last response tool: optional separate string for TTS only (transient, "_" prefix = not persisted).
CTX_TG_VOICE_TEXT = "_telegram_response_voice_text"

# Inline keyboard callbacks from plugin slash UI (do not use this prefix in agent response tool keyboards).
TG_UI_CALLBACK_PREFIX = "tgx|"
