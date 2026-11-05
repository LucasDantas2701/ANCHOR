"""Where a desktop install keeps the user's data: %LOCALAPPDATA%\\ANCHOR on Windows (the program's own
folder is read-only). The automations, the memory/ folder and downloads live there, and the browser
ANCHOR downloads on its first opening too."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    folder = base / "ANCHOR"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def use_data_dir(folder: Path | None = None) -> Path:
    """Works from the user's data folder, and keeps the downloaded browser there."""
    folder = folder or data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    os.chdir(folder)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(folder / "browsers"))
    return folder
