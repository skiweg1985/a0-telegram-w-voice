"""Targeted regression tests for the Telegram live-progress flood-control fix.

The original bug: when ``editMessageText`` was rate-limited by Telegram
(``TelegramRetryAfter``), :func:`helpers.telegram_client.edit_text` returned
``False``. That signalled the caller (``send_telegram_progress_update`` in
``helpers/handler.py``) to fall back to a fresh ``send_message`` call. Because
the new message id was then stored as the progress-message id, *every*
subsequent stream chunk or tool-status update repeated the same pattern,
spamming the chat with new bubbles whenever the per-chat edit limit was hit.

The fix introduces an opt-in ``rate_limit_is_soft_success`` parameter to the
edit helpers. Progress / live-draft / detail-status callers opt in so that a
rate-limited edit is silently skipped (no new send_message). The default
remains ``False`` so the final-reply path can still fall back to
``send_message`` when its in-place edit is rate-limited - the final answer
must never be lost.
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = REPO_ROOT / "helpers" / "telegram_client.py"


def _install_stub_helpers():
    aiogram = types.ModuleType("aiogram")
    aiogram.Bot = object
    sys.modules["aiogram"] = aiogram

    aiogram_exceptions = types.ModuleType("aiogram.exceptions")

    class TelegramBadRequest(Exception):
        def __init__(self, method=None, message=""):
            super().__init__(message)
            self.method = method

    class TelegramRetryAfter(Exception):
        def __init__(self, method=None, message="", retry_after=0):
            super().__init__(message)
            self.method = method
            self.retry_after = retry_after

    aiogram_exceptions.TelegramBadRequest = TelegramBadRequest
    aiogram_exceptions.TelegramRetryAfter = TelegramRetryAfter
    sys.modules["aiogram.exceptions"] = aiogram_exceptions

    aiogram_types = types.ModuleType("aiogram.types")

    class _DummyInline:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    aiogram_types.FSInputFile = _DummyInline
    aiogram_types.InlineKeyboardButton = _DummyInline
    aiogram_types.InlineKeyboardMarkup = _DummyInline
    sys.modules["aiogram.types"] = aiogram_types

    helpers = sys.modules.get("helpers")
    if helpers is None:
        helpers = types.ModuleType("helpers")
        helpers.__path__ = []
        sys.modules["helpers"] = helpers

    errors = types.ModuleType("helpers.errors")
    errors.format_error = lambda e: str(e)
    sys.modules["helpers.errors"] = errors

    print_style = types.ModuleType("helpers.print_style")

    class _PrintStyle:
        warnings: list[str] = []
        errors: list[str] = []

        @classmethod
        def warning(cls, msg, *a, **k):
            cls.warnings.append(str(msg))

        @classmethod
        def error(cls, msg, *a, **k):
            cls.errors.append(str(msg))

        @classmethod
        def info(cls, msg, *a, **k):
            pass

        @classmethod
        def reset(cls):
            cls.warnings = []
            cls.errors = []

    print_style.PrintStyle = _PrintStyle
    sys.modules["helpers.print_style"] = print_style
    return _PrintStyle


def _load_client():
    _install_stub_helpers()
    spec = importlib.util.spec_from_file_location(
        "telegram_client_under_test", CLIENT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeBot:
    """Minimal Bot stand-in. Each call appends to ``calls`` and returns / raises
    according to ``responses`` (FIFO). A response may be a callable producing a
    value or an Exception instance to raise."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def edit_message_text(self, **kwargs):
        self.calls.append({"method": "edit_message_text", **kwargs})
        if not self.responses:
            return types.SimpleNamespace(message_id=1)
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        if callable(resp):
            return resp()
        return resp


def _make_retry_after(seconds: int = 5):
    from aiogram.exceptions import TelegramRetryAfter

    return TelegramRetryAfter(
        method=types.SimpleNamespace(__class__=type("M", (), {"__name__": "editMessageText"})),
        message="Too Many Requests: retry after %d" % seconds,
        retry_after=seconds,
    )


def _make_bad_request(text: str):
    from aiogram.exceptions import TelegramBadRequest

    return TelegramBadRequest(
        method=types.SimpleNamespace(__class__=type("M", (), {"__name__": "editMessageText"})),
        message=text,
    )


class EditTextFloodControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = _load_client()
        cls.print_style = sys.modules["helpers.print_style"].PrintStyle

    def setUp(self):
        self.print_style.reset()

    # --- edit_text: soft-success mode (progress updates) -----------------

    def test_edit_text_soft_mode_returns_true_on_retry_after(self):
        bot = _FakeBot([_make_retry_after(7)])
        ok = asyncio.run(
            self.client.edit_text(bot, 1, 2, "hi", rate_limit_is_soft_success=True)
        )
        self.assertTrue(
            ok,
            "Progress updates must NOT fall back to send_message on flood "
            "control - that is the exact spam path the fix eliminates.",
        )
        self.assertEqual(len(bot.calls), 1, "should not retry on retry-after")
        self.assertTrue(any("rate-limited" in w for w in self.print_style.warnings))

    def test_edit_text_soft_mode_handles_retry_after_in_plaintext_retry(self):
        # Primary call hits a generic BadRequest -> code strips HTML and retries.
        # The retry hits flood control; soft-success mode must still report True.
        bot = _FakeBot([
            _make_bad_request("Bad Request: can't parse entities"),
            _make_retry_after(3),
        ])
        ok = asyncio.run(
            self.client.edit_text(
                bot, 1, 2, "<b>hi</b>", rate_limit_is_soft_success=True
            )
        )
        self.assertTrue(ok)
        self.assertEqual(len(bot.calls), 2)

    # --- edit_text: default (hard-fail) mode (final reply) ---------------

    def test_edit_text_default_mode_returns_false_on_retry_after(self):
        # The default mode is used by the final-reply edit path. There, the
        # caller MUST be told the edit failed so it can fall back to send_text
        # and actually deliver the user-visible answer.
        bot = _FakeBot([_make_retry_after(4)])
        ok = asyncio.run(self.client.edit_text(bot, 1, 2, "final answer"))
        self.assertFalse(
            ok,
            "Default mode must surface flood control so the final-reply path "
            "can fall back to send_message and deliver the answer.",
        )

    # --- edit_text: invariants preserved ---------------------------------

    def test_edit_text_not_modified_returns_true(self):
        bot = _FakeBot([_make_bad_request("Bad Request: message is not modified")])
        ok = asyncio.run(self.client.edit_text(bot, 1, 2, "hi"))
        self.assertTrue(ok)
        self.assertEqual(len(bot.calls), 1)

    def test_edit_text_hard_failure_returns_false(self):
        # Generic exception (e.g. network) -> False so the caller can fall back.
        bot = _FakeBot([RuntimeError("boom")])
        ok = asyncio.run(
            self.client.edit_text(bot, 1, 2, "hi", rate_limit_is_soft_success=True)
        )
        self.assertFalse(ok, "Network/IO errors are NOT covered by soft mode.")

    def test_edit_text_message_deleted_returns_false_even_in_soft_mode(self):
        # The 'message to edit not found' case is permanent: the caller should
        # be told so it can recreate the progress message. Soft mode covers
        # rate-limit only, never message-deleted.
        bot = _FakeBot([
            _make_bad_request("Bad Request: message to edit not found"),
            _make_bad_request("Bad Request: message to edit not found"),
        ])
        ok = asyncio.run(
            self.client.edit_text(bot, 1, 2, "hi", rate_limit_is_soft_success=True)
        )
        self.assertFalse(ok)

    # --- edit_text_with_keyboard ------------------------------------------

    def test_edit_text_with_keyboard_soft_mode_on_retry_after(self):
        bot = _FakeBot([_make_retry_after(11)])
        ok = asyncio.run(
            self.client.edit_text_with_keyboard(
                bot, 1, 2, "hi",
                [[{"text": "A", "callback_data": "a"}]],
                rate_limit_is_soft_success=True,
            )
        )
        self.assertTrue(ok)
        self.assertEqual(len(bot.calls), 1)

    def test_edit_text_with_keyboard_default_mode_on_retry_after(self):
        bot = _FakeBot([_make_retry_after(11)])
        ok = asyncio.run(
            self.client.edit_text_with_keyboard(
                bot, 1, 2, "hi", [[{"text": "A", "callback_data": "a"}]]
            )
        )
        self.assertFalse(
            ok,
            "Default mode for keyboarded edits must also surface flood control "
            "so the caller can decide whether to fall back.",
        )

    def test_edit_text_with_keyboard_soft_mode_plaintext_retry_path(self):
        bot = _FakeBot([
            _make_bad_request("Bad Request: can't parse entities"),
            _make_retry_after(2),
        ])
        ok = asyncio.run(
            self.client.edit_text_with_keyboard(
                bot, 1, 2, "<b>x</b>",
                [[{"text": "A", "callback_data": "a"}]],
                rate_limit_is_soft_success=True,
            )
        )
        self.assertTrue(ok)
        self.assertEqual(len(bot.calls), 2)


