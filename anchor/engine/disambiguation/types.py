"""
Contract between the Executor and whatever asks the user.

The Executor does not know whether the question shows up in the terminal,
on a web page or in an app: it only builds a ChoiceRequest and receives a
UserChoice. To create another interface (e.g. the frontend), implement the
Disambiguator protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Protocol


@dataclass
class CandidateView:
    """A candidate described for a non-technical person."""
    number: int          # number shown on the page (1, 2, 3...)
    kind: str            # "Button", "Link", "Text field"...
    name: str            # the element's text, label or visual hint
    near: str            # surrounding text, to tell identical elements apart


@dataclass
class ChoiceRequest:
    action: str                      # requested action (click, fill...)
    description: str                 # step in natural language
    reason: Literal["ambiguous", "not_found"]
    candidates: list[CandidateView]
    screenshot: Optional[bytes]      # screenshot with the numbers (when there is no visible window)
    can_point: bool                  # can the user click directly on the page?


@dataclass
class UserChoice:
    kind: Literal["candidate", "point", "skip"]
    number: Optional[int] = None     # only for kind == "candidate"


class Disambiguator(Protocol):
    def choose(self, request: ChoiceRequest) -> UserChoice:
        """Shows the candidates and returns the user's choice."""
        ...

    def notify(self, message: str) -> None:
        """Shows a short message to the user (e.g. 'click the element')."""
        ...
