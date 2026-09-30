"""Describes a Match for a non-technical person."""

from anchor.engine.element_resolver import Match
from anchor.i18n import MESSAGES, t

from .types import CandidateView


def kinds(language: str) -> dict[str, str]:
    """All element kinds in one language, by role."""
    return {key[len("kind."):]: MESSAGES[key][language] for key in MESSAGES if key.startswith("kind.")}


# Portuguese kinds: the ones the page summary sends to the model with the default
# (Portuguese) planner prompt, which the planner strips if the model copies them.
KIND = kinds("pt")


def kind_of(role: str, language: str | None = None) -> str:
    """The element kind in plain words ("Button", "Text field"...)."""
    key = f"kind.{role}" if f"kind.{role}" in MESSAGES else "kind.other"
    return t(key, language)


def describe(match: Match, number: int, language: str | None = None) -> CandidateView:
    """
    language: "en" or "pt"; None uses the interface language. The page summary
    sent to the model passes the planner's language explicitly.
    """
    # No label, text or visual hint: data-testid is often descriptive
    # ("shopping-cart-link" → "shopping cart link").
    test_id = " ".join(match.test_id.replace("-", " ").replace("_", " ").split())
    name = match.label or match.text or match.hint or match.value or test_id or t("element.no_text", language)

    # Text too short to identify the element (e.g. the cart counter "2"):
    # add the icon's visual hint ("shopping cart 2").
    if match.hint and name == match.text and len(name) <= 3:
        name = f"{match.hint} {name}"
    near = " ".join((match.context or "").split())

    # Remove the element's own name from "near" (case-insensitive).
    start = near.lower().find(name.lower())
    if start >= 0:
        near = " ".join((near[:start] + near[start + len(name):]).split())
    if len(near) > 60:
        near = near[:57].rstrip() + "..."
    return CandidateView(
        number=number,
        kind=kind_of(match.role, language),
        name=name[:60],
        near=near,
    )
