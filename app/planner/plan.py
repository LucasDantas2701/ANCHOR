"""
O plano: as metas do pedido e a lista de passos que o Executor sabe executar.

Cada passo pertence a uma meta. Uma meta é cumprida quando o último passo dela
deu certo, com o efeito verificado; o fim só é declarado com todas cumpridas.
Metas conclusivas (salvar, enviar, confirmar) vêm depois das outras.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

# Ações que o planejador pode usar e se exigem um valor.
ACTIONS = {
    "click": False,
    "hover": False,
    "check": False,
    "uncheck": False,
    "fill": True,          # valor = texto a digitar
    "select": True,        # valor = texto da opção
    "press": True,         # valor = tecla (ex.: "Enter")
    "extract_text": False,
}

# Esquema JSON exigido do modelo (formato "structured outputs" da OpenAI).
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
    """O modelo devolveu algo que não é um plano válido."""


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
    goal: Optional[str] = None     # id da meta a que o passo pertence
    expect: Optional[str] = None   # texto que deve aparecer na página depois do passo


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


def parse_goals(data: object) -> list[Goal]:
    """Metas do plano (opcionais: planos sem metas continuam válidos)."""
    raw = data.get("goals") if isinstance(data, dict) else None
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PlanError('"goals" deve ser uma lista')
    goals, ids = [], set()
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict) or not str(item.get("id") or "").strip():
            raise PlanError(f"meta {i} sem id")
        gid = str(item["id"]).strip()
        if gid in ids:
            raise PlanError(f'a meta "{gid}" aparece duas vezes')
        ids.add(gid)
        goals.append(Goal(gid, str(item.get("description") or "").strip(), bool(item.get("conclusive"))))
    return goals


def parse_plan(data: object) -> list[Step]:
    """Valida o JSON do modelo e devolve os passos. Lança PlanError com o motivo."""
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise PlanError('a resposta deve ser um objeto com a lista "steps"')

    steps = []
    for i, item in enumerate(data["steps"], 1):
        if not isinstance(item, dict):
            raise PlanError(f"passo {i} não é um objeto")
        action = item.get("action")
        description = (item.get("description") or "").strip()
        value = item.get("value")
        if action not in ACTIONS:
            raise PlanError(f'passo {i}: ação "{action}" não existe; use uma de {", ".join(ACTIONS)}')
        if not description:
            raise PlanError(f"passo {i}: descrição vazia")
        if ACTIONS[action] and (value is None or str(value).strip() == ""):
            raise PlanError(f'passo {i}: a ação "{action}" precisa de um valor')
        goal = str(item["goal"]).strip() if item.get("goal") else None
        expect = str(item["expect"]).strip() if item.get("expect") else None
        steps.append(Step(action, description, None if value is None else str(value), goal, expect or None))
    return steps


def check_goals(steps: list[Step], goals: list[Goal], known: set[str] | None = None) -> None:
    """
    Confere as ligações entre passos e metas. known: ids de metas de planos
    anteriores da mesma execução (um replanejamento pode citá-las).
    """
    if not goals and not known:
        return
    if goals and not known and steps and not any(g.conclusive for g in goals):
        raise PlanError("marque como conclusiva (conclusive: true) a meta que conclui o pedido")
    ids = {g.id for g in goals} | (known or set())
    for i, step in enumerate(steps, 1):
        if not step.goal:
            raise PlanError(f"passo {i}: informe a meta (goal) a que ele pertence")
        if step.goal not in ids:
            raise PlanError(f'passo {i}: a meta "{step.goal}" não existe; use uma de {", ".join(sorted(ids))}')
    empty = [g.id for g in goals if not any(s.goal == g.id for s in steps)]
    if steps and empty:
        raise PlanError(f"toda meta precisa de pelo menos um passo; a(s) meta(s) {', '.join(empty)} "
                        "não tem nenhum: acrescente os passos ou remova a meta")
    conclusive = {g.id for g in goals if g.conclusive}
    seen_conclusive = False
    for i, step in enumerate(steps, 1):
        if step.goal in conclusive:
            seen_conclusive = True
        elif seen_conclusive:
            raise PlanError(f"passo {i}: as metas conclusivas (salvar, enviar...) devem vir por último")


# ----------------------------------------------------------------------
# O plano cobre o pedido? (conferido sem LLM, só no plano inicial)
# ----------------------------------------------------------------------

import re as _re

# Verbos que concluem um pedido: se o pedido os usa, algum passo ou meta precisa falar neles.
CONCLUSIVE_VERBS = ["salvar", "save", "enviar", "send", "submit", "excluir", "delete", "remover",
                    "pesquisar", "buscar", "procurar", "search", "cancelar", "cancel",
                    "confirmar", "confirm", "baixar", "download"]

_QUOTED = _re.compile(r'["“]([^"”]{2,})["”]')
_EMAIL = _re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_NUMBER = _re.compile(r"\d[\d.()\-/ ]{2,}\d")
_NAME = _re.compile(r"(?<![.!?]\s)(?<!^)\b([A-ZÀ-Ý][\wÀ-ÿ]*(?:\s+(?:de|da|do|dos|das)?\s*[A-ZÀ-Ý][\wÀ-ÿ]*)*)")


def request_values(request: str) -> list[str]:
    """Dados que o pedido traz e que o plano precisa usar."""
    text = request.strip()
    found = _QUOTED.findall(text) + _EMAIL.findall(text) + _NUMBER.findall(text)
    first_word = text.split()[0] if text.split() else ""
    for name in _NAME.findall(text):
        if name != first_word and len(name) > 1:
            found.append(name)
    return list(dict.fromkeys(v.strip() for v in found if v.strip()))


def check_request(steps: list[Step], goals: list[Goal], request: str) -> None:
    from app.engine.element_resolver.tokenizer import expand_actions, normalize_tokens, tokenize

    def words(text: str) -> set[str]:
        tokens = tokenize(text or "")
        return tokens | normalize_tokens(tokens)

    plan_words = set()
    for s in steps:
        plan_words |= words(f"{s.description} {s.value or ''}")
    # O verbo conclusivo precisa estar num passo que conclui: um clique ou uma tecla.
    # Nem a descrição de uma meta ("vaga salva") nem um preenchimento contam.
    concluding_words = set()
    for s in steps:
        if s.action in ("click", "press"):
            concluding_words |= words(s.description)

    request_words = words(request)
    for verb in CONCLUSIVE_VERBS:
        forms = words(verb)                       # ex.: "pesquisar" → {"pesquis", "search"}
        if not forms & request_words:
            continue
        equivalents = forms | expand_actions(forms)
        if not equivalents & concluding_words:
            raise PlanError(f'o pedido pede para "{verb}", mas nenhum clique ou tecla faz isso; '
                            "inclua o passo que conclui o pedido (ex.: clicar em Salvar, "
                            "clicar em Buscar ou pressionar Enter no campo)")

    plan_text = " ".join(f"{s.description} {s.value or ''}" for s in steps)
    plan_digits = _re.sub(r"\D", "", plan_text)
    for value in request_values(request):
        digits = _re.sub(r"\D", "", value)
        if len(digits) >= 3 and digits == _re.sub(r"\D", "", value.replace(" ", "")) and digits in plan_digits:
            continue
        need = words(value)
        if need and len(need & plan_words) / len(need) < 0.5:
            raise PlanError(f'o pedido menciona "{value}", mas nenhum passo o usa')
