import os
import re
from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramRetryAfter,
)
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
)

from helpers.errors import format_error
from helpers.print_style import PrintStyle

_UNSET = object()  # sentinel: "not provided" (lets Bot default apply)


def _notify_rate_limited(callback) -> None:
    """Invoke an optional rate-limit callback without letting it break the edit path."""
    if callback is None:
        return
    try:
        callback()
    except Exception as e:
        PrintStyle.warning(f"Telegram rate-limit callback failed: {format_error(e)}")


# Text messages

MAX_MESSAGE_LENGTH: int = 4096  # Telegram message length limit
RICH_MESSAGE_MAX_BYTES: int = 32768


@dataclass
class RichSendResult:
    success: bool
    message_id: int | None = None
    fallback_allowed: bool = False
    capability_error: bool = False
    error: str | None = None


async def send_text(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None,
    parse_mode: object = _UNSET,
    reply_markup=None,
) -> int | None:
    """Send text message, splitting if too long. Returns last message_id or None on error.

    parse_mode behaviour:
      - _UNSET (default): omitted from send_message → Bot's DefaultBotProperties applies.
      - None: explicitly no formatting.
      - "HTML"/"Markdown"/etc.: that specific mode.
    """
    try:
        chunks = _split_text(text, MAX_MESSAGE_LENGTH)
        last_msg_id = None
        pm_kwargs: dict = {} if parse_mode is _UNSET else {"parse_mode": parse_mode}
        for chunk in chunks:
            try:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    reply_to_message_id=reply_to_message_id,
                    reply_markup=reply_markup,
                    **pm_kwargs,
                )
                last_msg_id = msg.message_id
                reply_markup = None
            except TelegramBadRequest:
                # Retry as plain text, stripping HTML tags
                plain = re.sub(r"<[^>]+>", "", chunk)
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=plain,
                    reply_to_message_id=reply_to_message_id,
                    parse_mode=None,
                    reply_markup=reply_markup,
                )
                last_msg_id = msg.message_id
                reply_markup = None
        return last_msg_id
    except Exception as e:
        PrintStyle.error(f"Telegram send_text failed: {format_error(e)}")
        return None


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in ("true", "1", "yes", "on", "enabled"):
        return True
    if s in ("false", "0", "no", "off", "disabled", ""):
        return False
    return default


def rich_messages_settings(bot_cfg: dict | None) -> dict:
    cfg = ((bot_cfg or {}).get("rich_messages") or {})
    return {
        "enabled": _coerce_bool(cfg.get("enabled"), False),
        "drafts_enabled": _coerce_bool(cfg.get("drafts_enabled"), False),
    }


def rich_content_fits_limits(text: str) -> bool:
    return len(str(text or "").encode("utf-8")) <= RICH_MESSAGE_MAX_BYTES


def rich_message_eligible(text: str) -> bool:
    raw = str(text or "")
    if not raw.strip():
        return False
    lines = raw.splitlines()
    for idx, line in enumerate(lines[:-1]):
        if "|" in line and re.search(r"(^|\|)\s*:?-{3,}:?\s*(\||$)", lines[idx + 1]):
            return True
    patterns = [
        r"(?m)^\s*#{1,6}\s+\S",
        r"(?m)^\s*[-*+]\s+\[[ xX]\]\s+\S",
        r"(?is)<details\b|<summary\b|</details>",
        r"(?m)^\s*>\s*>\s+\S",
        r"(?s)\$\$.+?\$\$",
        r"\\\(.+?\\\)|\\\[.+?\\\]",
        r"(?m)^\[\^[^\]]+\]:",
    ]
    return any(re.search(pattern, raw) for pattern in patterns)


def supports_rich_message(bot: Bot) -> bool:
    return hasattr(bot, "send_rich_message")


def _is_rich_capability_error(exc: Exception) -> bool:
    if isinstance(exc, (AttributeError, TypeError, NotImplementedError)):
        return True
    text = str(exc).lower()
    needles = (
        "method not found",
        "unknown method",
        "unsupported method",
        "not implemented",
        "sendrichmessage",
    )
    return any(n in text for n in needles) and any(
        n in text for n in ("not found", "unknown", "unsupported", "not implemented")
    )


def _is_rich_fallback_error(exc: Exception) -> bool:
    return isinstance(exc, TelegramBadRequest) or _is_rich_capability_error(exc)


