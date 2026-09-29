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
from app.engine.element_resolver.tokenizer import DESTRUCTIVE_N, normalize_tokens, tokenize
from app.planner import Plan, Step, page_elements, run_step
from app.planner.execute import clean_description

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
        self.report = report or (lambda _: None)

    # ------------------------------------------------------------------

    def _plan(self, request: str, history: list[str], result: AgentResult) -> Plan:
        elements = page_elements(self.executor.resolver, request=request)
        plan = self.planner.plan(request, self.page.url, elements, history or None)
        result.llm_calls += 1
        result.tokens_in += plan.tokens_in
        result.tokens_out += plan.tokens_out
        return plan

    def _finish(self, result: AgentResult, status: str, message: str, start: float) -> AgentResult:
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
        if not queue:
            return self._finish(result, "cancelled",
                                f"o planejador não encontrou outro caminho depois de: {reason}", start)
        return queue

    def run(self, request: str) -> AgentResult:
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
                result.records.append(StepRecord(step, "blocked", "", reason))
                history.append(f"barrado: {describe_step(step)} — {reason}")
                continue

            url_before = self.page.url
            self.report(f"  → {describe_step(step)}")

            # ---------------------------------------------------- Enter no lugar do botão de busca
            if self._is_submit(step) and last_fill is not None:
                status, found, _ = self.executor._resolve(clean_description(step.description), "click")
                # Sem botão: nada encontrado, ou o "botão" encontrado é o próprio campo de texto.
                record = next((r for r in self.executor.resolver.records
                               if found is not None and r["id"] == found.id), None)
                is_field = record is not None and accepts(record, "fill")
                if status != "success" or is_field:
                    try:
                        last_fill.locator.press("Enter")
                        outcome = ActionResult(status="success", action="press", description=step.description,
                                               selected_element=last_fill, resolved_by="enter_no_campo")
                        self.report("    sem botão de busca: Enter no campo preenchido")
                    except Exception as exc:
                        outcome = ActionResult(status="error", action="press", description=step.description,
                                               error=str(exc))
                else:
                    outcome = run_step(self.executor, step)
            else:
                outcome = run_step(self.executor, step)

            if outcome.resolved_by == "user":
                result.interventions += 1

            # ---------------------------------------------------- sucesso
            if outcome.status == "success":
                result.records.append(StepRecord(step, "success", outcome.resolved_by))
                history.append(f"feito: {describe_step(step)}")
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
