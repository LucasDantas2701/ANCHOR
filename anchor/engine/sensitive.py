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
    # Acting on the person's account on a social site: what others see as theirs.
    "account": ["conectar", "conecte", "curtir", "curta", "reagir", "comentar", "comente", "compartilhar",
                "compartilhe", "republicar", "repostar", "inscrever", "inscreva", "convidar", "convide",
                "connect", "like", "react", "comment", "share", "repost", "subscribe", "invite"],
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

_ORDER = ("pay", "delete", "cancel", "send", "account", "upload", "download", "submit")   # the most serious first

# "Seguir" is also "go on" in Portuguese ("Seguir", "Seguir para o pagamento"): it follows someone
# only with an object that is not "para"/"to" ("Seguir JAINE DA COSTA NERI", "Follow Ollama").
_FOLLOW = re.compile(r"\b(seguir|siga|follow)\s+(?!para\b|to\b|em\s+frente\b|adiante\b|next\b)[^\s()]", re.IGNORECASE)
_FOLLOW_ASKED = set().union(*(tokenize(w) for w in ("seguir", "siga", "follow")))
SENSITIVE_ACTIONS = ("click", "download", "upload")


def classify(action: str, description: str, element_name: str = "") -> Optional[str]:
    """The sensitive category of an action, or None."""
    if action not in SENSITIVE_ACTIONS:
        return None
    if action == "download":
        return "download"                 # whatever the button says, it saves a file
    if action == "upload":
        return "upload"                   # whatever the field says, it sends a file
    outside = re.sub(r"\([^)]*\)", " ", description or "")
    words = tokenize(outside) | tokenize(element_name or "")
    everything = words | tokenize(description or "")
    for category in _ORDER:
        if category == "cancel":
            if (words & _CANCEL_VERBS and everything & _CANCEL_OBJECTS) or words & _CANCEL_WITH_OBJECT:
                return "cancel"
        elif category == "account" and (_FOLLOW.search(outside) or _FOLLOW.search(element_name or "")):
            return "account"
        elif words & _STEMS[category]:
            return category
    return None


_CONCLUDING = ("submit", "send", "pay")          # one family: any of their verbs asks for any of them
_ALL_VERBS = set().union(*_STEMS.values()) | _CANCEL_VERBS


_PRINT = re.compile(r"\b(imprim\w*|impress\w*|print\w*)\b", re.IGNORECASE)


def unrequested_print(request: str, description: str, element_name: str = "") -> bool:
    """A click that prints (it opens the print dialog, or sends to a printer) the request did not ask for."""
    return bool(_PRINT.search(f"{description} {element_name}")) and not _PRINT.search(request or "")


def unrequested(category: Optional[str], request: str, description: str, element_name: str = "") -> bool:
    """
    Would a click send, save, confirm, pay or export something the request did not ask for?
    The models tend to "complete" a form on their own ("Enviar candidatura" after attaching the
    files they were asked to attach). It is asked for when the request has a verb of the family
    ("salve", "envie", "pague"; for exporting, a verb or a word for a file), or when the request
    and the button are about the same thing, verbs aside ("reserve a sala" and "Reservar sala",
    "cadastre a Maria" and "Salvar cadastro").
    """
    if category == "account":
        # Only a verb of the family asks for it: a request about the same person does not
        # ask to follow them ("abra o perfil da Jaine" is not "Seguir Jaine").
        return not tokenize(request or "") & (_STEMS["account"] | _FOLLOW_ASKED)
    if category not in _CONCLUDING + ("download",):
        return False
    asked = tokenize(request or "")
    if category in _CONCLUDING and asked & set().union(*(_STEMS[c] for c in _CONCLUDING)):
        return False
    if category == "download":
        from anchor.planner.reading import wants_file
        if asked & _STEMS["download"] or wants_file(request):
            return False
    about = (tokenize(re.sub(r"\([^)]*\)", " ", description or "")) | tokenize(element_name or "")) - _ALL_VERBS
    from anchor.engine.element_resolver.tokenizer import STOPWORDS_N
    return not (about - STOPWORDS_N) & asked


@dataclass
class ConfirmationRequest:
    action: str
    description: str          # the step's description
    element: str              # the name of the element that would be acted on
    category: str             # delete, submit, send, pay, download, upload, account
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
    """
    Asks in the terminal. With no one to answer (no terminal), the answer is no.
    remembers: whether the decision is kept (saved automations do; a one-off run does not),
    which changes what the question promises.
    """

    def __init__(self, input_fn=input, output=print, interactive=None, remembers=False):
        import sys
        self.input_fn, self.output, self.remembers = input_fn, output, remembers
        self.interactive = sys.stdin.isatty() if interactive is None else interactive

    def confirm(self, request: ConfirmationRequest) -> bool:
        from anchor.i18n import t
        self.output("\n" + t("confirm.ask", category=t("confirm.cat_" + request.category),
                              element=request.element, description=request.description))
        if not self.interactive:
            self.output(t("confirm.no_terminal"))
            return Decision(False, save=False)
        try:
            answer = self.input_fn(t("confirm.prompt_saved" if self.remembers else "confirm.prompt") + " ").strip().lower()
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
