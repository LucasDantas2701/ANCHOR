"""
Everything the *model* reads, in the planner prompt's language.

Portuguese is the default: it is the language the planner was measured in,
and its texts are kept exactly as they were, so the measured results stay
valid. English is an option (the "prompt_language" of the LLM profile, or
--prompt-language), and it must be measured on the dev set before use.

What the *user* reads is in anchor.i18n, with its own language setting.
The failure reasons ("why.*") live here but are also shown to the user:
render them with the interface language for that.
"""

from __future__ import annotations

PROMPT_LANGUAGES = ("pt", "en")
DEFAULT_PROMPT_LANGUAGE = "pt"
AUTO = "auto"   # the prompt follows the request's language (see detect_language)

# Words that are common in one language and rare in the other. Ambiguous ones
# ("a", "e", "do" in English, "no") are left out.
_PT_WORDS = {
    "o", "os", "as", "da", "das", "dos", "de", "em", "na", "nas", "nos", "para", "pra", "com", "que",
    "um", "uma", "ao", "aos", "pelo", "pela", "não", "nao", "meu", "minha", "seu", "sua", "depois",
    "todos", "todas", "também", "tambem", "só", "so", "isso", "esse", "essa", "este", "esta",
}
_EN_WORDS = {
    "the", "to", "and", "of", "in", "for", "with", "my", "your", "is", "are", "it", "this", "that",
    "then", "only", "all", "from", "by", "an", "at", "please", "into", "on",
}
# Command verbs: a request almost always starts with one.
_EN_VERBS = {
    "save", "search", "find", "add", "put", "delete", "remove", "open", "click", "fill", "type", "enter",
    "select", "choose", "pick", "register", "sign", "cancel", "show", "sort", "change", "set", "tick",
    "check", "uncheck", "create", "send", "submit", "export", "download", "upload", "edit", "update",
    "close", "go", "log", "filter", "accept", "confirm", "write", "buy", "pay", "book", "list", "display",
}
_PT_VERBS = {
    "salve", "salvar", "pesquise", "pesquisar", "procure", "busque", "adicione", "coloque", "exclua",
    "apague", "remova", "abra", "clique", "preencha", "digite", "selecione", "escolha", "cadastre",
    "entre", "cancele", "mostre", "ordene", "troque", "mude", "marque", "desmarque", "crie", "envie",
    "exporte", "baixe", "edite", "atualize", "feche", "vá", "va", "filtre", "aceite", "confirme",
    "escreva", "compre", "pague", "reserve", "liste", "mostra", "cancela", "salva", "pesquisa",
}
_ACCENTS = set("áàâãéêíóôõúç")


def detect_language(text: str) -> str:
    """
    "pt" or "en", for the planner prompt. Counts words typical of each language
    (and accents, which only Portuguese has here). On a tie, Portuguese, the
    measured default.
    """
    import re

    words = re.findall(r"[a-záàâãéêíóôõúç]+", (text or "").lower())
    pt = sum(w in _PT_WORDS for w in words) + (2 if _ACCENTS & set((text or "").lower()) else 0)
    en = sum(w in _EN_WORDS for w in words)
    if words:
        pt += words[0] in _PT_VERBS
        en += words[0] in _EN_VERBS
    return "en" if en > pt else "pt"


def mt(key: str, language: str = DEFAULT_PROMPT_LANGUAGE, **values) -> str:
    """The model-facing text for key, in the given language."""
    entry = TEXT[key]
    text = entry.get(language) or entry[DEFAULT_PROMPT_LANGUAGE]
    return text.format(**values) if values else text


class Reason:
    """A failure reason, written later in whichever language each reader needs."""

    def __init__(self, key: str, **values):
        self.key, self.values = key, values

    def render(self, language: str) -> str:
        return mt(self.key, language, **self.values)

    def __repr__(self) -> str:
        return f"Reason({self.key!r}, {self.values!r})"


