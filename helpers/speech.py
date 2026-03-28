from __future__ import annotations

import base64
import json
import mimetypes
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib import request, error

from helpers.print_style import PrintStyle


def _resolve_secret(value: str | None) -> str:
    if not value:
        return ""
    value = str(value).strip()
    if value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    if value.startswith("os.environ/"):
        return os.getenv(value.split("/", 1)[1], "")
    return value


def _speech_cfg(bot_cfg: dict, section: str) -> dict:
    speech = bot_cfg.get("speech") or {}
    return speech.get(section) or {}


def stt_enabled(bot_cfg: dict) -> bool:
    cfg = _speech_cfg(bot_cfg, "stt")
    return bool(cfg.get("enabled", False))


def tts_enabled(bot_cfg: dict) -> bool:
    cfg = _speech_cfg(bot_cfg, "tts")
    return bool(cfg.get("enabled", False))


def voice_reply_settings(bot_cfg: dict) -> dict:
    reply = (bot_cfg.get("speech") or {}).get("reply") or {}
    return {
        "voice_mode": str(reply.get("voice_mode", "off")).lower(),  # off|auto|force
        "also_send_text": bool(reply.get("also_send_text", True)),
        "max_chars": int(reply.get("max_chars", 700) or 700),
    }


def transcribe_audio_file(bot_cfg: dict, audio_path: str) -> dict:
    cfg = _speech_cfg(bot_cfg, "stt")
    provider = str(cfg.get("provider", "openai_compatible")).lower()

    if provider == "local_whisper":
        return _stt_local_whisper(cfg, audio_path)
    if provider == "openai_compatible":
        return _stt_openai_compatible(cfg, audio_path)
    if provider == "elevenlabs":
        return _stt_elevenlabs(cfg, audio_path)
    if provider == "custom_http":
        return _stt_custom_http(cfg, audio_path)

    raise RuntimeError(f"Unsupported STT provider: {provider}")


def synthesize_to_voice_file(bot_cfg: dict, text: str) -> tuple[str, dict]:
    cfg = _speech_cfg(bot_cfg, "tts")
    provider = str(cfg.get("provider", "openai_compatible")).lower()

    if provider == "openai_compatible":
        audio, mime_hint = _tts_openai_compatible(cfg, text)
    elif provider == "elevenlabs":
        audio, mime_hint = _tts_elevenlabs(cfg, text)
    elif provider == "custom_http":
        audio, mime_hint = _tts_custom_http(cfg, text)
    elif provider == "kokoro_local":
        audio, mime_hint = _tts_kokoro_local(text)
    else:
        raise RuntimeError(f"Unsupported TTS provider: {provider}")

    return _convert_to_telegram_voice(audio, mime_hint)


# ---------- STT providers ----------

def _stt_local_whisper(cfg: dict, audio_path: str) -> dict:
    from helpers import whisper

    model = cfg.get("model") or cfg.get("model_name") or "base"
    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")
    result = _run_async_sync(whisper.transcribe(model, audio_b64))
    text = (result or {}).get("text", "")
    return {"text": text, "raw": result or {}}


def _stt_openai_compatible(cfg: dict, audio_path: str) -> dict:
    base_url = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    endpoint = cfg.get("endpoint") or f"{base_url}/audio/transcriptions"
    api_key = _resolve_secret(cfg.get("api_key"))
    model = cfg.get("model") or "whisper-1"
    language = cfg.get("language") or ""
    timeout_sec = int(cfg.get("timeout_sec", 60) or 60)

    fields = {"model": str(model)}
    if language:
        fields["language"] = str(language)
    body, content_type = _multipart_form_data(
        fields=fields,
        file_field="file",
        file_path=audio_path,
    )

    req = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
        },
    )
    data = _http_json(req, timeout_sec)
    text = data.get("text") or ""
    if not text and isinstance(data.get("choices"), list):
        text = data["choices"][0].get("text", "")
    return {"text": text, "raw": data}


