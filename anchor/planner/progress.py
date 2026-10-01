"""
Progress indicator in the terminal, on a single line that updates itself:

waiting for the model... 12 s
model thinking... 85 tokens, 20 s
writing the plan... 140 tokens, 27 s

A background clock updates the line every second, even when nothing
arrives from the model (for example, while it is being loaded).
"""

from __future__ import annotations

import sys
import threading
import time

from anchor.i18n import t

PHASES = {"waiting": "progress.waiting", "thinking": "progress.thinking", "writing": "progress.writing"}


class Progress:
    def __init__(self, prefix: str = "  ", stream=None, interval_s: float = 1.0):
        self.prefix = prefix
        self.stream = stream or sys.stdout
        self.interval_s = interval_s
        self.phase = "waiting"
        self.tokens = 0
        self._start = 0.0
        self._last_len = 0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None

    def __enter__(self):
        self.phase, self.tokens = "waiting", 0
        self._start = time.perf_counter()
        self._stop.clear()
        self._thread = threading.Thread(target=self._tick, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join()
        self.clear()

    def update(self, phase: str, tokens: int) -> None:
        """Called for each chunk of the answer that arrives from the model."""
        with self._lock:
            self.phase, self.tokens = phase, tokens
        self._render()

    def _tick(self):
        while not self._stop.wait(self.interval_s):
            self._render()

    def _render(self):
        with self._lock:
            elapsed = time.perf_counter() - self._start
            text = f"{self.prefix}{t(PHASES[self.phase]) if self.phase in PHASES else self.phase}..."
            text += f" {self.tokens} tokens," if self.tokens else ""
            text += f" {elapsed:.0f} s"
            pad = max(0, self._last_len - len(text))
            self.stream.write("\r" + text + " " * pad)
            self.stream.flush()
            self._last_len = len(text)

    def clear(self):
        with self._lock:
            self.stream.write("\r" + " " * self._last_len + "\r")
            self.stream.flush()
            self._last_len = 0
