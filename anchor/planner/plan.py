"""
The plan: the request's goals and the list of steps the Executor can run.

Each step belongs to a goal. A goal is fulfilled when its last step worked, with
the effect verified; the end is only declared when all of them are fulfilled.
Conclusive goals (save, send, confirm) come after the others.

The error messages go back to the model so it can fix the plan, so they are
written in the planner prompt's language (see language.py).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from .language import DEFAULT_PROMPT_LANGUAGE, mt

# Actions the planner can use, and whether they need a value.
ACTIONS = {
    "click": False,
    "hover": False,
    "check": False,
    "uncheck": False,
    "fill": True,          # value = text to type
    "select": True,        # value = option text
    "press": True,         # value = key (e.g. "Enter")
    "extract_text": False,
}

# JSON schema required from the model (OpenAI "structured outputs" format).
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "goals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "description": {"type": "string"},
                    "conclusive": {"type": "boolean"},
                },
                "required": ["id", "description", "conclusive"],
                "additionalProperties": False,
            },
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(ACTIONS)},
                    "description": {"type": "string"},
                    "value": {"type": ["string", "null"]},
                    "goal": {"type": "string"},
                    "expect": {"type": ["string", "null"]},
                },
                "required": ["action", "description", "value", "goal", "expect"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["goals", "steps"],
    "additionalProperties": False,
}


class PlanError(ValueError):
    """The model returned something that is not a valid plan."""


@dataclass
class Goal:
    id: str
    description: str
    conclusive: bool = False


@dataclass
class Step:
    action: str
    description: str
    value: Optional[str] = None
    goal: Optional[str] = None     # id of the goal the step belongs to
    expect: Optional[str] = None   # text that should appear on the page after the step


@dataclass
class Plan:
    steps: list[Step]
    goals: list[Goal] = field(default_factory=list)
    model: str = ""
    latency_s: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    attempts: int = 1
    raw: str = field(default="", repr=False)

    def to_dict(self) -> dict:
        return asdict(self)


def parse_goals(data: object, language: str = DEFAULT_PROMPT_LANGUAGE) -> list[Goal]:
    """The plan's goals (optional: plans without goals are still valid)."""
    raw = data.get("goals") if isinstance(data, dict) else None
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PlanError(mt("plan.goals_list", language))
    goals, ids = [], set()
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict) or not str(item.get("id") or "").strip():
            raise PlanError(mt("plan.goal_no_id", language, i=i))
        gid = str(item["id"]).strip()
        if gid in ids:
            raise PlanError(mt("plan.goal_twice", language, gid=gid))
        ids.add(gid)
        goals.append(Goal(gid, str(item.get("description") or "").strip(), bool(item.get("conclusive"))))
    return goals


def parse_plan(data: object, language: str = DEFAULT_PROMPT_LANGUAGE) -> list[Step]:
    """Validates the model's JSON and returns the steps. Raises PlanError with the reason."""
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise PlanError(mt("plan.steps_list", language))

    steps = []
    for i, item in enumerate(data["steps"], 1):
        if not isinstance(item, dict):
            raise PlanError(mt("plan.step_not_object", language, i=i))
        action = item.get("action")
        description = (item.get("description") or "").strip()
        value = item.get("value")
        if action not in ACTIONS:
            raise PlanError(mt("plan.bad_action", language, i=i, action=action, actions=", ".join(ACTIONS)))
        if not description:
            raise PlanError(mt("plan.empty_description", language, i=i))
        if ACTIONS[action] and (value is None or str(value).strip() == ""):
            raise PlanError(mt("plan.needs_value", language, i=i, action=action))
        goal = str(item["goal"]).strip() if item.get("goal") else None
        expect = str(item["expect"]).strip() if item.get("expect") else None
        steps.append(Step(action, description, None if value is None else str(value), goal, expect or None))
    return steps


def check_goals(steps: list[Step], goals: list[Goal], known: set[str] | None = None,
                language: str = DEFAULT_PROMPT_LANGUAGE) -> None:
    """
    Checks the links between steps and goals. known: goal ids from earlier
    plans in the same run (a replan may refer to them).
    """
    if not goals and not known:
        return
    if goals and not known and steps and not any(g.conclusive for g in goals):
        raise PlanError(mt("plan.no_conclusive", language))
    ids = {g.id for g in goals} | (known or set())
    for i, step in enumerate(steps, 1):
        if not step.goal:
            raise PlanError(mt("plan.step_no_goal", language, i=i))
        if step.goal not in ids:
            raise PlanError(mt("plan.unknown_goal", language, i=i, goal=step.goal, ids=", ".join(sorted(ids))))
    empty = [g.id for g in goals if not any(s.goal == g.id for s in steps)]
    if steps and empty:
        raise PlanError(mt("plan.empty_goals", language, goals=", ".join(empty)))
    conclusive = {g.id for g in goals if g.conclusive}
    seen_conclusive = False
    for i, step in enumerate(steps, 1):
        if step.goal in conclusive:
            seen_conclusive = True
        elif seen_conclusive:
            raise PlanError(mt("plan.conclusive_last", language, i=i))


