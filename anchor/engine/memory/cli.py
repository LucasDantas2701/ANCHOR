"""
Reviewing the choice memory from the terminal.

    python -m anchor.engine.memory memory/demo.json list
    python -m anchor.engine.memory memory/demo.json forget 2
    python -m anchor.engine.memory memory/demo.json forget 1 3
    python -m anchor.engine.memory memory/demo.json clear

It lets the user fix what the assistant learned wrong: if a remembered
choice is not the right one, forget it, and the next run will ask again.
The Portuguese commands (listar, esquecer, limpar) are still accepted.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from anchor.engine.disambiguation.describe import kind_of
from anchor.i18n import t

from .choices import ChoiceMemory, Entry

COMMANDS = {"list": "list", "listar": "list", "forget": "forget", "esquecer": "forget",
            "clear": "clear", "limpar": "clear"}
YES = {"y", "yes", "s", "sim"}


def describe_entry(entry: Entry) -> str:
    sig = entry.signature
    kind = kind_of(sig.get("role", ""))
    name = sig.get("label") or sig.get("text") or sig.get("hint") or t("element.no_text")
    near = " ".join((sig.get("context") or "").split())
    start = near.lower().find(name.lower())
    if start >= 0:
        near = " ".join((near[:start] + near[start + len(name):]).split())
    near = t("mem.near", near=near[:50]) if near else ""
    return f'{kind} "{name[:50]}"{near}'


def list_entries(memory: ChoiceMemory, out: Callable[[str], None]) -> None:
    items = memory.ordered()
    if not items:
        out(t("mem.empty"))
        return
    out(t("mem.count", count=len(items), path=memory.path))
    for number, (_, e) in enumerate(items, 1):
        out(t("mem.step", number=number, description=e.description, action=e.action))
        out(t("mem.element", element=describe_entry(e)))
        out(t("mem.page", url=e.url))
        out(t("mem.used", uses=e.uses, last=e.last_used.replace("T", " ")))


def main(argv: list[str] | None = None, input_fn=input, out: Callable[[str], None] = print) -> int:
    ap = argparse.ArgumentParser(prog="python -m anchor.engine.memory", description=t("mem.help"))
    ap.add_argument("file", type=Path, help=t("mem.help_file"))
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("list", aliases=["listar"], help=t("mem.help_list"))
    forget = sub.add_parser("forget", aliases=["esquecer"], help=t("mem.help_forget"))
    forget.add_argument("numbers", type=int, nargs="+")
    clear = sub.add_parser("clear", aliases=["limpar"], help=t("mem.help_clear"))
    clear.add_argument("--yes", "--sim", action="store_true", help=t("mem.help_yes"))
    args = ap.parse_args([str(a) for a in argv] if argv is not None else None)
    command = COMMANDS[args.command]

    if not args.file.exists():
        out(t("mem.no_file", path=args.file))
        return 1

    memory = ChoiceMemory(args.file)

    if command == "list":
        list_entries(memory, out)
        return 0

    if command == "forget":
        items = memory.ordered()
        invalid = [n for n in args.numbers if not 1 <= n <= len(items)]
        if invalid:
            out(t("mem.invalid", numbers=", ".join(map(str, invalid))))
            return 1
        for n in sorted(set(args.numbers)):
            key, entry = items[n - 1]
            memory.forget_key(key)
            out(t("mem.forgotten", number=n, description=entry.description, element=describe_entry(entry)))
        out(t("mem.will_ask"))
        return 0

    if command == "clear":
        total = len(memory.entries)
        if not total:
            out(t("mem.empty"))
            return 0
        if not args.yes and input_fn(t("mem.confirm", total=total)).strip().lower() not in YES:
            out(t("mem.nothing_deleted"))
            return 0
        memory.clear()
        out(t("mem.cleared", total=total))
        return 0

    return 1
