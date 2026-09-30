"""
Avaliação de tarefas completas: pedido → plano (LLM) → execução → estado final.

Uso (na raiz do projeto):

    python -m eval.plan_run --referencia                     # planos escritos à mão (teto, sem LLM)
    python -m eval.plan_run --perfis ollama-pequeno          # um modelo
    python -m eval.plan_run --perfis ollama-pequeno ollama-medio openai -v
    python -m eval.plan_run --agente --perfis ollama-pequeno # tarefas pelo loop do agente completo
    python -m eval.plan_run --check                          # confere as tarefas, sem chamar modelos
    python -m eval.plan_run --final --perfis ...             # conjunto FECHADO (uma vez, no fim)

As tarefas de eval/plans/holdout_tasks.json (split "test") formam o conjunto
fechado: ficam fora de todas as execuções, a menos que --final seja usado.

Cada tarefa roda numa página nova. A execução não tem desempate: quando a
heurística recusa um passo, a tarefa para ali (mede o sistema sem ajuda humana).
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Optional

from playwright.sync_api import Page, sync_playwright

from anchor import __version__
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.element_resolver import ElementResolver
from anchor.planner import ConfigError, Plan, Step, get_profile, page_elements, run_plan
from anchor.planner.progress import Progress

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
TASKS = ROOT / "plans" / "tasks.json"
HOLDOUT_TASKS = ROOT / "plans" / "holdout_tasks.json"

# Registra cliques e Enter, e impede navegação (links e envio de formulários),
# para a página continuar aberta até as verificações.
INSTRUMENT = """
window.__er_log = [];
document.addEventListener("click", (e) => {
    window.__er_log.push({ type: "click", el: e.target });
    if (e.target.closest && e.target.closest("a[href]")) e.preventDefault();
}, true);
document.addEventListener("keydown", (e) => {
    if (e.key === "Enter") window.__er_log.push({ type: "enter", el: e.target });
}, true);
document.addEventListener("submit", (e) => e.preventDefault(), true);
for (const type of ["input", "change"]) {
    document.addEventListener(type, (e) => window.__er_log.push({ type, el: e.target }), true);
}
window.__clicked = (sel) => window.__er_log.some((x) => x.type === "click" && x.el.closest && x.el.closest(sel));
// Elementos com que o plano interagiu (clique, digitação, escolha) fora dos permitidos.
window.__unrequested = (allowed) => {
    const seen = new Set(), out = [];
    for (const { type, el } of window.__er_log) {
        if (type === "enter" || !el || !el.closest) continue;
        if (allowed.some((sel) => el.closest(sel))) continue;
        const target = el.closest("a, button, input, select, textarea, [role], [onclick]") || el;
        if (seen.has(target)) continue;
        seen.add(target);
        const name = (target.getAttribute("aria-label") || target.getAttribute("title")
            || target.innerText || target.value || target.id || target.tagName).trim().replace(/\\s+/g, " ");
        out.push(target.tagName.toLowerCase() + ' "' + name.slice(0, 40) + '"');
    }
    return out;
};
window.__entered = (sel) => window.__er_log.some((x) => x.type === "enter" && x.el.closest && x.el.closest(sel));
"""


class ReferencePlanner:
    """Devolve o plano de referência da tarefa (sem LLM)."""

    model = "referencia"

    def __init__(self):
        self.current: list = []

    def plan(self, request, url, page_elements=None, history=None, **_) -> Plan:
        # No modo --agente, um replanejamento devolve os passos de referência que faltam.
        done = sum(1 for h in (history or []) if h.startswith("feito:"))
        return Plan(steps=[Step(a, d, v) for a, d, v in self.current[done:]], model=self.model)


@dataclass
class TaskResult:
    perfil: str
    modelo: str
    tarefa: str
    split: str
    plano_valido: bool
    passos_plano: int
    passos_ok: int
    parou_em: str            # status do passo que falhou ("" se todos passaram)
    verificacoes_ok: int
    verificacoes: int
    sucesso: bool
    nao_pedidos: int          # elementos acionados que a tarefa não pedia
    nao_pedidos_lista: str
    limpa: bool               # sucesso E nenhum passo não pedido
    segundos: float
    tokens_entrada: int
    tokens_saida: int
    tentativas: int
    erro: str
    plano: str
    chamadas_llm: int = 0     # só no modo --agente (no modo plano, 1)
    replanejamentos: int = 0
    sem_efeito: int = 0       # modo --agente: ações que não tiveram efeito na página
    prematuro: bool = False   # modo --agente: declarou sucesso, mas as verificações falharam
    metas: int = 0            # modo --agente: metas definidas pelo planejador
    metas_cumpridas: int = 0
    suspeitas: int = 0        # modo --agente: textos esperados que não apareceram


def run_task_agent(page: Page, planner, profile_name: str, task: dict) -> TaskResult:
    """A tarefa executada pelo loop do agente (sem desempate humano)."""
    from anchor.agent import Agent

    page.goto((FIXTURES / task["fixture"]).as_uri())
    if isinstance(planner, ReferencePlanner):
        planner.current = task["reference"]
    result = Agent(page, planner, ActionExecutor(page, resolver=ElementResolver(page)), report=None).run(task["request"])

    checks = [bool(page.evaluate(f"() => Boolean({c})")) for c in task["checks"]]
    unrequested = page.evaluate("(allowed) => window.__unrequested(allowed)", task["allowed"])
    success = result.ok and all(checks)
    done = [r for r in result.records if r.status == "success"]
    stopped = next((r.status for r in reversed(result.records) if r.status != "success"), "")
    return TaskResult(
        perfil=profile_name, modelo=getattr(planner, "model", ""), tarefa=task["id"],
        split=task.get("split", "dev"),
        plano_valido=not result.message.startswith("não foi possível gerar o plano"),
        passos_plano=len(result.records), passos_ok=len(done), parou_em=stopped,
        verificacoes_ok=sum(checks), verificacoes=len(checks), sucesso=success,
        nao_pedidos=len(unrequested), nao_pedidos_lista="; ".join(unrequested),
        limpa=success and not unrequested,
        segundos=result.seconds, tokens_entrada=result.tokens_in, tokens_saida=result.tokens_out,
        tentativas=result.failures, erro="" if result.ok else result.message[:300],
        plano=json.dumps([[r.step.action, r.step.description, r.step.value] for r in result.records],
                         ensure_ascii=False),
        chamadas_llm=result.llm_calls, replanejamentos=result.replans,
        sem_efeito=result.no_effect, prematuro=result.ok and not all(checks),
        metas=result.goals_total, metas_cumpridas=result.goals_done, suspeitas=result.suspicions,
    )


def run_task(page: Page, planner, profile_name: str, task: dict, use_page: bool) -> TaskResult:
    page.goto((FIXTURES / task["fixture"]).as_uri())
    resolver = ElementResolver(page)
    elements = page_elements(resolver, request=task["request"]) if use_page else None

    if isinstance(planner, ReferencePlanner):
        planner.current = task["reference"]

    plan: Optional[Plan] = None
    error = ""
    try:
        plan = planner.plan(task["request"], page.url, elements)
    except Exception as exc:  # plano inválido, conexão, modelo inexistente...
        error = f"{type(exc).__name__}: {exc}"[:300]

    steps_ok, stopped = 0, ""
    if plan is not None:
        for _, result in run_plan(ActionExecutor(page, resolver=resolver), plan):
            if result.status == "success":
                steps_ok += 1
            else:
                stopped = result.status

    checks = [bool(page.evaluate(f"() => Boolean({c})")) for c in task["checks"]]
    unrequested = page.evaluate("(allowed) => window.__unrequested(allowed)", task["allowed"])
    success = plan is not None and all(checks)
    return TaskResult(
        perfil=profile_name,
        modelo=getattr(planner, "model", ""),
        tarefa=task["id"],
        split=task.get("split", "dev"),
        plano_valido=plan is not None,
        passos_plano=len(plan.steps) if plan else 0,
        passos_ok=steps_ok,
        parou_em=stopped,
        verificacoes_ok=sum(checks),
        verificacoes=len(checks),
        sucesso=success,
        nao_pedidos=len(unrequested),
        nao_pedidos_lista="; ".join(unrequested),
        limpa=success and not unrequested,
        segundos=plan.latency_s if plan else 0.0,
        tokens_entrada=plan.tokens_in if plan else 0,
        tokens_saida=plan.tokens_out if plan else 0,
        tentativas=plan.attempts if plan else 0,
        chamadas_llm=1 if plan is not None else 0,
        erro=error,
        plano=json.dumps([[s.action, s.description, s.value] for s in plan.steps], ensure_ascii=False)
        if plan else "",
    )


def warm_up(planner) -> float:
    """Carrega o modelo antes das tarefas, para o carregamento não entrar no tempo dos planos."""
    start = time.perf_counter()
    planner.client.chat.completions.create(
        model=planner.model,
        messages=[{"role": "user", "content": "Responda só com a palavra: ok"}],
        temperature=0,
    )
    return time.perf_counter() - start


def load_tasks() -> list[dict]:
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))["tasks"]
    if HOLDOUT_TASKS.exists():
        tasks += json.loads(HOLDOUT_TASKS.read_text(encoding="utf-8"))["tasks"]
    return tasks


REQUIRED = ("id", "fixture", "request", "checks", "allowed", "reference")


def check_tasks(tasks: list[dict], browser=None) -> int:
    """Confere a estrutura das tarefas sem chamar modelos nem a heurística."""
    if browser is None:
        with sync_playwright() as p:
            b = p.chromium.launch()
            try:
                return check_tasks(tasks, b)
            finally:
                b.close()

    from anchor.planner import ACTIONS

    problems = []
    ids = [t.get("id") for t in tasks]
    problems += [f"id repetido: {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for t in tasks:
        tid = t.get("id", "?")
        missing = [k for k in REQUIRED if not t.get(k)]
        if missing:
            problems.append(f"{tid}: faltam os campos {', '.join(missing)}")
            continue
        if not (FIXTURES / t["fixture"]).exists():
            problems.append(f"{tid}: página {t['fixture']} não existe em eval/fixtures")
            continue
        for a, d, v in t["reference"]:
            if a not in ACTIONS or (ACTIONS[a] and not v):
                problems.append(f"{tid}: passo de referência inválido: {a} {d!r} {v!r}")
        page = browser.new_page()
        page.add_init_script(INSTRUMENT)
        page.goto((FIXTURES / t["fixture"]).as_uri())
        for sel in t["allowed"]:
            if page.locator(sel).count() == 0:
                print(f"  [aviso] {tid}: {sel} não existe na página inicial (pode surgir depois)")
        for c in t["checks"]:
            try:
                page.evaluate(f"() => Boolean({c})")
            except Exception as exc:
                problems.append(f"{tid}: verificação com erro: {c} ({str(exc).splitlines()[0][:80]})")
        page.close()
    for msg in problems:
        print(f"  [PROBLEMA] {msg}")
    n_test = sum(t.get("split") == "test" for t in tasks)
    print(f"{len(tasks)} tarefas conferidas ({n_test} do conjunto fechado), {len(problems)} problema(s).")
    return 1 if problems else 0


def summarize(rows: list[TaskResult]) -> dict:
    n = len(rows)
    valid = [r for r in rows if r.plano_valido]
    return {
        "tarefas": n,
        "sucesso": sum(r.sucesso for r in rows) / n,
        "limpas": sum(r.limpa for r in rows) / n,
        "nao_pedidos": sum(r.nao_pedidos for r in rows),
        "plano_valido": len(valid) / n,
        "verificacoes": sum(r.verificacoes_ok for r in rows) / max(1, sum(r.verificacoes for r in rows)),
        "recusas_heuristica": sum(r.parou_em in ("ambiguous", "not_found") for r in rows),
        "segundos_medio": mean(r.segundos for r in valid) if valid else 0.0,
        "tokens_medio": mean(r.tokens_entrada + r.tokens_saida for r in valid) if valid else 0.0,
        "tentativas_medio": mean(r.tentativas for r in valid) if valid else 0.0,
        "chamadas_llm_medio": mean(r.chamadas_llm for r in rows),
        "replanejamentos": sum(r.replanejamentos for r in rows),
        "sem_efeito": sum(r.sem_efeito for r in rows),
        "prematuros": sum(r.prematuro for r in rows),
        "metas_cumpridas": (sum(r.metas_cumpridas for r in rows) / sum(r.metas for r in rows)
                            if sum(r.metas for r in rows) else None),
        "suspeitas": sum(r.suspeitas for r in rows),
    }


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "sem-git"


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.plan_run")
    ap.add_argument("--perfis", nargs="*", default=[], help="perfis de llm_profiles.json")
    ap.add_argument("--referencia", action="store_true", help="inclui os planos escritos à mão")
    ap.add_argument("--sem-pagina", action="store_true", help="não envia a lista de elementos ao modelo")
    ap.add_argument("--tarefa", help="roda só uma tarefa (id)")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--check", action="store_true", help="confere as tarefas, sem chamar modelos")
    ap.add_argument("--final", action="store_true", help="roda o conjunto FECHADO (split test)")
    ap.add_argument("--agente", action="store_true",
                    help="executa as tarefas pelo loop do agente (replanejamento e conferência do fim)")
    args = ap.parse_args()

    all_tasks = load_tasks()
    if args.check:
        return check_tasks(all_tasks)

    wanted = "test" if args.final else "dev"
    tasks = [t for t in all_tasks if t.get("split", "dev") == wanted]
    if args.final:
        print("*** CONJUNTO FECHADO: execução final. Registre a data e o commit desta rodada. ***")
        if not tasks:
            print("Nenhuma tarefa no conjunto fechado (eval/plans/holdout_tasks.json).")
            return 1
    if args.tarefa:
        tasks = [t for t in tasks if t["id"] == args.tarefa]

    planners = []
    progress = Progress()
    if args.referencia:
        planners.append(("referencia", ReferencePlanner()))
    for name in args.perfis:
        try:
            profile = get_profile(name)
            planners.append((name, profile.planner(on_progress=progress.update)))
        except ConfigError as exc:
            print(f"[{name}] {exc}")
            return 1
    if not planners:
        ap.error("informe --perfis e/ou --referencia")

    rows: list[TaskResult] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        warm = {}
        for name, planner in planners:
            print(f"\n=== {name} ({getattr(planner, 'model', '')})")
            is_llm = not isinstance(planner, ReferencePlanner)
            if is_llm:
                progress.prefix = "  carregando o modelo: "
                try:
                    with progress:
                        warm[name] = round(warm_up(planner), 1)
                except Exception as exc:
                    print(f"  não foi possível usar este perfil: {type(exc).__name__}: {exc}")
                    continue
                print(f"  modelo pronto em {warm[name]} s (fora do tempo dos planos)")
            for task in tasks:
                page = browser.new_page()
                page.set_default_timeout(5000)
                page.add_init_script(INSTRUMENT)
                progress.prefix = f"  ...   {task['id']:10} "
                def execute():
                    if args.agente:
                        return run_task_agent(page, planner, name, task)
                    return run_task(page, planner, name, task, use_page=not args.sem_pagina)

                if is_llm:
                    with progress:
                        r = execute()
                else:
                    r = execute()
                page.close()
                rows.append(r)
                mark = ("OK " if r.limpa else "OK+") if r.sucesso else ("ERR" if not r.plano_valido else "---")
                print(f"[{mark}] {r.tarefa:10} passos {r.passos_ok}/{r.passos_plano} "
                      f"verif. {r.verificacoes_ok}/{r.verificacoes} {r.segundos:5.1f}s"
                      + (f"  parou: {r.parou_em}" if r.parou_em else "")
                      + (f"  erro: {r.erro[:80]}" if r.erro else "")
                      + (f"  não pedido: {r.nao_pedidos_lista}" if r.nao_pedidos else "")
                      + ("  TÉRMINO PREMATURO" if r.prematuro else "")
                      + (f"  metas {r.metas_cumpridas}/{r.metas}" if r.metas else "")
                      + (f"  suspeitas: {r.suspeitas}" if r.suspeitas else "")
                      + (f"  sem efeito: {r.sem_efeito}" if r.sem_efeito else ""))
                if args.verbose and r.plano:
                    for a, d, v in json.loads(r.plano):
                        print(f"        {a:12} {d}" + (f' = "{v}"' if v is not None else ""))
        browser.close()

    print("\nCOMPARAÇÃO")
    print("(limpas = tarefas cumpridas sem nenhum passo não pedido; OK+ = cumprida, mas com passo a mais)")
    tempo = "seg/tarefa" if args.agente else "seg/plano"
    print(f"{'perfil':16} {'sucesso':>8} {'limpas':>7} {'não ped.':>9} {'plano ok':>9} {'verif.':>7} "
          f"{'recusas':>8} {tempo:>10} {'tokens':>7}"
          + (f" {'LLM/tar.':>9} {'replan.':>8} {'s/ efeito':>10} {'prematuro':>10} {'metas':>6} {'suspeitas':>10}"
             if args.agente else ""))
    summaries = {}
    for name, _ in planners:
        profile_rows = [r for r in rows if r.perfil == name]
        if not profile_rows:
            continue
        s = summarize(profile_rows)
        s["carregamento_s"] = warm.get(name)
        summaries[name] = s
        print(f"{name:16} {s['sucesso']:8.0%} {s['limpas']:7.0%} {s['nao_pedidos']:9} {s['plano_valido']:9.0%} {s['verificacoes']:7.0%} "
              f"{s['recusas_heuristica']:8} {s['segundos_medio']:10.1f} {s['tokens_medio']:7.0f}"
              + (f" {s['chamadas_llm_medio']:9.1f} {s['replanejamentos']:8} {s['sem_efeito']:10} {s['prematuros']:10}"
                 + (f" {s['metas_cumpridas']:6.0%}" if s["metas_cumpridas"] is not None else f" {'—':>6}")
                 + f" {s['suspeitas']:10}" if args.agente else ""))

    if not rows:
        print("Nenhuma tarefa foi executada.")
        return 1

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    stem = f"planos_{datetime.now():%Y%m%d-%H%M%S}_{git_commit()}" + ("_FINAL" if args.final else "")
    with open(out / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0])))
        w.writeheader()
        w.writerows(asdict(r) for r in rows)
    (out / f"{stem}.json").write_text(json.dumps({
        "versao": __version__, "commit": git_commit(), "data": datetime.now().isoformat(timespec="seconds"),
        "contexto_da_pagina": not args.sem_pagina, "modo": "agente" if args.agente else "plano",
        "resumo": summaries,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResultados salvos em {(out / stem).relative_to(ROOT.parent)}.csv (+ .json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
