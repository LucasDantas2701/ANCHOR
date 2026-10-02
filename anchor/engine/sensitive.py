"""
Sensitive actions: the ones the user should approve before they happen.

A click is sensitive when the step's description (outside parentheses, which hold the
item's context) or the name of the element the resolver chose has a verb of one of
these categories, in Portuguese or English. Looking at the element too catches vague
steps ("click the button") on a button called "Excluir". Cancelling is sensitive only
with an object that makes it irreversible (an order, a subscription, a booking...).

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

# "Cancelar" alone usually closes a form, which is harmless; cancelling an order, a
# subscription or a booking is not. So cancelling is sensitive only with one of these
# objects, which may be in the item's context in parentheses ("Cancelar (Pedido #1024)").
CANCEL_VERBS = ["cancelar", "cancele", "cancel"]
CANCEL_OBJECTS = ["pedido", "compra", "assinatura", "reserva", "conta", "plano", "inscrição", "matrícula",
                  "contrato", "order", "purchase", "subscription", "booking", "reservation", "account",
                  "plan", "membership", "enrollment", "contract"]
# Verbs that already carry their object ("cancelar assinatura" becomes "unsubscribe").
CANCEL_WITH_OBJECT = ["unsubscribe", "descadastrar"]
_CANCEL_VERBS = set().union(*(tokenize(w) for w in CANCEL_VERBS))
_CANCEL_WITH_OBJECT = set().union(*(tokenize(w) for w in CANCEL_WITH_OBJECT))
_CANCEL_OBJECTS = set().union(*(tokenize(w) for w in CANCEL_OBJECTS))

_ORDER = ("pay", "delete", "cancel", "send", "upload", "download", "submit")   # the most serious first
SENSITIVE_ACTIONS = ("click",)


def classify(action: str, description: str, element_name: str = "") -> Optional[str]:
    """The sensitive category of an action, or None."""
    if action not in SENSITIVE_ACTIONS:
        return None
    outside = re.sub(r"\([^)]*\)", " ", description or "")
    words = tokenize(outside) | tokenize(element_name or "")
    everything = words | tokenize(description or "")
    for category in _ORDER:
        if category == "cancel":
            if (words & _CANCEL_VERBS and everything & _CANCEL_OBJECTS) or words & _CANCEL_WITH_OBJECT:
                return "cancel"
        elif words & _STEMS[category]:
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


class Decision(int):
    """
    The answer of a confirmer that also says whether it should be saved: an explicit "no"
    is saved; just pressing Enter denies only this time (the next run asks again).
    It behaves as a bool (True = allowed).
    """

    def __new__(cls, allowed: bool, save: bool = True):
        obj = super().__new__(cls, bool(allowed))
        obj.save = save
        return obj


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
            return Decision(False, save=False)
        try:
            answer = self.input_fn(t("confirm.prompt") + " ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return Decision(False, save=False)
        if answer in ("y", "yes", "s", "sim"):
            return Decision(True)
        if answer in ("n", "no", "não", "nao"):
            return Decision(False)
        return Decision(False, save=False)        # Enter (or anything else): not now, ask again next time


class AllowAll:
    """Approves every sensitive action (--allow-sensitive)."""

    def confirm(self, request: ConfirmationRequest) -> bool:
        return True