def _stt_elevenlabs(cfg: dict, audio_path: str) -> dict:
    base_url = (cfg.get("base_url") or "https://api.elevenlabs.io/v1").rstrip("/")
    endpoint = cfg.get("endpoint") or f"{base_url}/speech-to-text"
    api_key = _resolve_secret(cfg.get("api_key"))
    model = cfg.get("model") or cfg.get("model_id") or "scribe_v1"
    language = cfg.get("language") or ""
    timeout_sec = int(cfg.get("timeout_sec", 60) or 60)

    fields = {"model_id": str(model)}
    if language:
        fields["language_code"] = str(language)
    body, content_type = _multipart_form_data(
        fields=fields,
        file_field="file",
        file_path=audio_path,
    )
    req = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            **({"xi-api-key": api_key} if api_key else {}),
        },
    )
    data = _http_json(req, timeout_sec)
    text = data.get("text") or ""
    return {"text": text, "raw": data}


def _stt_custom_http(cfg: dict, audio_path: str) -> dict:
    endpoint = cfg.get("endpoint")
    if not endpoint:
        raise RuntimeError("custom_http STT requires speech.stt.endpoint")

    api_key = _resolve_secret(cfg.get("api_key"))
    model = cfg.get("model") or ""
    language = cfg.get("language") or ""
    timeout_sec = int(cfg.get("timeout_sec", 60) or 60)

    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "audio_base64": audio_b64,
        "filename": os.path.basename(audio_path),
        "model": model,
        "language": language,
    }
    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
        },
    )
    data = _http_json(req, timeout_sec)
    return {"text": data.get("text", ""), "raw": data}


# ---------- TTS providers ----------

def _tts_openai_compatible(cfg: dict, text: str) -> tuple[bytes, str]:
    base_url = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    endpoint = cfg.get("endpoint") or f"{base_url}/audio/speech"
    api_key = _resolve_secret(cfg.get("api_key"))
    model = cfg.get("model") or "gpt-4o-mini-tts"
    voice = cfg.get("voice") or "alloy"
    response_format = cfg.get("format") or "opus"
    timeout_sec = int(cfg.get("timeout_sec", 60) or 60)

    payload = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": response_format,
    }
    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "audio/*",
            **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
        },
    )
    audio, content_type = _http_bytes(req, timeout_sec)
    return audio, content_type or _content_type_for_format(response_format)


def _tts_elevenlabs(cfg: dict, text: str) -> tuple[bytes, str]:
    base_url = (cfg.get("base_url") or "https://api.elevenlabs.io/v1").rstrip("/")
    voice_id = cfg.get("voice") or cfg.get("voice_id") or ""
    if not voice_id:
        raise RuntimeError("elevenlabs TTS requires speech.tts.voice or speech.tts.voice_id")

    endpoint = cfg.get("endpoint") or f"{base_url}/text-to-speech/{voice_id}"
    api_key = _resolve_secret(cfg.get("api_key"))
    model_id = cfg.get("model") or cfg.get("model_id") or "eleven_multilingual_v2"
    output_format = cfg.get("format") or "mp3_44100_128"
    timeout_sec = int(cfg.get("timeout_sec", 60) or 60)

    payload = {
        "text": text,
        "model_id": model_id,
    }
    if output_format:
        payload["output_format"] = output_format

    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "audio/*",
            **({"xi-api-key": api_key} if api_key else {}),
        },
    )
    audio, content_type = _http_bytes(req, timeout_sec)
    return audio, content_type or "audio/mpeg"


def _tts_custom_http(cfg: dict, text: str) -> tuple[bytes, str]:
    endpoint = cfg.get("endpoint")
    if not endpoint:
        raise RuntimeError("custom_http TTS requires speech.tts.endpoint")

    api_key = _resolve_secret(cfg.get("api_key"))
    timeout_sec = int(cfg.get("timeout_sec", 60) or 60)
    payload = {
        "text": text,
        "model": cfg.get("model"),
        "voice": cfg.get("voice"),
        "format": cfg.get("format"),
    }

    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
        },
    )

    audio, content_type = _http_bytes(req, timeout_sec)
    if content_type.startswith("application/json"):
        data = json.loads(audio.decode("utf-8", "replace"))
        audio_b64 = data.get("audio_base64") or ""
        if not audio_b64:
            raise RuntimeError("custom_http TTS JSON response missing audio_base64")
        return base64.b64decode(audio_b64), data.get("mime_type") or "audio/mpeg"

    return audio, content_type or "audio/mpeg"