async def send_rich_text(
    bot: Bot,
    chat_id: int,
    markdown: str,
    reply_to_message_id: int | None = None,
    reply_markup=None,
) -> RichSendResult:
    """Try Telegram Bot API rich messages; caller owns legacy fallback.

    Permanent parser/capability errors are safe to fall back from. Transient
    errors are not silently legacy-sent because the rich request may have
    reached Telegram and a fallback could duplicate the final answer.
    """
    content = str(markdown or "")
    if not content.strip() or not rich_content_fits_limits(content):
        return RichSendResult(success=False, fallback_allowed=True)
    if not supports_rich_message(bot):
        return RichSendResult(
            success=False,
            fallback_allowed=True,
            capability_error=True,
            error="send_rich_message is not available on this aiogram Bot",
        )

    kwargs = {
        "chat_id": chat_id,
        "rich_message": {"markdown": content},
    }
    if reply_to_message_id is not None:
        kwargs["reply_parameters"] = {"message_id": int(reply_to_message_id)}
    if reply_markup is not None:
        kwargs["reply_markup"] = reply_markup

    try:
        msg = await bot.send_rich_message(**kwargs)
        return RichSendResult(
            success=True,
            message_id=getattr(msg, "message_id", None),
        )
    except Exception as e:
        if _is_rich_fallback_error(e):
            capability = _is_rich_capability_error(e)
            if capability:
                PrintStyle.warning(
                    f"Telegram rich messages disabled after capability error: {format_error(e)}"
                )
            else:
                PrintStyle.warning(
                    f"Telegram rich message rejected, falling back to legacy text: {format_error(e)}"
                )
            return RichSendResult(
                success=False,
                fallback_allowed=True,
                capability_error=capability,
                error=format_error(e),
            )
        PrintStyle.error(
            f"Telegram rich message transient failure, not legacy-resending: {format_error(e)}"
        )
        return RichSendResult(
            success=False,
            fallback_allowed=False,
            error=format_error(e),
        )

# Files and images / audio

async def send_file(
    bot: Bot,
    chat_id: int,
    file_path: str,
    caption: str = "",
    reply_to_message_id: int | None = None,
    reply_markup=None,
) -> int | None:
    """Send a file from local path. Returns message_id or None on error."""
    try:
        if not os.path.isfile(file_path):
            PrintStyle.error(f"Telegram: file not found: {file_path}")
            return None
        input_file = FSInputFile(file_path)
        msg = await bot.send_document(
            chat_id=chat_id,
            document=input_file,
            caption=caption[:1024] if caption else None,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
        )
        return msg.message_id
    except Exception as e:
        PrintStyle.error(f"Telegram send_file failed: {format_error(e)}")
        return None


async def send_photo(
    bot: Bot,
    chat_id: int,
    photo_path: str,
    caption: str = "",
    reply_to_message_id: int | None = None,
    reply_markup=None,
) -> int | None:
    """Send a photo from local path. Returns message_id or None on error."""
    try:
        if not os.path.isfile(photo_path):
            PrintStyle.error(f"Telegram: photo not found: {photo_path}")
            return None
        input_file = FSInputFile(photo_path)
        msg = await bot.send_photo(
            chat_id=chat_id,
            photo=input_file,
            caption=caption[:1024] if caption else None,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
        )
        return msg.message_id
    except Exception as e:
        PrintStyle.error(f"Telegram send_photo failed: {format_error(e)}")
        return None


async def send_video(
    bot: Bot,
    chat_id: int,
    video_path: str,
    caption: str = "",
    reply_to_message_id: int | None = None,
    reply_markup=None,
) -> int | None:
    """Send a video from local path. Returns message_id or None on error."""
    try:
        if not os.path.isfile(video_path):
            PrintStyle.error(f"Telegram: video not found: {video_path}")
            return None
        input_file = FSInputFile(video_path)
        msg = await bot.send_video(
            chat_id=chat_id,
            video=input_file,
            caption=caption[:1024] if caption else None,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
            supports_streaming=True,
        )
        return msg.message_id
    except Exception as e:
        PrintStyle.error(f"Telegram send_video failed: {format_error(e)}")
        return None