TEXT: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------ user message
    "user.page": {"pt": "Página aberta: {url}", "en": "Open page: {url}"},
    "user.request": {"pt": "Pedido do usuário: {request}", "en": "User request: {request}"},
    "user.history": {
        "pt": "O que já aconteceu nesta execução:\n{lines}\n\nDevolva APENAS os passos que ainda faltam "
              "para cumprir o pedido, a partir da página como ela está agora. Não repita passos que já "
              "deram certo. Se um passo falhou, tente outro caminho (por exemplo, fechar o que cobre a "
              "página). Se o pedido já foi cumprido, devolva uma lista vazia.",
        "en": "What has already happened in this run:\n{lines}\n\nReturn ONLY the steps still needed to "
              "fulfill the request, starting from the page as it is now. Do not repeat steps that "
              "already worked. If a step failed, try another way (for example, closing whatever covers "
              "the page). If the request is already fulfilled, return an empty list.",
    },
    "user.notes": {"pt": "Observações do usuário sobre esta tarefa, de execuções anteriores:\n{lines}",
                   "en": "Notes from the user about this task, from earlier runs:\n{lines}"},
    "user.elements": {"pt": "Elementos visíveis na página:\n{lines}", "en": "Visible elements on the page:\n{lines}"},
    "summary.options": {"pt": " [opções: {options}]", "en": " [options: {options}]"},
    # ------------------------------------------------------------ plan errors (sent back to the model)
    "plan.not_json": {"pt": "a resposta não é um JSON válido ({msg})", "en": "the answer is not valid JSON ({msg})"},
    "plan.retry": {"pt": "Plano inválido: {error}. Corrija e responda só com o JSON.",
                   "en": "Invalid plan: {error}. Fix it and answer with the JSON only."},
    "plan.goals_list": {"pt": '"goals" deve ser uma lista', "en": '"goals" must be a list'},
    "plan.goal_no_id": {"pt": "meta {i} sem id", "en": "goal {i} has no id"},
    "plan.goal_twice": {"pt": 'a meta "{gid}" aparece duas vezes', "en": 'goal "{gid}" appears twice'},
    "plan.steps_list": {"pt": 'a resposta deve ser um objeto com a lista "steps"',
                        "en": 'the answer must be an object with the "steps" list'},
    "plan.step_not_object": {"pt": "passo {i} não é um objeto", "en": "step {i} is not an object"},
    "plan.bad_action": {"pt": 'passo {i}: ação "{action}" não existe; use uma de {actions}',
                        "en": 'step {i}: action "{action}" does not exist; use one of {actions}'},
    "plan.empty_description": {"pt": "passo {i}: descrição vazia", "en": "step {i}: empty description"},
    "plan.needs_value": {"pt": 'passo {i}: a ação "{action}" precisa de um valor',
                         "en": 'step {i}: the "{action}" action needs a value'},
    "plan.no_conclusive": {"pt": "marque como conclusiva (conclusive: true) a meta que conclui o pedido",
                           "en": "mark as conclusive (conclusive: true) the goal that completes the request"},
    "plan.step_no_goal": {"pt": "passo {i}: informe a meta (goal) a que ele pertence",
                          "en": "step {i}: give the goal it belongs to"},
    "plan.unknown_goal": {"pt": 'passo {i}: a meta "{goal}" não existe; use uma de {ids}',
                          "en": 'step {i}: goal "{goal}" does not exist; use one of {ids}'},
    "plan.empty_goals": {
        "pt": "toda meta precisa de pelo menos um passo; a(s) meta(s) {goals} não tem nenhum: acrescente "
              "os passos ou remova a meta",
        "en": "every goal needs at least one step; goal(s) {goals} have none: add the steps or remove the goal",
    },
    "plan.conclusive_last": {"pt": "passo {i}: as metas conclusivas (salvar, enviar...) devem vir por último",
                             "en": "step {i}: conclusive goals (save, send...) must come last"},
    "plan.missing_verb": {
        "pt": 'o pedido pede para "{verb}", mas nenhum clique ou tecla faz isso; inclua o passo que conclui '
              "o pedido (ex.: clicar em Salvar, clicar em Buscar ou pressionar Enter no campo)",
        "en": 'the request asks to "{verb}", but no click or key press does it; add the step that completes '
              "the request (e.g. click Save, click Search or press Enter in the field)",
    },
    "plan.missing_value": {"pt": 'o pedido menciona "{value}", mas nenhum passo o usa',
                           "en": 'the request mentions "{value}", but no step uses it'},
    # ------------------------------------------------------------ execution history
    "hist.done": {"pt": "feito: {step}", "en": "done: {step}"},
    "hist.failed": {"pt": "falhou: {step} — {reason}", "en": "failed: {step} — {reason}"},
    "hist.blocked": {"pt": "barrado: {step} — {reason}", "en": "blocked: {step} — {reason}"},
    "hist.skipped": {"pt": "pulado pelo usuário: {step}", "en": "skipped by the user: {step}"},
    "hist.message": {"pt": 'apareceu na página: "{message}"', "en": 'appeared on the page: "{message}"'},
    "hist.suspicion": {"pt": 'suspeita: depois de "{step}", esperava ver "{expect}", e não apareceu',
                       "en": 'suspicion: after "{step}", expected to see "{expect}", and it did not appear'},
    "hist.not_fulfilled": {"pt": "o pedido ainda não foi cumprido: {reason}",
                           "en": "the request is not fulfilled yet: {reason}"},
    "ctx.goals": {"pt": "metas: {goals}", "en": "goals: {goals}"},
    "ctx.messages": {"pt": "mensagens visíveis na página agora: {messages}",
                     "en": "messages visible on the page now: {messages}"},
    "goal.done": {"pt": "cumprida", "en": "done"},
    "goal.pending": {"pt": "pendente", "en": "pending"},
    "goal.dropped": {"pt": "descartada ou substituída", "en": "dropped or replaced"},
    # ------------------------------------------------------------ failure reasons (model and user)
    "why.obscured": {"pt": "o elemento está coberto por outro (um modal, aviso ou banner); feche-o antes",
                     "en": "the element is covered by another one (a modal, notice or banner); close it first"},
    "why.not_found": {"pt": "nenhum elemento da página corresponde a essa descrição",
                      "en": "no element on the page matches this description"},
    "why.ambiguous": {"pt": "mais de um elemento corresponde a essa descrição; seja mais específico",
                      "en": "more than one element matches this description; be more specific"},
    "why.error": {"pt": "a ação não pôde ser executada ({detail})", "en": "the action could not be performed ({detail})"},
    "why.error_plain": {"pt": "a ação não pôde ser executada", "en": "the action could not be performed"},
    "why.status": {"pt": "{status}", "en": "{status}"},
    "why.error_message": {"pt": 'apareceu a mensagem "{message}"', "en": 'the message "{message}" appeared'},
    "why.no_effect": {"pt": "a ação não teve efeito visível na página", "en": "the action had no visible effect on the page"},
    "why.repeated_now": {"pt": "este passo acabou de ser executado com sucesso; não o repita",
                         "en": "this step was just performed successfully; do not repeat it"},
    "why.repeated": {"pt": "este passo já foi executado {count} vezes; o plano está repetindo",
                     "en": "this step has already been performed {count} times; the plan is repeating"},
    "why.destructive": {"pt": "o pedido não pede para fechar, excluir, remover, ocultar ou cancelar; não inclua esse passo",
                        "en": "the request does not ask to close, delete, remove, hide or cancel; do not include this step"},
    "why.field_value": {"pt": 'o campo ficou com "{got}" em vez de "{want}"', "en": 'the field has "{got}" instead of "{want}"'},
    "why.list_value": {"pt": 'a lista ficou com "{got}" em vez de "{want}"', "en": 'the list has "{got}" instead of "{want}"'},
    "why.not_checked": {"pt": "a caixa não ficou marcada", "en": "the box did not get checked"},
    "why.still_checked": {"pt": "a caixa continuou marcada", "en": "the box is still checked"},
    "why.expected_missing": {"pt": 'esperava ver "{expect}", e não apareceu', "en": 'expected to see "{expect}", and it did not appear'},
}
