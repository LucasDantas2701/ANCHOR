"""
Loop do agente: pedido → plano → execução passo a passo → replanejamento → fim.

O LLM só planeja. Cada passo é executado pelo ActionExecutor, que usa a
memória das escolhas, a heurística e, quando ela recusa, o desempate pelo
usuário. O agente volta ao planejador em três situações:

    1. a página mudou (navegação): pede os passos que faltam na página nova;
    2. um passo falhou: informa o que foi feito e o motivo da falha;
    3. o plano acabou: pergunta se falta algo; lista vazia = objetivo atingido.

Três falhas cancelam a execução, com um relato ao usuário.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from playwright.sync_api import Page

from app.engine.action_executor import ActionExecutor, ActionResult
from app.engine.element_resolver.resolver import accepts
from app.engine.element_resolver.tokenizer import (
    DESTRUCTIVE_N,
    STOPWORDS_N,
    normalize_tokens,
    tokenize,
)
from app.planner import Plan, Step, page_elements, run_step
from app.planner.execute import clean_description, clean_value

from .effects import EffectWatcher, state_problem

# Radicais de "pesquisar", "buscar", "procurar", "search", "find", "ir", "go":
# um clique desses sem botão, logo depois de preencher um campo, vira Enter.
SUBMIT_STEMS = {"pesquis", "busc", "procur", "search", "find", "go", "lupa"}


@dataclass
class StepRecord:
    step: Step
    status: str                  # success, not_found, ambiguous, error, skipped
    resolved_by: str = ""
    note: str = ""


@dataclass
class AgentResult:
    status: str                  # "success" | "cancelled" | "failed"
    message: str
    records: list[StepRecord] = field(default_factory=list)
    llm_calls: int = 0
    replans: int = 0
    failures: int = 0
    interventions: int = 0       # passos em que o usuário escolheu o elemento
    no_effect: int = 0           # ações que não tiveram efeito na página
    goals_total: int = 0         # metas definidas pelo planejador
    goals_done: int = 0          # metas cumpridas no fim
    suspicions: int = 0          # passos em que o texto esperado não apareceu
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "success"


def step_key(step: Step) -> tuple:
    return (step.action, clean_description(step.description).lower(), step.value)


def describe_step(step: Step) -> str:
    value = f' = "{step.value}"' if step.value is not None else ""
    return f"{step.action} {step.description}{value}"


def failure_reason(result: ActionResult) -> str:
    """Motivo da falha em palavras que ajudam o planejador a tentar outro caminho."""
    element = result.selected_element
    if element is not None and getattr(element, "obscured", False):
        return "o elemento está coberto por outro (um modal, aviso ou banner); feche-o antes"
    if result.status == "not_found":
        return "nenhum elemento da página corresponde a essa descrição"
    if result.status == "ambiguous":
        return "mais de um elemento corresponde a essa descrição; seja mais específico"
    if result.status == "error":
        first_line = (result.error or "").strip().splitlines()[0][:120] if result.error else ""
        return f"a ação não pôde ser executada ({first_line})" if first_line else "a ação não pôde ser executada"
    return result.status


class Agent:
    """
    planner: qualquer objeto com plan(request, url, page_elements, history) → Plan.
    report: função chamada com uma linha de texto a cada acontecimento (padrão: print).
    """

    def __init__(
        self,
        page: Page,
        planner,
        executor: ActionExecutor,
        max_failures: int = 3,
        max_steps: int = 25,
        verify_end: bool = True,
        max_end_checks: int = 2,
        max_repeats: int = 3,
        verify_effect: bool = True,
        report: Optional[Callable[[str], None]] = print,
    ):
        self.page = page
        self.planner = planner
        self.executor = executor
        self.max_failures = max_failures
        self.max_steps = max_steps
        self.verify_end = verify_end
        self.max_end_checks = max_end_checks
        self.max_repeats = max_repeats
        self.watcher = EffectWatcher(page) if verify_effect else None
        self.report = report or (lambda _: None)

    # ------------------------------------------------------------------

    _VISIBLE_MESSAGES_JS = r"""() => [...document.querySelectorAll(
        '[role=alert],[role=status],[aria-live],.toast,.alert,.error,.message,.notification')]
        .filter(e => e.offsetParent !== null || getComputedStyle(e).position === 'fixed')
        .map(e => (e.innerText || '').replace(/\s+/g, ' ').trim())
        .filter(t => t.length > 1 && t.length <= 160).slice(0, 5)"""

    def _context_lines(self) -> list[str]:
        """O estado das metas e as mensagens visíveis, para o planejador (não fica no histórico)."""
        lines = []
        if self._goals:
            labels = {"done": "cumprida", "pending": "pendente", "dropped": "descartada ou substituída"}
            lines.append("metas: " + "; ".join(
                f"{g.id} ({g.description}): {labels[self._goal_status[g.id]]}" for g in self._goals.values()))
        try:
            visible = self.page.evaluate(self._VISIBLE_MESSAGES_JS)
        except Exception:
            visible = []
        if visible:
            lines.append("mensagens visíveis na página agora: " + " | ".join(f'"{m}"' for m in visible))
        return lines

    def _plan(self, request: str, history: list[str], result: AgentResult) -> Plan:
        elements = page_elements(self.executor.resolver, request=request)
        context = history + self._context_lines() if history else []
        extra = {"known_goals": set(self._goals)} if self._goals else {}
        plan = self.planner.plan(request, self.page.url, elements, context or None, **extra)
        for goal in getattr(plan, "goals", []) or []:
            if goal.id not in self._goals:
                self._goals[goal.id] = goal
                self._goal_status[goal.id] = "pending"
        result.goals_total = len(self._goals)
        result.llm_calls += 1
        result.tokens_in += plan.tokens_in
        result.tokens_out += plan.tokens_out
        return plan

    def _pending_goals(self) -> list[str]:
        """Metas que ainda impedem o fim (as descartadas e as substituídas não impedem)."""
        return [f"{g.id} ({g.description})" for g in self._goals.values() if self._goal_status[g.id] == "pending"]

    def _supersede(self, failed_goal, queue) -> None:
        """Depois de uma falha, se o novo plano não tem passos da meta, ela foi substituída."""
        if (failed_goal in self._goal_status and self._goal_status[failed_goal] == "pending"
                and not any(s.goal == failed_goal for s in queue)):
            self._goal_status[failed_goal] = "dropped"

    def _page_words(self) -> set[str]:
        try:
            text = self.page.inner_text("body")
        except Exception:
            return set()
        tokens = tokenize(text)
        return tokens | normalize_tokens(tokens)

    def _expected_missing(self, step: Step, words_before: set[str]) -> bool:
        """
        O texto esperado não apareceu depois do passo? (suspeita, não falha)
        Só conta o texto novo: o que já estava na página antes não confirma nada.
        """
        if not step.expect:
            return False
        want = normalize_tokens(tokenize(step.expect)) - STOPWORDS_N
        new = self._page_words() - words_before
        return bool(want) and len(want & new) / len(want) < 0.5

    def _finish(self, result: AgentResult, status: str, message: str, start: float) -> AgentResult:
        if status == "success" and self._pending_goals():
            status = "cancelled"
            message = "o planejador encerrou com metas pendentes: " + ", ".join(self._pending_goals())
        result.goals_done = sum(s == "done" for s in self._goal_status.values())
        result.status, result.message = status, message
        result.seconds = round(time.perf_counter() - start, 2)
        self.report(f"{'Concluído' if status == 'success' else 'Encerrado'}: {message}")
        return result

    # ------------------------------------------------------------------

    def _layer_count(self) -> int:
        """Quantos elementos estão num pop-up, diálogo ou menu aberto."""
        return sum(1 for r in self.executor.resolver.records if r.get("layer"))

    @staticmethod
    def _destructive(text: str) -> bool:
        tokens = tokenize(text or "")
        return bool((tokens | normalize_tokens(tokens)) & DESTRUCTIVE_N)

    def _unrequested_destructive(self, request: str, step: Step) -> bool:
        """
        O passo fecha, exclui, remove, oculta ou cancela algo que o pedido não mencionou?
        Fechar um pop-up (aviso, diálogo) não conta: é navegação, não descarte.
        """
        if step.action != "click" or self._destructive(request):
            return False
        description = clean_description(step.description)
        if not self._destructive(description):
            return False
        status, found, _ = self.executor._resolve(description, "click")
        return not (found is not None and found.layer)

    def _execute(self, step: Step, last_fill) -> ActionResult:
        """Executa um passo, com as redes de segurança do Enter e do campo a revelar."""
        description = clean_description(step.description)

        # Enter no lugar de um botão de busca que não existe.
        if self._is_submit(step) and last_fill is not None:
            status, found, _ = self.executor._resolve(description, "click")
            record = next((r for r in self.executor.resolver.records
                           if found is not None and r["id"] == found.id), None)
            if status != "success" or (record is not None and accepts(record, "fill")):
                try:
                    last_fill.locator.press("Enter")
                    self.report("    sem botão de busca: Enter no campo preenchido")
                    return ActionResult(status="success", action="press", description=step.description,
                                        selected_element=last_fill, resolved_by="enter_no_campo")
                except Exception as exc:
                    return ActionResult(status="error", action="press", description=step.description, error=str(exc))

        # Enter num elemento que não é campo de texto: vai para o último campo preenchido.
        if step.action == "press" and (step.value or "").lower() == "enter" and last_fill is not None:
            status, found, _ = self.executor._resolve(description, "click")
            record = next((r for r in self.executor.resolver.records
                           if found is not None and r["id"] == found.id), None)
            if status != "success" or record is None or not accepts(record, "fill"):
                try:
                    last_fill.locator.press("Enter")
                    return ActionResult(status="success", action="press", description=step.description,
                                        selected_element=last_fill, resolved_by="enter_no_campo")
                except Exception:
                    pass

        # Campo que só aparece depois de um clique (ex.: a lupa que abre a busca).
        if step.action == "fill":
            status, _, _ = self.executor._resolve(description, "fill")
            if status == "not_found":
                revealed = self._reveal_and_fill(step, description)
                if revealed is not None:
                    return revealed

        return run_step(self.executor, step)

    def _reveal_and_fill(self, step: Step, description: str) -> Optional[ActionResult]:
        status, trigger, _ = self.executor._resolve(description, "click")
        if status != "success" or trigger is None:
            return None
        try:
            trigger.click()
            self.page.wait_for_timeout(400)
        except Exception:
            return None
        self.report(f'    campo não encontrado: clicou em "{description}" para revelá-lo')

        status, target, _ = self.executor._resolve(description, "fill")
        if status != "success" or target is None:
            # O campo revelado costuma receber o foco (ex.: o campo de um pop-up de busca).
            focused = self.page.locator(":focus")
            try:
                editable = focused.count() == 1 and focused.evaluate(
                    "e => e.matches('input, textarea, [contenteditable=\"\"], [contenteditable=true]') && !e.readOnly")
                er_id = focused.get_attribute("data-er-id") if editable else None
            except Exception:
                return None
            record = next((r for r in self.executor.resolver.records if r["id"] == er_id), None)
            if record is None:
                return None
            target = self.executor.resolver.to_match(record)
        try:
            target.fill(step.value or "")
        except Exception as exc:
            return ActionResult(status="error", action="fill", description=step.description, error=str(exc))
        return ActionResult(status="success", action="fill", description=step.description,
                            selected_element=target, resolved_by="campo_revelado")

    def _verify(self, step: Step, outcome: ActionResult, before) -> tuple[str, list[str]]:
        """
        Confere o efeito de um passo que foi executado. Devolve (problema, mensagens):
        problema vazio = efeito ok; "no_effect" = nada aconteceu; outro texto = o motivo.
        """
        action = outcome.action if outcome.action in ("fill", "select", "check", "uncheck", "press") else step.action
        if action in ("hover", "extract_text"):
            return "", []
        effect = self.watcher.effect_since(before)
        errors = effect.errors
        others = [m for m in effect.new_messages if m not in errors]
        if errors:
            return f'apareceu a mensagem "{errors[0]}"', others
        element = outcome.selected_element
        if action in ("fill", "select", "check", "uncheck") and element is not None:
            return state_problem(action, clean_value(step.value), element.locator), others
        if action == "click" and element is not None:
            record = next((r for r in self.executor.resolver.records if r["id"] == element.id), None) or {}
            if accepts(record, "check"):
                # Clicar numa caixa ou opção muda o estado dela, não a estrutura da página.
                was = bool((element.state or {}).get("checked"))
                try:
                    now = element.locator.is_checked()
                except Exception:
                    return "", others
                return ("" if now != was or record.get("role") == "radio" and now else "no_effect"), others
            if accepts(record, "fill") or accepts(record, "select"):
                return "focus_only", others   # clicar num campo ou numa lista só dá o foco
        if action in ("click", "press") and not effect.changed:
            return "no_effect", others
        return "", others

    def _is_submit(self, step: Step) -> bool:
        return step.action == "click" and bool(tokenize(clean_description(step.description)) & SUBMIT_STEMS)

    def _replan(self, request, history, result, start, why):
        """Replaneja; devolve a nova fila, ou um AgentResult se não for possível."""
        self.report(f"  {why}; replanejando...")
        try:
            queue = list(self._plan(request, history, result).steps)
        except Exception as exc:  # plano inválido, conexão, modelo inexistente...
            return self._finish(result, "failed", f"falha ao replanejar: {exc}", start)
        result.replans += 1
        return queue

    def _fail(self, request, history, result, start, step, status, resolved_by, reason):
        """Registra uma falha e replaneja, ou cancela depois de max_failures."""
        if step.goal in self._goal_status and status != "loop":
            self._goal_status[step.goal] = "pending"
        result.failures += 1
        result.records.append(StepRecord(step, status, resolved_by, reason))
        history.append(f"falhou: {describe_step(step)} — {reason}")
        self.report(f"    falhou: {reason}")
        if result.failures >= self.max_failures:
            return self._finish(
                result, "cancelled",
                f"{self.max_failures} tentativas sem sucesso; último problema: "
                f"{describe_step(step)} — {reason}",
                start,
            )
        queue = self._replan(request, history, result, start,
                             f"Tentativa {result.failures + 1} de {self.max_failures}")
        if isinstance(queue, AgentResult):
            return queue
        self._supersede(step.goal, queue)
        if not queue:
            return self._finish(result, "cancelled",
                                f"o planejador não encontrou outro caminho depois de: {reason}", start)
        return queue

    def run(self, request: str) -> AgentResult:
        self._goals = {}
        self._goal_status = {}
        start = time.perf_counter()
        result = AgentResult(status="failed", message="")
        history: list[str] = []
        end_checks = 0
        done_count: dict[tuple, int] = {}
        last_done: Optional[tuple] = None   # último passo executado com sucesso
        after_replan = False                # a fila atual acabou de ser replanejada
        last_fill = None                    # elemento do último "fill", para o Enter
        blocked: set[tuple] = set()         # passos destrutivos barrados

        try:
            self.report("Planejando...")
            queue = list(self._plan(request, history, result).steps)
        except Exception as exc:  # plano inválido, conexão, modelo inexistente...
            return self._finish(result, "failed", f"não foi possível gerar o plano: {exc}", start)

        if not queue:
            return self._finish(result, "cancelled", "o pedido não pode ser feito nesta página", start)

        while True:
            # ---------------------------------------------------- fim do plano
            if not queue:
                if not self.verify_end:
                    return self._finish(result, "success", "todos os passos foram executados", start)
                if end_checks >= self.max_end_checks:
                    return self._finish(
                        result, "cancelled",
                        "a conferência do fim continuou encontrando passos; confira o resultado", start)
                end_checks += 1
                self.report("Conferindo se falta algo...")
                try:
                    queue = list(self._plan(request, history, result).steps)
                except Exception as exc:
                    return self._finish(result, "failed", f"falha ao conferir o fim: {exc}", start)
                # Passos já feitos que a conferência propõe de novo: o modelo não percebeu
                # que estavam feitos. Descarta; se não sobrar nada, o objetivo foi atingido.
                queue = [s for s in queue if step_key(s) not in done_count]
                if not queue:
                    return self._finish(result, "success", "objetivo atingido", start)
                result.replans += 1
                after_replan = True
                continue

            if len(result.records) >= self.max_steps:
                return self._finish(result, "failed", f"limite de {self.max_steps} passos atingido", start)

            step = queue.pop(0)
            key = step_key(step)

            # ---------------------------------------------------- laço
            repeated_now = after_replan and key == last_done
            if repeated_now or done_count.get(key, 0) >= self.max_repeats:
                reason = ("este passo acabou de ser executado com sucesso; não o repita"
                          if repeated_now else
                          f"este passo já foi executado {done_count[key]} vezes; o plano está repetindo")
                self.report(f"  ↺ {describe_step(step)}")
                after_replan = False
                outcome = self._fail(request, history, result, start, step, "loop", "", reason)
                if isinstance(outcome, AgentResult):
                    return outcome
                queue, after_replan = outcome, True
                continue
            after_replan = False

            # ---------------------------------------------------- ação destrutiva não pedida
            if self._unrequested_destructive(request, step):
                reason = "o pedido não pede para fechar, excluir, remover, ocultar ou cancelar; não inclua esse passo"
                self.report(f"  ✕ {describe_step(step)} (barrado: ação destrutiva não pedida)")
                if key in blocked:
                    outcome = self._fail(request, history, result, start, step, "blocked", "", reason)
                    if isinstance(outcome, AgentResult):
                        return outcome
                    queue, after_replan = outcome, True
                    continue
                blocked.add(key)
                if self._goal_status.get(step.goal) == "pending" and not any(
                        r.status == "success" and r.step.goal == step.goal for r in result.records):
                    self._goal_status[step.goal] = "dropped"   # meta que só tinha a ação barrada
                result.records.append(StepRecord(step, "blocked", "", reason))
                history.append(f"barrado: {describe_step(step)} — {reason}")
                continue

            url_before = self.page.url
            self.report(f"  → {describe_step(step)}")

            before = self.watcher.snapshot() if self.watcher else None
            words_before = self._page_words() if (self.watcher and step.expect) else set()
            outcome = self._execute(step, last_fill)

            if outcome.resolved_by == "user":
                result.interventions += 1

            # ---------------------------------------------------- verificação do efeito
            messages: list[str] = []
            focus_only = False
            if outcome.status == "success" and self.watcher is not None:
                problem, messages = self._verify(step, outcome, before)
                if problem == "no_effect":
                    self.report("    sem efeito visível; tentando mais uma vez")
                    before = self.watcher.snapshot()
                    outcome = self._execute(step, last_fill)
                    if outcome.status == "success":
                        problem, messages = self._verify(step, outcome, before)
                focus_only = problem == "focus_only"
                if focus_only:
                    problem = ""
                if outcome.status == "success" and problem:
                    history.extend(f'apareceu na página: "{m}"' for m in messages)
                    status = "no_effect" if problem == "no_effect" else "wrong_effect"
                    reason = "a ação não teve efeito visível na página" if problem == "no_effect" else problem
                    if outcome.resolved_by == "memory" and self.executor.memory is not None:
                        # A escolha memorizada não serve mais: esquece.
                        self.executor.memory.forget(url_before, outcome.action, clean_description(step.description))
                    result.no_effect += problem == "no_effect"
                    outcome_q = self._fail(request, history, result, start, step, status,
                                           outcome.resolved_by, reason)
                    if isinstance(outcome_q, AgentResult):
                        return outcome_q
                    queue, after_replan = outcome_q, True
                    continue

            # ---------------------------------------------------- sucesso
            if outcome.status == "success":
                result.records.append(StepRecord(step, "success", outcome.resolved_by))
                history.append(f"feito: {describe_step(step)}")
                history.extend(f'apareceu na página: "{m}"' for m in messages)
                if step.goal in self._goal_status and not (self.watcher is not None and focus_only):
                    # Um clique que só dá o foco não cumpre a meta.
                    self._goal_status[step.goal] = "done"
                if self.watcher is not None and self._expected_missing(step, words_before):
                    result.suspicions += 1
                    result.records[-1].note = f'esperava ver "{step.expect}", e não apareceu'
                    history.append(f'suspeita: depois de "{describe_step(step)}", esperava ver "{step.expect}", e não apareceu')
                done_count[key] = done_count.get(key, 0) + 1
                last_done = key
                if step.action == "fill" and outcome.selected_element is not None:
                    last_fill = outcome.selected_element

                layers_before = self._layer_count()
                if self.page.url != url_before:
                    self.page.wait_for_load_state()
                    why = "A página mudou"
                elif step.action == "fill":
                    # Sugestões que aparecem enquanto se digita são efeito normal da
                    # digitação: não justificam replanejar.
                    why = ""
                else:
                    self.executor.resolver.index("interactive")
                    layers_after = self._layer_count()
                    why = ("Abriu um pop-up" if layers_after > layers_before
                           else "Fechou um pop-up" if layers_after < layers_before
                           else "")
                if why:
                    queue = self._replan(request, history, result, start, why)
                    if isinstance(queue, AgentResult):
                        return queue
                    after_replan = True
                continue

            # ---------------------------------------------------- pulado pelo usuário
            if outcome.resolved_by == "user_skipped":
                result.records.append(StepRecord(step, "skipped", "user_skipped"))
                history.append(f"pulado pelo usuário: {describe_step(step)}")
                self.report("    pulado pelo usuário")
                continue

            # ---------------------------------------------------- falha
            outcome_q = self._fail(request, history, result, start, step,
                                   outcome.status, outcome.resolved_by, failure_reason(outcome))
            if isinstance(outcome_q, AgentResult):
                return outcome_q
            queue, after_replan = outcome_q, True