async def send_animation(
    bot: Bot,
    chat_id: int,
    animation_path: str,
    caption: str = "",
    reply_to_message_id: int | None = None,
    reply_markup=None,
) -> int | None:
    """Send an animation (e.g. GIF) from local path. Returns message_id or None on error."""
    try:
        if not os.path.isfile(animation_path):
            PrintStyle.error(f"Telegram: animation not found: {animation_path}")
            return None
        input_file = FSInputFile(animation_path)
        msg = await bot.send_animation(
            chat_id=chat_id,
            animation=input_file,
            caption=caption[:1024] if caption else None,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
        )
        return msg.message_id
    except Exception as e:
        PrintStyle.error(f"Telegram send_animation failed: {format_error(e)}")
        return None


async def send_video_note(
    bot: Bot,
    chat_id: int,
    video_note_path: str,
    reply_to_message_id: int | None = None,
    reply_markup=None,
) -> int | None:
    """Send a Telegram-native video note from local path."""
    try:
        if not os.path.isfile(video_note_path):
            PrintStyle.error(f"Telegram: video note not found: {video_note_path}")
            return None
        input_file = FSInputFile(video_note_path)
        msg = await bot.send_video_note(
            chat_id=chat_id,
            video_note=input_file,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
        )
        return msg.message_id
    except Exception as e:
        PrintStyle.error(f"Telegram send_video_note failed: {format_error(e)}")
        return None


async def send_voice(
    bot: Bot,
    chat_id: int,
    voice_path: str,
    caption: str = "",
    reply_to_message_id: int | None = None,
    buttons: list[list[dict]] | None = None,
    reply_markup=None,
) -> int | None:
    """Send a Telegram voice message (.ogg/opus preferred)."""
    try:
        if not os.path.isfile(voice_path):
            PrintStyle.error(f"Telegram: voice file not found: {voice_path}")
            return None
        input_file = FSInputFile(voice_path)
        if buttons:
            reply_markup = build_inline_keyboard(buttons)
        msg = await bot.send_voice(
            chat_id=chat_id,
            voice=input_file,
            caption=caption[:1024] if caption else None,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
        )
        return msg.message_id
    except Exception as e:
        PrintStyle.error(f"Telegram send_voice failed: {format_error(e)}")
        return None


# Inline keyboards

def build_inline_keyboard(
    buttons: list[list[dict]],
) -> InlineKeyboardMarkup:
    """Build inline keyboard from a list of rows.
    Each row is a list of dicts with keys: text, callback_data or url.
    """
    rows = []
    for row in buttons:
        row_buttons = []
        for btn in row:
            if "url" in btn:
                row_buttons.append(InlineKeyboardButton(
                    text=btn["text"], url=btn["url"],
                ))
            else:
                row_buttons.append(InlineKeyboardButton(
                    text=btn["text"],
                    callback_data=btn.get("callback_data", btn["text"]),
                ))
        rows.append(row_buttons)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_text_with_keyboard(
    bot: Bot,
    chat_id: int,
    text: str,
    buttons: list[list[dict]],
    reply_to_message_id: int | None = None,
    parse_mode: object = _UNSET,
) -> int | None:
    """Send text with inline keyboard buttons."""
    try:
        keyboard = build_inline_keyboard(buttons)
        pm_kwargs: dict = {} if parse_mode is _UNSET else {"parse_mode": parse_mode}
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            reply_to_message_id=reply_to_message_id,
            **pm_kwargs,
        )
        return msg.message_id
    except Exception as e:
        PrintStyle.error(f"Telegram send_text_with_keyboard failed: {format_error(e)}")
        return None