def _tts_kokoro_local(text: str) -> tuple[bytes, str]:
    from helpers import kokoro_tts

    audio_b64 = _run_async_sync(kokoro_tts.synthesize_sentences([text]))
    return base64.b64decode(audio_b64), "audio/wav"


# ---------- Conversion / HTTP helpers ----------

def _convert_to_telegram_voice(audio_bytes: bytes, mime_hint: str) -> tuple[str, dict]:
    tmp_dir = Path(tempfile.gettempdir()) / "a0_telegram_voice"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    ext = _ext_from_mime(mime_hint)
    input_path = tmp_dir / f"tts_{uuid.uuid4().hex}{ext}"
    output_path = tmp_dir / f"tts_{uuid.uuid4().hex}.ogg"

    input_path.write_bytes(audio_bytes)

    # Already OGG? keep as-is.
    if ext == ".ogg":
        return str(input_path), {"mime_type": mime_hint or "audio/ogg", "converted": False}

    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        PrintStyle.warning("Telegram Voice: ffmpeg not found, trying raw audio as voice file")
        return str(input_path), {"mime_type": mime_hint or "application/octet-stream", "converted": False}

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-c:a",
        "libopus",
        "-b:a",
        "48k",
        str(output_path),
    ]

    run = subprocess.run(cmd, capture_output=True, text=True)
    if run.returncode != 0:
        PrintStyle.error(f"Telegram Voice ffmpeg conversion failed: {run.stderr[-400:]}")
        return str(input_path), {"mime_type": mime_hint or "application/octet-stream", "converted": False}

    try:
        input_path.unlink(missing_ok=True)
    except Exception:
        pass

    return str(output_path), {"mime_type": "audio/ogg", "converted": True}


def _find_ffmpeg() -> str | None:
    for candidate in ("ffmpeg", "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if shutil_which(candidate):
            return candidate
    return None


def shutil_which(cmd: str) -> str | None:
    from shutil import which

    return which(cmd)


def _http_json(req: request.Request, timeout_sec: int) -> dict:
    raw, _ = _http_bytes(req, timeout_sec)
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception as e:
        raise RuntimeError(f"Invalid JSON response: {e}") from e


def _http_bytes(req: request.Request, timeout_sec: int) -> tuple[bytes, str]:
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            content_type = resp.headers.get("Content-Type", "")
            return resp.read(), content_type
    except error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:800]}") from e


def _multipart_form_data(fields: dict[str, str], file_field: str, file_path: str) -> tuple[bytes, str]:
    boundary = f"----A0Boundary{uuid.uuid4().hex}"
    lines: list[bytes] = []

    for key, value in fields.items():
        lines.extend([
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="{key}"'.encode(),
            b"",
            str(value).encode("utf-8"),
        ])

    file_name = os.path.basename(file_path)
    mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    with open(file_path, "rb") as f:
        file_data = f.read()

    lines.extend([
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"'.encode(),
        f"Content-Type: {mime_type}".encode(),
        b"",
        file_data,
    ])
    lines.append(f"--{boundary}--".encode())
    lines.append(b"")

    body = b"\r\n".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def _ext_from_mime(mime_type: str) -> str:
    mime_type = (mime_type or "").lower()
    if "ogg" in mime_type:
        return ".ogg"
    if "wav" in mime_type:
        return ".wav"
    if "mpeg" in mime_type or "mp3" in mime_type:
        return ".mp3"
    if "mp4" in mime_type or "aac" in mime_type:
        return ".m4a"
    return ".bin"


def _content_type_for_format(fmt: str) -> str:
    fmt = str(fmt or "").lower()
    return {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "opus": "audio/ogg",
        "ogg": "audio/ogg",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "pcm": "audio/wav",
    }.get(fmt, "application/octet-stream")


def _run_async_sync(coro):
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # execute in a dedicated loop to avoid nested-loop runtime errors
        import threading

        result_box: dict[str, Any] = {}
        err_box: dict[str, Exception] = {}

        def _runner():
            try:
                result_box["value"] = asyncio.run(coro)
            except Exception as e:  # pragma: no cover
                err_box["error"] = e

        th = threading.Thread(target=_runner, daemon=True)
        th.start()
        th.join()
        if "error" in err_box:
            raise err_box["error"]
        return result_box.get("value")

    return asyncio.run(coro)
