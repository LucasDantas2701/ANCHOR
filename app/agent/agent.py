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
from app.planner import Plan, Step, page_elements, run_step


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
        report: Optional[Callable[[str], None]] = print,
    ):
        self.page = page
        self.planner = planner
        self.executor = executor
        self.max_failures = max_failures
        self.max_steps = max_steps
        self.verify_end = verify_end
        self.report = report or (lambda _: None)

    # ------------------------------------------------------------------

    def _plan(self, request: str, history: list[str], result: AgentResult) -> Plan:
        elements = page_elements(self.executor.resolver)
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

    def run(self, request: str) -> AgentResult:
        start = time.perf_counter()
        result = AgentResult(status="failed", message="")
        history: list[str] = []
        verified_end = False

        try:
            self.report("Planejando...")
            queue = list(self._plan(request, history, result).steps)
        except Exception as exc:  # plano inválido, conexão, modelo inexistente...
            return self._finish(result, "failed", f"não foi possível gerar o plano: {exc}", start)

        if not queue:
            return self._finish(result, "cancelled", "o pedido não pode ser feito nesta página", start)

        while True:
            if not queue:
                if not self.verify_end or verified_end:
                    return self._finish(result, "success", "todos os passos foram executados", start)
                self.report("Conferindo se falta algo...")
                try:
                    queue = list(self._plan(request, history, result).steps)
                except Exception as exc:
                    return self._finish(result, "failed", f"falha ao conferir o fim: {exc}", start)
                verified_end = True
                if not queue:
                    return self._finish(result, "success", "objetivo atingido", start)
                result.replans += 1
                continue

            if len(result.records) >= self.max_steps:
                return self._finish(result, "failed", f"limite de {self.max_steps} passos atingido", start)

            step = queue.pop(0)
            url_before = self.page.url
            self.report(f"  → {describe_step(step)}")
            outcome = run_step(self.executor, step)

            if outcome.resolved_by == "user":
                result.interventions += 1

            if outcome.status == "success":
                result.records.append(StepRecord(step, "success", outcome.resolved_by))
                history.append(f"feito: {describe_step(step)}")
                verified_end = False

                if self.page.url != url_before:
                    self.page.wait_for_load_state()
                    self.report("  A página mudou; replanejando...")
                    try:
                        queue = list(self._plan(request, history, result).steps)
                    except Exception as exc:
                        return self._finish(result, "failed", f"falha ao replanejar: {exc}", start)
                    result.replans += 1
                continue

            if outcome.resolved_by == "user_skipped":
                result.records.append(StepRecord(step, "skipped", "user_skipped"))
                history.append(f"pulado pelo usuário: {describe_step(step)}")
                self.report("    pulado pelo usuário")
                continue

            reason = failure_reason(outcome)
            result.failures += 1
            result.records.append(StepRecord(step, outcome.status, outcome.resolved_by, reason))
            history.append(f"falhou: {describe_step(step)} — {reason}")
            self.report(f"    falhou: {reason}")

            if result.failures >= self.max_failures:
                return self._finish(
                    result, "cancelled",
                    f"{self.max_failures} tentativas sem sucesso; último problema: "
                    f"{describe_step(step)} — {reason}",
                    start,
                )

            self.report(f"  Replanejando (tentativa {result.failures + 1} de {self.max_failures})...")
            try:
                queue = list(self._plan(request, history, result).steps)
            except Exception as exc:
                return self._finish(result, "failed", f"falha ao replanejar: {exc}", start)
            result.replans += 1
            if not queue:
                return self._finish(
                    result, "cancelled",
                    f"o planejador não encontrou outro caminho depois de: {reason}", start,
                )
