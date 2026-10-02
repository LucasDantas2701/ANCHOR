"""
Sensitive actions: the ones the user should approve before they happen.

A click is sensitive when the step's description (outside parentheses, which hold the
item's context) or the name of the element the resolver chose has a verb of one of
these categories, in Portuguese or English. Looking at the element too catches vague
steps ("click the button") on a button called "Excluir".

The Executor asks a confirmer (see ConfirmationRequest) after finding the element and
before acting; without a confirmer, nothing is asked (evaluations, tests).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Protocol

from .element_resolver.tokenizer import tokenize

# Category → words (both languages). Stemmed with the resolver's tokenizer.
CATEGORIES: dict[str, list[str]] = {
    "delete": ["excluir", "exclua", "apagar", "apague", "remover", "remova", "deletar", "lixeira",
               "delete", "remove", "erase", "trash"],
    "submit": ["salvar", "salve", "gravar", "cadastrar", "registrar", "submeter", "confirmar", "concluir",
               "finalizar", "save", "submit", "register", "confirm", "finish"],
    "send": ["enviar", "envie", "publicar", "postar", "responder", "candidatar",
             "send", "publish", "post", "reply", "apply"],
    "pay": ["pagar", "pague", "comprar", "compre", "checkout", "pay", "buy", "purchase"],
    "download": ["baixar", "baixe", "exportar", "download", "export"],
    "upload": ["anexar", "importar", "upload", "attach", "import"],
}
_STEMS = {cat: set().union(*(tokenize(w) for w in words)) for cat, words in CATEGORIES.items()}
_ORDER = ("pay", "delete", "send", "upload", "download", "submit")   # the most serious first
SENSITIVE_ACTIONS = ("click",)


def classify(action: str, description: str, element_name: str = "") -> Optional[str]:
    """The sensitive category of an action, or None."""
    if action not in SENSITIVE_ACTIONS:
        return None
    outside = re.sub(r"\([^)]*\)", " ", description or "")
    words = tokenize(outside) | tokenize(element_name or "")
    for category in _ORDER:
        if words & _STEMS[category]:
            return category
    return None


@dataclass
class ConfirmationRequest:
    action: str
    description: str          # the step's description
    element: str              # the name of the element that would be acted on
    category: str             # delete, submit, send, pay, download, upload
    url: str = ""


class Confirmer(Protocol):
    def confirm(self, request: ConfirmationRequest) -> bool:
        """True to allow the action, False to deny it."""


class TerminalConfirmer:
    """Asks in the terminal. With no one to answer (no terminal), the answer is no."""

    def __init__(self, input_fn=input, output=print, interactive=None):
        import sys
        self.input_fn, self.output = input_fn, output
        self.interactive = sys.stdin.isatty() if interactive is None else interactive

    def confirm(self, request: ConfirmationRequest) -> bool:
        from anchor.i18n import t
        self.output("\n" + t("confirm.ask", category=t("confirm.cat_" + request.category),
                              element=request.element, description=request.description))
        if not self.interactive:
            self.output(t("confirm.no_terminal"))
            return False
        try:
            answer = self.input_fn(t("confirm.prompt") + " ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer in ("y", "yes", "s", "sim")


class AllowAll:
    """Approves every sensitive action (--allow-sensitive)."""

    def confirm(self, request: ConfirmationRequest) -> bool:
        return True
