from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from anchor.engine.element_resolver import Match


class ActionExecutionError(Exception):
    def __init__(self, result: "ActionResult"):
        self.result = result
        super().__init__(repr(result))


@dataclass
class ActionResult:
    status: str
    action: str
    description: str

    selected_element: Optional[Match] = None
    score: Optional[float] = None
    value: Optional[Any] = None
    candidates: Optional[list[Match]] = None
    error: Optional[str] = None

    # Who chose the element: "heuristic", "user" (disambiguation),
    # "memory" (a previous choice by the user) or "user_skipped"
    # (the user asked to skip the step).
    resolved_by: str = "heuristic"

    # Only for resolved_by == "memory": how similar the element on the page
    # is to the remembered one. It is not comparable to the heuristic's score,
    # so it lives in a separate field (and score is None).
    similarity: Optional[float] = None

    def __bool__(self) -> bool:
        return self.status == "success"

    def raise_if_error(self) -> "ActionResult":
        if self.status != "success":
            raise ActionExecutionError(self)

        return self

    def __repr__(self) -> str:
        if self.status == "success":
            element = self.selected_element

            if element:
                label = (
                    element.label
                    or element.text
                    or f"{element.tag}#{element.id}"
                )
            else:
                label = ""

            measure = (
                f"similarity={self.similarity:.2f}"
                if self.similarity is not None
                else f"score={self.score:.2f}"
                if self.score is not None
                else "score=None"
            )

            return (
                f"ActionResult("
                f"status='success', "
                f"action='{self.action}', "
                f"{measure}, "
                f"element='{label}'"
                + (f", resolved_by='{self.resolved_by}'" if self.resolved_by != "heuristic" else "")
                + f")"
            )

        if self.status == "ambiguous":
            scores = ", ".join(
                f"{candidate.score:.2f}"
                for candidate in (self.candidates or [])[:3]
            )

            return (
                f"ActionResult("
                f"status='ambiguous', "
                f"action='{self.action}', "
                f"candidates=[{scores}]"
                f")"
            )

        if self.status == "error":
            return (
                f"ActionResult("
                f"status='error', "
                f"action='{self.action}', "
                f"error='{self.error}'"
                f")"
            )

        return (
            f"ActionResult("
            f"status='not_found', "
            f"action='{self.action}', "
            f"description='{self.description}'"
            f")"
        )