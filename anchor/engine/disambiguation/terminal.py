"""Disambiguation through the terminal (a provisional interface, until the frontend exists)."""

from __future__ import annotations

import os
import sys
import tempfile
import webbrowser

from anchor.i18n import MESSAGES, t

from .types import ChoiceRequest, UserChoice

SKIP_KEYS = {"s", "p"}   # "skip" (English) and "pular" (Portuguese) both work


class TerminalDisambiguator:
    def __init__(self, open_screenshot: bool = True, input_fn=input, output=print):
        self.open_screenshot = open_screenshot
        self._input = input_fn
        self._print = output

    def notify(self, message: str) -> None:
        self._print(f"\n>>> {message}")

    def choose(self, request: ChoiceRequest) -> UserChoice:
        p = self._print
        verb_key = f"verb.{request.action}"
        verb = t(verb_key) if verb_key in MESSAGES else request.action
        p("")
        p("=" * 64)
        where = t("dis.where_browser") if request.can_point else t("dis.where_image")

        if request.reason == "ambiguous":
            p(t("dis.ambiguous", description=request.description))
            p("=" * 64)
            p(t("dis.numbered", where=where))
        else:
            p(t("dis.not_found", verb=verb, description=request.description))
            p("=" * 64)
            if request.can_point:
                p(t("dis.point_hint"))
            if request.candidates:
                p(t("dis.number_hint", where=where))

        for c in request.candidates:
            near = t("dis.near", near=c.near) if c.near else ""
            p(f"  [{c.number}] {c.kind} \"{c.name}\"{near}")

        if request.reason == "ambiguous" and request.can_point:
            p(t("dis.none_of_these"))

        if request.screenshot and self.open_screenshot:
            self._show(request.screenshot)

        options = []
        point = t("dis.opt_point")
        if request.can_point and request.reason == "not_found":
            options.append(point)
        if request.candidates:
            options.append(t("dis.opt_number", count=len(request.candidates)))
        if request.can_point and request.reason == "ambiguous":
            options.append(point)
        options.append(t("dis.opt_skip"))
        prompt = t("dis.prompt", options=", ".join(options))

        while True:
            answer = self._input(prompt).strip().lower()
            if answer in SKIP_KEYS:
                return UserChoice("skip")
            if answer == "c" and request.can_point:
                return UserChoice("point")
            if answer.isdigit() and 1 <= int(answer) <= len(request.candidates):
                return UserChoice("candidate", int(answer))
            p(t("dis.invalid"))

    def _show(self, png: bytes) -> None:
        fd, path = tempfile.mkstemp(suffix=".png", prefix="disambiguation_")
        with os.fdopen(fd, "wb") as f:
            f.write(png)
        self._print(t("dis.image_saved", path=path))
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(f"file://{path}")
        except Exception:
            pass
