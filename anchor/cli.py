"""
Helpers shared by the command-line tools.

Options are in English; the old Portuguese names still work, hidden from --help,
so existing commands and scripts keep running.
"""

from __future__ import annotations

import argparse

from anchor.i18n import SUPPORTED, set_language
from anchor.planner.language import PROMPT_LANGUAGES


def option(parser: argparse.ArgumentParser, name: str, *old_names: str, **kwargs) -> None:
    """Adds --name, plus hidden aliases (the old Portuguese option names)."""
    dest = kwargs.pop("dest", name.lstrip("-").replace("-", "_"))
    parser.add_argument(name, dest=dest, **kwargs)
    hidden = {k: v for k, v in kwargs.items() if k not in ("help", "default", "required")}
    for old in old_names:
        parser.add_argument(old, dest=dest, help=argparse.SUPPRESS, default=argparse.SUPPRESS, **hidden)


def language_options(parser: argparse.ArgumentParser, prompt: bool = True) -> None:
    option(parser, "--lang", choices=SUPPORTED, help="interface language (default: ANCHOR_LANG or en)")
    if prompt:
        option(parser, "--prompt-language", choices=PROMPT_LANGUAGES,
               help="planner prompt language (default: the profile's, usually pt)")


def apply_language(args: argparse.Namespace) -> None:
    if getattr(args, "lang", None):
        set_language(args.lang)


def require(parser: argparse.ArgumentParser, args: argparse.Namespace, *names: str) -> None:
    """argparse cannot require an option that has aliases; this checks it."""
    for name in names:
        if getattr(args, name.lstrip("-").replace("-", "_"), None) in (None, ""):
            parser.error(f"the option {name} is required")
