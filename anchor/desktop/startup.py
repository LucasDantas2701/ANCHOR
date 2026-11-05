"""
Starting ANCHOR with Windows: a value under the user's "Run" key (HKEY_CURRENT_USER, no admin needed)
that opens ANCHOR hidden near the clock when the person logs in, so schedules run without anyone
remembering to open it. On by default (the installer's box), off in one click (Settings, the icon's
menu).
"""
from __future__ import annotations

import sys
from typing import Optional

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "ANCHOR"


class StartWithWindows:
    def __init__(self, exe: Optional[str] = None, registry=None):
        self.exe = exe or sys.executable
        self.registry = registry
        if registry is None and sys.platform == "win32":
            import winreg
            self.registry = winreg

    @property
    def available(self) -> bool:
        """Only for the installed program on Windows (not for `python -m anchor.ui`)."""
        return self.registry is not None and bool(getattr(sys, "frozen", False) or self._forced)

    _forced = False                                   # the tests turn this on

    def command(self) -> str:
        return f'"{self.exe}" --background'

    def is_on(self) -> bool:
        if self.registry is None:
            return False
        try:
            with self.registry.OpenKey(self.registry.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _ = self.registry.QueryValueEx(key, NAME)
                return bool(value)
        except OSError:
            return False

    def set(self, on: bool) -> bool:
        if self.registry is None:
            return False
        with self.registry.CreateKey(self.registry.HKEY_CURRENT_USER, RUN_KEY) as key:
            if on:
                self.registry.SetValueEx(key, NAME, 0, self.registry.REG_SZ, self.command())
            else:
                try:
                    self.registry.DeleteValue(key, NAME)
                except OSError:
                    pass
        return self.is_on()
