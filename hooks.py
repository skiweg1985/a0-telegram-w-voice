"""Framework lifecycle hooks (install, pre-update, uninstall). See Agent Zero a0-create-plugin SKILL."""

from __future__ import annotations

from pathlib import Path


async def pre_update() -> None:
    """Stop all Telegram polling before Git replaces files (reduces duplicate getUpdates after reload)."""
    try:
        from usr.plugins.telegram_integration_voice.helpers.bot_manager import stop_all_bots

        await stop_all_bots()
    except Exception as e:
        from helpers.print_style import PrintStyle

        PrintStyle.warning(f"telegram_integration_voice pre_update: {e}")


async def uninstall() -> None:
    """Release getUpdates / webhook before the plugin directory is deleted."""
    try:
        from usr.plugins.telegram_integration_voice.helpers.bot_manager import stop_all_bots

        await stop_all_bots()
    except Exception as e:
        from helpers.print_style import PrintStyle

        PrintStyle.warning(f"telegram_integration_voice uninstall: {e}")


def install() -> int:
    """Runs after install and after git-based updates; installs Python dependencies."""
    from usr.plugins.telegram_integration_voice.execute import install_dependencies

    root = Path(__file__).resolve().parent
    return install_dependencies(root)
