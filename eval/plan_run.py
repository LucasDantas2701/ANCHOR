"""
Avaliação de tarefas completas: pedido → plano (LLM) → execução → estado final.

Uso (na raiz do projeto):

    python -m eval.plan_run --referencia                     # planos escritos à mão (teto, sem LLM)
    python -m eval.plan_run --perfis ollama-pequeno          # um modelo
    python -m eval.plan_run --perfis ollama-pequeno ollama-medio openai -v

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

from app import __version__
from app.engine.action_executor import ActionExecutor
from app.engine.element_resolver import ElementResolver
from app.planner import ConfigError, Plan, Step, get_profile, page_elements, run_plan
from app.planner.progress import Progress

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
TASKS = ROOT / "plans" / "tasks.json"

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
window.__clicked = (sel) => window.__er_log.some((x) => x.type === "click" && x.el.closest && x.el.closest(sel));
window.__entered = (sel) => window.__er_log.some((x) => x.type === "enter" && x.el.closest && x.el.closest(sel));
"""


class ReferencePlanner:
    """Devolve o plano de referência da tarefa (sem LLM)."""

    model = "referencia"

    def __init__(self):
        self.current: list = []

    def plan(self, request, url, page_elements=None) -> Plan:
        return Plan(steps=[Step(a, d, v) for a, d, v in self.current], model=self.model)


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
    segundos: float
    tokens_entrada: int
    tokens_saida: int
    tentativas: int
    erro: str
    plano: str


def run_task(page: Page, planner, profile_name: str, task: dict, use_page: bool) -> TaskResult:
    page.goto((FIXTURES / task["fixture"]).as_uri())
    resolver = ElementResolver(page)
    elements = page_elements(resolver) if use_page else None

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
        sucesso=plan is not None and all(checks),
        segundos=plan.latency_s if plan else 0.0,
        tokens_entrada=plan.tokens_in if plan else 0,
        tokens_saida=plan.tokens_out if plan else 0,
        tentativas=plan.attempts if plan else 0,
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


def summarize(rows: list[TaskResult]) -> dict:
    n = len(rows)
    valid = [r for r in rows if r.plano_valido]
    return {
        "tarefas": n,
        "sucesso": sum(r.sucesso for r in rows) / n,
        "plano_valido": len(valid) / n,
        "verificacoes": sum(r.verificacoes_ok for r in rows) / max(1, sum(r.verificacoes for r in rows)),
        "recusas_heuristica": sum(r.parou_em in ("ambiguous", "not_found") for r in rows),
        "segundos_medio": mean(r.segundos for r in valid) if valid else 0.0,
        "tokens_medio": mean(r.tokens_entrada + r.tokens_saida for r in valid) if valid else 0.0,
        "tentativas_medio": mean(r.tentativas for r in valid) if valid else 0.0,
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
    args = ap.parse_args()

    tasks = json.loads(TASKS.read_text(encoding="utf-8"))["tasks"]
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
                if is_llm:
                    with progress:
                        r = run_task(page, planner, name, task, use_page=not args.sem_pagina)
                else:
                    r = run_task(page, planner, name, task, use_page=not args.sem_pagina)
                page.close()
                rows.append(r)
                mark = "OK " if r.sucesso else ("ERR" if not r.plano_valido else "---")
                print(f"[{mark}] {r.tarefa:10} passos {r.passos_ok}/{r.passos_plano} "
                      f"verif. {r.verificacoes_ok}/{r.verificacoes} {r.segundos:5.1f}s"
                      + (f"  parou: {r.parou_em}" if r.parou_em else "")
                      + (f"  erro: {r.erro[:80]}" if r.erro else ""))
                if args.verbose and r.plano:
                    for a, d, v in json.loads(r.plano):
                        print(f"        {a:12} {d}" + (f' = "{v}"' if v is not None else ""))
        browser.close()

    print("\nCOMPARAÇÃO")
    print(f"{'perfil':16} {'sucesso':>8} {'plano ok':>9} {'verif.':>7} {'recusas':>8} {'seg/plano':>10} {'tokens':>7}")
    summaries = {}
    for name, _ in planners:
        profile_rows = [r for r in rows if r.perfil == name]
        if not profile_rows:
            continue
        s = summarize(profile_rows)
        s["carregamento_s"] = warm.get(name)
        summaries[name] = s
        print(f"{name:16} {s['sucesso']:8.0%} {s['plano_valido']:9.0%} {s['verificacoes']:7.0%} "
              f"{s['recusas_heuristica']:8} {s['segundos_medio']:10.1f} {s['tokens_medio']:7.0f}")

    if not rows:
        print("Nenhuma tarefa foi executada.")
        return 1

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    stem = f"planos_{datetime.now():%Y%m%d-%H%M%S}_{git_commit()}"
    with open(out / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0])))
        w.writeheader()
        w.writerows(asdict(r) for r in rows)
    (out / f"{stem}.json").write_text(json.dumps({
        "versao": __version__, "commit": git_commit(), "data": datetime.now().isoformat(timespec="seconds"),
        "contexto_da_pagina": not args.sem_pagina, "resumo": summaries,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResultados salvos em {(out / stem).relative_to(ROOT.parent)}.csv (+ .json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