async def delete_message(bot: Bot, chat_id: int, message_id: int) -> bool:
    """Delete a bot message when Telegram allows it."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "message to delete not found" in err or "message can't be deleted" in err:
            PrintStyle.warning(f"Telegram delete_message skipped: {format_error(e)}")
            return False
        PrintStyle.error(f"Telegram delete_message failed: {format_error(e)}")
        return False
    except Exception as e:
        PrintStyle.error(f"Telegram delete_message failed: {format_error(e)}")
        return False


async def edit_text(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: object = _UNSET,
    *,
    rate_limit_is_soft_success: bool = False,
    on_rate_limited=None,
) -> bool:
    """Edit an existing bot message text. Returns True on success (or no-op), False on hard failure.

    ``rate_limit_is_soft_success`` controls how ``TelegramRetryAfter`` (flood control on
    ``editMessageText``) is reported back. The default ``False`` preserves the historical
    behaviour: the function returns ``False`` so callers that need a guaranteed delivery
    (e.g. the final reply) can fall back to ``send_message``. Set this to ``True`` for
    cosmetic in-place updates (progress bubbles, live drafts, status edits) where it is
    preferable to silently skip a rate-limited edit rather than spam the chat with a new
    ``send_message`` for every flood-controlled edit.
    """
    try:
        pm_kwargs: dict = {} if parse_mode is _UNSET else {"parse_mode": parse_mode}
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            **pm_kwargs,
        )
        return True
    except TelegramRetryAfter as e:
        if rate_limit_is_soft_success:
            PrintStyle.warning(
                f"Telegram edit_text rate-limited (retry after {getattr(e, 'retry_after', '?')}s); skipping edit."
            )
            _notify_rate_limited(on_rate_limited)
            return True
        PrintStyle.warning(
            f"Telegram edit_text rate-limited (retry after {getattr(e, 'retry_after', '?')}s)."
        )
        return False
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return True
        try:
            plain = re.sub(r"<[^>]+>", "", text)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=plain,
                parse_mode=None,
            )
            return True
        except TelegramRetryAfter as ee:
            if rate_limit_is_soft_success:
                PrintStyle.warning(
                    f"Telegram edit_text rate-limited (retry after {getattr(ee, 'retry_after', '?')}s); skipping edit."
                )
                _notify_rate_limited(on_rate_limited)
                return True
            PrintStyle.warning(
                f"Telegram edit_text rate-limited (retry after {getattr(ee, 'retry_after', '?')}s)."
            )
            return False
        except TelegramBadRequest as ee:
            if "message is not modified" in str(ee).lower():
                return True
            PrintStyle.error(f"Telegram edit_text failed: {format_error(ee)}")
            return False
        except Exception as ee:
            PrintStyle.error(f"Telegram edit_text failed: {format_error(ee)}")
            return False
    except Exception as e:
        PrintStyle.error(f"Telegram edit_text failed: {format_error(e)}")
        return False


async def edit_text_with_keyboard(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    buttons: list[list[dict]],
    parse_mode: object = _UNSET,
    *,
    rate_limit_is_soft_success: bool = False,
    on_rate_limited=None,
) -> bool:
    """Edit existing text + inline keyboard. Returns True on success (or no-op).

    See :func:`edit_text` for the meaning of ``rate_limit_is_soft_success`` and the
    flood-control rationale.
    """
    try:
        keyboard = build_inline_keyboard(buttons)
        pm_kwargs: dict = {} if parse_mode is _UNSET else {"parse_mode": parse_mode}
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
            **pm_kwargs,
        )
        return True
    except TelegramRetryAfter as e:
        if rate_limit_is_soft_success:
            PrintStyle.warning(
                f"Telegram edit_text_with_keyboard rate-limited (retry after {getattr(e, 'retry_after', '?')}s); skipping edit."
            )
            _notify_rate_limited(on_rate_limited)
            return True
        PrintStyle.warning(
            f"Telegram edit_text_with_keyboard rate-limited (retry after {getattr(e, 'retry_after', '?')}s)."
        )
        return False
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return True
        try:
            plain = re.sub(r"<[^>]+>", "", text)
            keyboard = build_inline_keyboard(buttons)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=plain,
                reply_markup=keyboard,
                parse_mode=None,
            )
            return True
        except TelegramRetryAfter as ee:
            if rate_limit_is_soft_success:
                PrintStyle.warning(
                    f"Telegram edit_text_with_keyboard rate-limited (retry after {getattr(ee, 'retry_after', '?')}s); skipping edit."
                )
                _notify_rate_limited(on_rate_limited)
                return True
            PrintStyle.warning(
                f"Telegram edit_text_with_keyboard rate-limited (retry after {getattr(ee, 'retry_after', '?')}s)."
            )
            return False
        except TelegramBadRequest as ee:
            if "message is not modified" in str(ee).lower():
                return True
            PrintStyle.error(f"Telegram edit_text_with_keyboard failed: {format_error(ee)}")
            return False
        except Exception as ee:
            PrintStyle.error(f"Telegram edit_text_with_keyboard failed: {format_error(ee)}")
            return False
    except Exception as e:
        PrintStyle.error(f"Telegram edit_text_with_keyboard failed: {format_error(e)}")
        return False


def supports_message_draft(bot: Bot) -> bool:
    return hasattr(bot, "send_message_draft")


async def send_message_draft(
    bot: Bot,
    chat_id: int,
    draft_id: int,
    text: str,
    parse_mode: object = _UNSET,
) -> bool:
    if not supports_message_draft(bot):
        return False
    try:
        pm_kwargs: dict = {} if parse_mode is _UNSET else {"parse_mode": parse_mode}
        ok = await bot.send_message_draft(
            chat_id=chat_id,
            draft_id=draft_id,
            text=text,
            **pm_kwargs,
        )
        return bool(ok)
    except TelegramBadRequest:
        try:
            plain = re.sub(r"<[^>]+>", "", text)
            ok = await bot.send_message_draft(
                chat_id=chat_id,
                draft_id=draft_id,
                text=plain,
                parse_mode=None,
            )
            return bool(ok)
        except Exception as ee:
            PrintStyle.error(f"Telegram send_message_draft failed: {format_error(ee)}")
            return False
    except Exception as e:
        PrintStyle.error(f"Telegram send_message_draft failed: {format_error(e)}")
        return False


# Chat actions

async def send_chat_action(bot: Bot, chat_id: int, action: str):
    try:
        await bot.send_chat_action(chat_id=chat_id, action=action)
    except Exception:
        pass


async def send_typing(bot: Bot, chat_id: int):
    """Send 'typing...' action to chat."""
    await send_chat_action(bot, chat_id, "typing")


async def send_record_voice(bot: Bot, chat_id: int):
    """Send 'recording voice' action to chat."""
    await send_chat_action(bot, chat_id, "record_voice")


async def send_location(
    bot: Bot,
    chat_id: int,
    latitude: float,
    longitude: float,
    reply_to_message_id: int | None = None,
    reply_markup=None,
    **kwargs,
) -> int | None:
    """Send a native Telegram location message."""
    try:
        msg = await bot.send_location(
            chat_id=chat_id,
            latitude=float(latitude),
            longitude=float(longitude),
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
            **kwargs,
        )
        return msg.message_id
    except Exception as e:
        PrintStyle.error(f"Telegram send_location failed: {format_error(e)}")
        return None


async def send_contact(
    bot: Bot,
    chat_id: int,
    phone_number: str,
    first_name: str,
    reply_to_message_id: int | None = None,
    reply_markup=None,
    **kwargs,
) -> int | None:
    """Send a native Telegram contact message."""
    try:
        msg = await bot.send_contact(
            chat_id=chat_id,
            phone_number=phone_number,
            first_name=first_name,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
            **kwargs,
        )
        return msg.message_id
    except Exception as e:
        PrintStyle.error(f"Telegram send_contact failed: {format_error(e)}")
        return None


async def send_venue(
    bot: Bot,
    chat_id: int,
    latitude: float,
    longitude: float,
    title: str,
    address: str,
    reply_to_message_id: int | None = None,
    reply_markup=None,
    **kwargs,
) -> int | None:
    """Send a native Telegram venue message."""
    try:
        msg = await bot.send_venue(
            chat_id=chat_id,
            latitude=float(latitude),
            longitude=float(longitude),
            title=title,
            address=address,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
            **kwargs,
        )
        return msg.message_id
    except Exception as e:
        PrintStyle.error(f"Telegram send_venue failed: {format_error(e)}")
        return None


async def send_media_group(
    bot: Bot,
    chat_id: int,
    items: list[dict],
    reply_to_message_id: int | None = None,
) -> list[int] | None:
    """Send a Telegram media group. Items must be photo/video/document dicts."""
    media = []
    for idx, item in enumerate(items):
        item_type = str(item.get("type") or "").strip().lower()
        path = str(item.get("path") or "").strip()
        if not path or not os.path.isfile(path):
            PrintStyle.error(f"Telegram media group item not found: {path}")
            return None
        input_file = FSInputFile(path)
        caption = str(item.get("caption") or "")
        common = {
            "media": input_file,
        }
        if idx == 0 and caption:
            common["caption"] = caption[:1024]
        if item_type == "photo":
            media.append(InputMediaPhoto(**common))
        elif item_type == "video":
            common["supports_streaming"] = True
            media.append(InputMediaVideo(**common))
        elif item_type == "document":
            media.append(InputMediaDocument(**common))
        else:
            PrintStyle.error(f"Telegram media group unsupported item type: {item_type}")
            return None

    try:
        messages = await bot.send_media_group(
            chat_id=chat_id,
            media=media,
            reply_to_message_id=reply_to_message_id,
        )
        return [msg.message_id for msg in messages]
    except Exception as e:
        PrintStyle.error(f"Telegram send_media_group failed: {format_error(e)}")
        return None

# File download

async def download_file(
    bot: Bot,
    file_id: str,
    destination: str,
) -> str | None:
    """Download a file by file_id to destination path. Returns path or None on error."""
    try:
        file = await bot.get_file(file_id)
        if not file.file_path:
            return None
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        await bot.download_file(file.file_path, destination)
        return destination
    except Exception as e:
        PrintStyle.error(f"Telegram download failed: {format_error(e)}")
        return None

# Helpers

def _split_text(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split at newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1 or split_at < max_len // 2:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
_ANIMATION_EXTENSIONS = {".gif"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}


def is_image_file(path: str) -> bool:
    _, ext = os.path.splitext(path.lower())
    return ext in _IMAGE_EXTENSIONS


def is_animation_file(path: str) -> bool:
    _, ext = os.path.splitext(path.lower())
    return ext in _ANIMATION_EXTENSIONS


def is_video_file(path: str) -> bool:
    _, ext = os.path.splitext(path.lower())
    return ext in _VIDEO_EXTENSIONS


def md_to_telegram_html(text: str) -> str:
    """Convert Markdown to Telegram-compatible HTML."""
    stash: list[str] = []

    def _put(html: str) -> str:
        stash.append(html)
        return f"\x00B{len(stash) - 1}\x00"

    def _esc(t: str) -> str:
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Stash code blocks & inline code
    def _code_block(m):
        lang, body = m.group(1), m.group(2).rstrip("\n")
        if lang:
            return _put(f'<pre><code class="language-{lang}">{_esc(body)}</code></pre>')
        return _put(f"<pre>{_esc(body)}</pre>")

    text = re.sub(r"(?:```|~~~)(\w*)\n?(.*?)(?:```|~~~)", _code_block, text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", lambda m: _put(f"<code>{_esc(m.group(1))}</code>"), text)

    # Strip unsupported syntax
    text = _strip_tables(text)
    text = re.sub(r"^[ \t]*[-*_=]{3,}[ \t]*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"[\1](\2)", text)

    # Stash links
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: _put(
            f'<a href="{m.group(2).replace("&", "&amp;").replace(chr(34), "&quot;")}">{_esc(m.group(1))}</a>'
        ),
        text,
    )

    # Escape HTML & apply inline formatting
    text = _esc(text)
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\w)\*([^*]+?)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # Block-level formatting
    text = _convert_blockquotes(text)
    text = _convert_lists(text)

    # Restore stash
    for i, block in enumerate(stash):
        text = text.replace(f"\x00B{i}\x00", block)
    return text



_TABLE_RE = re.compile(r"^\|(.+)\|$")
_TABLE_SEP = re.compile(r"^[\s|:-]+$")


def _strip_tables(text: str) -> str:
    """Strip Markdown table pipe syntax, keeping cell content as plain text."""
    out: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if _TABLE_SEP.match(stripped):
            continue
        m = _TABLE_RE.match(stripped)
        if m:
            out.append("  ".join(c.strip() for c in m.group(1).split("|")))
        else:
            out.append(line)
    return "\n".join(out)


_LIST_RE = re.compile(r"^( *)([-*+]|\d+\.)\s+(.*)$")
_BULLETS = ("\u2022", "\u25e6", "\u25aa")


def _convert_lists(text: str) -> str:
    """Convert Markdown list markers to Unicode bullets."""
    out: list[str] = []
    for line in text.split("\n"):
        m = _LIST_RE.match(line)
        if m:
            depth = len(m.group(1)) // 2
            marker, content = m.group(2), m.group(3)
            px = "  " * depth
            if marker.rstrip(".").isdigit():
                out.append(f"{px}{marker} {content}")
            else:
                out.append(f"{px}{_BULLETS[min(depth, len(_BULLETS) - 1)]} {content}")
        else:
            out.append(line)
    return "\n".join(out)


def _convert_blockquotes(text: str) -> str:
    """Convert Markdown blockquotes to Telegram <blockquote> tags."""
    out: list[str] = []
    buf: list[str] = []

    def _flush():
        if buf:
            out.append("<blockquote>" + "\n".join(buf) + "</blockquote>")
            buf.clear()

    for line in text.split("\n"):
        m = re.match(r"^&gt;\s?(.*)", line)
        if m:
            buf.append(m.group(1))
        else:
            _flush()
            out.append(line)
    _flush()
    return "\n".join(out)
