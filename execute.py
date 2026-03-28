"""User-triggered install of plugin dependencies (see Agent Zero a0-create-plugin SKILL)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    req = root / "requirements.txt"
    if not req.is_file():
        print("ERROR: requirements.txt not found next to execute.py")
        return 1

    uv = shutil.which("uv")
    if uv:
        cmd = [
            uv,
            "pip",
            "install",
            "--python",
            sys.executable,
            "-r",
            str(req),
        ]
        print("Installing with uv into the Agent Zero Python environment...")
    else:
        cmd = [sys.executable, "-m", "pip", "install", "-r", str(req)]
        print("Installing with pip into the Agent Zero Python environment...")

    result = subprocess.run(cmd, cwd=str(root), text=True)
    if result.returncode != 0:
        print("ERROR: Dependency installation failed")
        return result.returncode

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