# ----------------------------------------------------------------------
# Does the plan cover the request? (checked without the LLM, initial plan only)
# ----------------------------------------------------------------------

import re as _re

# Verbs that complete a request: if the request uses them, some step must do them.
CONCLUSIVE_VERBS = ["salvar", "save", "enviar", "send", "submit", "excluir", "delete", "remover",
                    "pesquisar", "buscar", "procurar", "search", "cancelar", "cancel",
                    "confirmar", "confirm", "baixar", "download"]

SEARCH_VERBS = ["pesquisar", "buscar", "procurar", "search"]

_QUOTED = _re.compile(r'["“]([^"”]{2,})["”]')
_EMAIL = _re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_NUMBER = _re.compile(r"\d[\d.()\-/ ]{2,}\d")
_NAME = _re.compile(r"(?<![.!?]\s)(?<!^)\b([A-ZÀ-Ý][\wÀ-ÿ]*(?:\s+(?:de|da|do|dos|das)?\s*[A-ZÀ-Ý][\wÀ-ÿ]*)*)")


# English capitalizes languages, weekdays and months, which are not data the plan must
# copy: the page may show them in another form ("Portuguese" → the option "Português").
_CAPITALIZED_COMMON = {
    "english", "portuguese", "spanish", "french", "german", "italian", "chinese", "japanese",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december",
}


def request_values(request: str) -> list[str]:
    """Data the request brings and the plan needs to use."""
    text = request.strip()
    found = _QUOTED.findall(text) + _EMAIL.findall(text) + _NUMBER.findall(text)
    first_word = text.split()[0] if text.split() else ""
    for name in _NAME.findall(text):
        if name != first_word and len(name) > 1 and name.lower() not in _CAPITALIZED_COMMON:
            found.append(name)
    return list(dict.fromkeys(v.strip() for v in found if v.strip()))


def check_request(steps: list[Step], goals: list[Goal], request: str,
                  language: str = DEFAULT_PROMPT_LANGUAGE) -> None:
    from anchor.engine.element_resolver.tokenizer import expand_actions, normalize_tokens, tokenize

    def words(text: str) -> set[str]:
        tokens = tokenize(text or "")
        return tokens | normalize_tokens(tokens)

    plan_words = set()
    for s in steps:
        plan_words |= words(f"{s.description} {s.value or ''}")
    # The conclusive verb must be in a completing step: a click or a key press.
    # Neither a goal's description ("vaga salva") nor a fill counts.
    concluding_words = set()
    for s in steps:
        if s.action in ("click", "press"):
            concluding_words |= words(s.description)
        # Pressing Enter in a field is a search, whatever the field is called ("Type a coin").
        if s.action == "press" and (s.value or "").strip().lower() == "enter":
            concluding_words |= {v for w in SEARCH_VERBS for v in words(w)}

    request_words = words(request)
    for verb in CONCLUSIVE_VERBS:
        forms = words(verb)                       # e.g. "pesquisar" → {"pesquis", "search"}
        if not forms & request_words:
            continue
        equivalents = forms | expand_actions(forms)
        if not equivalents & concluding_words:
            raise PlanError(mt("plan.missing_verb", language, verb=verb))

    plan_text = " ".join(f"{s.description} {s.value or ''}" for s in steps)
    plan_digits = _re.sub(r"\D", "", plan_text)
    for value in request_values(request):
        digits = _re.sub(r"\D", "", value)
        if len(digits) >= 3 and digits == _re.sub(r"\D", "", value.replace(" ", "")) and digits in plan_digits:
            continue
        need = words(value)
        if need and len(need & plan_words) / len(need) < 0.5:
            raise PlanError(mt("plan.missing_value", language, value=value))


# --------------------------------------------------------------------------
# Typed values must come from the request (checked on every plan)
# --------------------------------------------------------------------------

def _plain(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _alnum(text: str) -> str:
    return _re.sub(r"[^a-z0-9]+", "", _plain(text))


def _tokens(text: str) -> set[str]:
    return set(_re.findall(r"[a-z0-9]+", _plain(text)))


def check_values_from_request(steps: list[Step], sources: list[str],
                              language: str = DEFAULT_PROMPT_LANGUAGE) -> None:
    """
    What a plan types (fill) must come from the request (or the user's notes), never from the
    page: a page may try to make the agent type data it chose, such as an attacker's e-mail.
    A value is accepted if, ignoring case, accents and punctuation, it is part of the sources,
    or all its words are in them.
    """
    text = " ".join(s for s in sources if s)
    flat, words = _alnum(text), _tokens(text)
    for i, step in enumerate(steps, 1):
        if step.action != "fill" or not step.value:
            continue
        value = step.value
        if _alnum(value) and (_alnum(value) in flat or _tokens(value) <= words):
            continue
        raise PlanError(mt("plan.value_not_in_request", language, i=i, value=value))