class ProgressUpdateNoSpamTests(unittest.TestCase):
    """End-to-end-ish check that send_telegram_progress_update does NOT call
    send_message when its edit is rate-limited."""

    @classmethod
    def setUpClass(cls):
        # Re-use the session-picker stub harness to load handler.py.
        try:
            from tests.test_telegram_session_picker import _load_handler_module
        except ModuleNotFoundError:
            from test_telegram_session_picker import _load_handler_module
        cls.handler = _load_handler_module()

    def _make_context(self, with_progress_id=True):
        from agent import AgentContext
        from usr.plugins.telegram_integration_voice.helpers.constants import (
            CTX_TG_BOT,
            CTX_TG_BOT_CFG,
            CTX_TG_CHAT_ID,
            CTX_TG_PROGRESS_MESSAGE_ID,
        )

        ctx = AgentContext()
        ctx.data[CTX_TG_BOT] = "testbot"
        ctx.data[CTX_TG_BOT_CFG] = {"progress": {"edit_throttle_ms": 0}}
        ctx.data[CTX_TG_CHAT_ID] = 12345
        if with_progress_id:
            ctx.data[CTX_TG_PROGRESS_MESSAGE_ID] = 999
        return ctx

    def test_progress_update_skips_send_on_rate_limited_edit(self):
        """The flood-control regression: a rate-limited edit must NOT degrade
        into a fresh send_message call."""
        handler = self.handler
        from unittest import mock

        ctx = self._make_context(with_progress_id=True)

        edit_calls = []
        send_calls = []

        async def fake_edit(*args, **kwargs):
            edit_calls.append((args, kwargs))
            # Simulate the fixed edit helper: rate-limited + soft mode -> True
            return bool(kwargs.get("rate_limit_is_soft_success"))

        async def fake_send(*args, **kwargs):
            send_calls.append((args, kwargs))
            return 12346

        class _AsyncBotCM:
            async def __aenter__(self):
                return types.SimpleNamespace(token="t")

            async def __aexit__(self, *a):
                return False

        with mock.patch.object(handler.tc, "edit_text", side_effect=fake_edit, create=True), \
             mock.patch.object(handler.tc, "edit_text_with_keyboard", side_effect=fake_edit, create=True), \
             mock.patch.object(handler.tc, "send_text", side_effect=fake_send, create=True), \
             mock.patch.object(handler.tc, "send_text_with_keyboard", side_effect=fake_send, create=True), \
             mock.patch.object(handler.tc, "MAX_MESSAGE_LENGTH", 4096, create=True), \
             mock.patch.object(handler, "_temp_bot", lambda *a, **k: _AsyncBotCM()):
            result = asyncio.run(
                handler.send_telegram_progress_update(ctx, "status text", text_is_html=True)
            )

        self.assertIsNone(result, "no error should be returned on soft-success edit")
        self.assertEqual(len(edit_calls), 1, "exactly one edit attempt")
        self.assertEqual(
            len(send_calls),
            0,
            "send_text MUST NOT be called when the edit was only rate-limited "
            "(this is the flood-control bug).",
        )

    def test_progress_update_falls_back_to_send_on_hard_edit_failure(self):
        """When the edit fails for a real reason (e.g. message deleted), the
        progress update should still recover by sending a fresh message."""
        handler = self.handler
        from unittest import mock

        ctx = self._make_context(with_progress_id=True)

        edit_calls = []
        send_calls = []

        async def fake_edit(*args, **kwargs):
            edit_calls.append((args, kwargs))
            return False  # hard failure (e.g. message deleted)

        async def fake_send(*args, **kwargs):
            send_calls.append((args, kwargs))
            return 12346

        class _AsyncBotCM:
            async def __aenter__(self):
                return types.SimpleNamespace(token="t")

            async def __aexit__(self, *a):
                return False

        with mock.patch.object(handler.tc, "edit_text", side_effect=fake_edit, create=True), \
             mock.patch.object(handler.tc, "edit_text_with_keyboard", side_effect=fake_edit, create=True), \
             mock.patch.object(handler.tc, "send_text", side_effect=fake_send, create=True), \
             mock.patch.object(handler.tc, "send_text_with_keyboard", side_effect=fake_send, create=True), \
             mock.patch.object(handler.tc, "MAX_MESSAGE_LENGTH", 4096, create=True), \
             mock.patch.object(handler, "_temp_bot", lambda *a, **k: _AsyncBotCM()):
            result = asyncio.run(
                handler.send_telegram_progress_update(ctx, "status text", text_is_html=True)
            )

        self.assertIsNone(result)
        self.assertEqual(len(edit_calls), 1)
        self.assertEqual(
            len(send_calls),
            1,
            "On a real edit failure the progress helper should still send a "
            "replacement message - we are only suppressing rate-limit spam.",
        )


if __name__ == "__main__":
    unittest.main()
