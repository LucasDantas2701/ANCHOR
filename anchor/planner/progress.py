"""
Indicador de progresso no terminal, numa única linha que se atualiza:

    carregando/aguardando o modelo... 12 s
    modelo pensando... 85 tokens, 20 s
    escrevendo o plano... 140 tokens, 27 s

Um relógio em segundo plano atualiza a linha a cada segundo, mesmo
quando nada chega do modelo (por exemplo, enquanto ele é carregado).
"""

from __future__ import annotations

import sys
import threading
import time

PHASES = {
    "waiting": "aguardando o modelo",
    "thinking": "modelo pensando",
    "writing": "escrevendo o plano",
}


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
        """Chamado a cada pedaço de resposta que chega do modelo."""
        with self._lock:
            self.phase, self.tokens = phase, tokens
        self._render()

    def _tick(self):
        while not self._stop.wait(self.interval_s):
            self._render()

    def _render(self):
        with self._lock:
            elapsed = time.perf_counter() - self._start
            text = f"{self.prefix}{PHASES.get(self.phase, self.phase)}..."
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
