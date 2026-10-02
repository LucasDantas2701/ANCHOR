"""
Sensitive actions in a saved automation: each decision is asked once and saved.

An action the user allowed is not asked again in the next runs (nor in the next rows of
a spreadsheet); an action the user denied with an explicit "no" stops the run, in this run
and in the next ones, until the decision is forgotten (python -m anchor.automations
confirmations <name> --forget N). Just pressing Enter, or having no terminal to answer,
denies only this time: nothing is saved, and the next run asks again.
"""

from __future__ import annotations

from anchor.engine.sensitive import ConfirmationRequest
from anchor.i18n import t

from .params import templatize


class AutomationConfirmer:
    def __init__(self, store, name: str, values: dict, ask, report=print):
        self.store, self.name, self.values, self.ask = store, name, values, ask
        self.report = report or (lambda _: None)

    def _key(self, request: ConfirmationRequest) -> dict:
        return {"action": request.action, "element": templatize(request.element, self.values),
                "category": request.category}

    def confirm(self, request: ConfirmationRequest) -> bool:
        key = self._key(request)
        for item in self.store.confirmations(self.name):
            if {k: item[k] for k in key} == key:
                if item["decision"] == "denied":
                    self.report(t("confirm.denied_before", element=key["element"], number=item["number"],
                                  name=self.name))
                return item["decision"] == "allowed"
        allowed = self.ask.confirm(request)
        if not getattr(allowed, "save", True):
            self.report(t("confirm.not_now"))
            return bool(allowed)
        record = self.store.add_confirmation(self.name, {**key, "decision": "allowed" if allowed else "denied"})
        self.report(t("confirm.saved_allowed" if allowed else "confirm.saved_denied", number=record["number"]))
        return bool(allowed)
