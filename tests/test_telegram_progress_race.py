"""Regression tests for the progress-update / final-reply race.

The bug: ``schedule_telegram_progress_update`` fires background tasks that
edit the progress bubble ("🤔 Drafting reply…", tool detail lines, live
previews). ``send_telegram_reply`` finalizes by editing that same bubble into
the final answer (or deleting it / marking it done). Nothing ordered the two,
so a queued or in-flight background edit could land *after* the final one and
overwrite the delivered answer with "🤔 Drafting reply…" — or, when it ran
after ``_clear_progress_state``, re-create a fresh status bubble that nobody
ever cleans up. Telegram then shows a chat stuck on "Drafting reply…" while
the web UI shows the completed response.

The fix fences the progress pipeline with a monotonic epoch
(``CTX_TG_PROGRESS_EPOCH``): background updates capture the epoch at schedule
time and abort when it has moved on, and ``send_telegram_reply`` bumps the
epoch and awaits all in-flight update tasks (``_finalize_progress_updates``)
before its first final edit, so the final edit always lands last.
"""

import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

try:
    from tests.test_telegram_session_picker import _load_handler_module
except ModuleNotFoundError:
    from test_telegram_session_picker import _load_handler_module


class _AsyncBotCM:
    async def __aenter__(self):
        return types.SimpleNamespace(token="t")

    async def __aexit__(self, *a):
        return False


class TelegramProgressFinalReplyRaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handler = _load_handler_module()
        from usr.plugins.telegram_integration_voice.helpers import constants

        cls.constants = constants

    def _make_context(self, progress_message_id=999):
        from agent import AgentContext

        c = self.constants
        ctx = AgentContext()
        ctx.data[c.CTX_TG_BOT] = "testbot"
        ctx.data[c.CTX_TG_BOT_CFG] = {"progress": {"edit_throttle_ms": 0}}
        ctx.data[c.CTX_TG_CHAT_ID] = 12345
        # No reply actions -> final edit path stays a plain edit_text
        ctx.data[c.CTX_TG_REPLY_ACTIONS_SESSION] = "off"
        if progress_message_id:
            ctx.data[c.CTX_TG_PROGRESS_MESSAGE_ID] = progress_message_id
        return ctx

    def _patch_telegram(self, calls, slow_texts=(), edit_delay=0.0):
        """``slow_texts``: edits whose payload contains one of these substrings
        simulate a slow network call. The edit is recorded AFTER the delay —
        i.e. when the request would actually land at Telegram."""
        handler = self.handler

        async def fake_edit(bot, chat_id, message_id, text, *args, **kwargs):
            if edit_delay and any(s in text for s in slow_texts):
                await asyncio.sleep(edit_delay)
            calls.append(("edit", text))
            return True

        async def fake_send(bot, chat_id, text, *args, **kwargs):
            calls.append(("send", text))
            return 777

        async def fake_delete(bot, chat_id, message_id, *args, **kwargs):
            calls.append(("delete", message_id))
            return True

        async def fake_typing(*args, **kwargs):
            return None

        return mock.patch.multiple(
            handler.tc,
            create=True,
            edit_text=fake_edit,
            edit_text_with_keyboard=fake_edit,
            send_text=fake_send,
            send_text_with_keyboard=fake_send,
            delete_message=fake_delete,
            send_typing=fake_typing,
            MAX_MESSAGE_LENGTH=4096,
        )

    def _patch_speech(self):
        handler = self.handler
        return mock.patch.multiple(
            handler.speech,
            create=True,
            effective_voice_reply_mode=lambda bot_cfg, ctx_data: "off",
            effective_also_send_text=lambda bot_cfg, ctx_data: True,
        )

    # --- the core race: in-flight "Drafting reply…" edit vs final edit -----

    def test_final_edit_lands_after_inflight_drafting_edit(self):
        """A progress edit already on the wire must never overwrite the final
        answer: send_telegram_reply awaits it before performing its own edit,
        so the final edit is the last write to the progress message."""
        handler = self.handler
        c = self.constants
        ctx = self._make_context()
        calls = []

        async def scenario():
            # Background status update carrying the stale "Drafting reply…"
            # text — scheduled the way the stream-chunk hook does it.
            ok = handler.schedule_telegram_progress_update(
                ctx, "<b>🤔 Drafting reply…</b>", text_is_html=True
            )
            assert ok
            # Let the task start and block inside its (slow) edit call.
            await asyncio.sleep(0.01)
            await handler.send_telegram_reply(ctx, "final answer")
            # Give a leaked in-flight edit time to land AFTER the final one
            # (this is exactly what the pre-fix code allowed).
            await asyncio.sleep(0.3)

        with self._patch_telegram(calls, slow_texts=("Drafting reply",), edit_delay=0.2), \
             self._patch_speech(), \
             mock.patch.object(handler, "_temp_bot", lambda *a, **k: _AsyncBotCM()):
            asyncio.run(scenario())

        edits = [call for call in calls if call[0] == "edit"]
        self.assertTrue(edits, "expected at least the final edit")
        self.assertEqual(
            edits[-1][1],
            "final answer",
            "the final answer must be the LAST edit of the progress message — "
            "a stale 'Drafting reply…' edit landing after it is the bug.",
        )
        self.assertTrue(ctx.data.get(c.CTX_TG_FINAL_REPLY_DELIVERED))
        self.assertNotIn(c.CTX_TG_PROGRESS_MESSAGE_ID, ctx.data)

    # --- queued (not yet started) update dropped at finalization -----------

    def test_queued_progress_update_is_dropped_by_finalize(self):
        handler = self.handler
        ctx = self._make_context()
        calls = []

        async def scenario():
            handler.schedule_telegram_progress_update(
                ctx, "<b>🤔 Drafting reply…</b>", text_is_html=True
            )
            # Finalize before the task ever runs: it must be cancelled/aborted.
            await handler._finalize_progress_updates(ctx)
            await asyncio.sleep(0.01)

        with self._patch_telegram(calls), \
             mock.patch.object(handler, "_temp_bot", lambda *a, **k: _AsyncBotCM()):
            asyncio.run(scenario())

        self.assertEqual(
            calls,
            [],
            "a progress update scheduled before finalization must not reach "
            "Telegram afterwards",
        )

    # --- stale epoch never re-creates a status bubble after cleanup --------

    def test_stale_epoch_update_does_not_recreate_progress_message(self):
        """After the final reply cleared the progress state, a late update
        from the previous epoch must not send a fresh 'Drafting reply…'
        bubble (which nothing would ever edit or delete again)."""
        handler = self.handler
        c = self.constants
        ctx = self._make_context(progress_message_id=None)
        calls = []

        async def scenario():
            stale_epoch = handler._progress_epoch(ctx)
            # Final reply finished: state cleared, epoch bumped.
            handler._clear_progress_state(ctx)
            return await handler.send_telegram_progress_update(
                ctx,
                "<b>🤔 Drafting reply…</b>",
                text_is_html=True,
                epoch=stale_epoch,
            )

        with self._patch_telegram(calls), \
             mock.patch.object(handler, "_temp_bot", lambda *a, **k: _AsyncBotCM()):
            result = asyncio.run(scenario())

        self.assertIsNone(result)
        self.assertEqual(calls, [], "stale-epoch update must be a no-op")
        self.assertNotIn(c.CTX_TG_PROGRESS_MESSAGE_ID, ctx.data)

    def test_current_epoch_update_still_works(self):
        """Sanity: the fence must not break normal progress updates."""
        handler = self.handler
        c = self.constants
        ctx = self._make_context(progress_message_id=None)
        calls = []

        with self._patch_telegram(calls), \
             mock.patch.object(handler, "_temp_bot", lambda *a, **k: _AsyncBotCM()):
            result = asyncio.run(
                handler.send_telegram_progress_update(
                    ctx, "<b>🤔 Drafting reply…</b>", text_is_html=True
                )
            )

        self.assertIsNone(result)
        self.assertEqual([call[0] for call in calls], ["send"])
        self.assertEqual(ctx.data.get(c.CTX_TG_PROGRESS_MESSAGE_ID), 777)


if __name__ == "__main__":
    unittest.main()
