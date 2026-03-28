"""Framework lifecycle hooks (install, pre-update). See Agent Zero a0-create-plugin SKILL."""

from __future__ import annotations

from pathlib import Path


def pre_update() -> None:
    """Runs immediately before new plugin code is pulled; extend for migrations if needed."""
    pass


def install() -> int:
    """Runs after install and after git-based updates; installs Python dependencies."""
    from usr.plugins.telegram_integration_voice.execute import install_dependencies

    root = Path(__file__).resolve().parent
    return install_dependencies(root)
