"""
Avaliação do ElementResolver + validação do Executor (Peça 10).

Para cada caso (página + consulta + elemento esperado), mede:

    - em que posição o elemento certo ficou no ranking;
    - o que o Executor decidiria (success / ambiguous / not_found);
    - se a falha foi de percepção (alvo nem indexado) ou de ranqueamento.

Uso (na raiz do projeto):

    python -m eval.run                  # todos os casos
    python -m eval.run --split dev      # só os casos de desenvolvimento
    python -m eval.run --offline        # pula sites reais
    python -m eval.run --site loja -v   # um site, mostrando cada caso
    python -m eval.run --sweep          # varre score mínimo × gap
    python -m eval.run --check          # só confere os seletores esperados (inclui o holdout)
    python -m eval.run --final          # roda o HOLDOUT (split "test"). Uma vez, no fim.

O split "test" é o conjunto fechado (holdout): fica fora de todas as
execuções, a menos que --final seja usado. Não olhe esses resultados
durante o desenvolvimento.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from anchor import __version__
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.action_executor.constants import (
    DEFAULT_AMBIGUITY_GAP,
    DEFAULT_MIN_SCORE,
    RESOLVER_ACTION_MAP,
)
from anchor.engine.element_resolver import ElementResolver
from eval.setups import SETUPS

ROOT = Path(__file__).resolve().parent
KS = (1, 3, 5, 10)
MAX_K = max(KS)


@dataclass
class CaseResult:
    suite: str
    case_id: str
    split: str
    action: str
    query: str
    status: str               # decisão do Executor
    rank: int | None          # posição do alvo (1 = primeiro); None = fora do top-10
    target_indexed: bool      # o alvo estava entre os elementos indexados?
    outcome: str              # ver classify()
    top1_score: float
    runner_up_score: float
    target_score: float | None
    top1_is_target: bool
    top1_desc: str
    n_indexed: int
    ms: float


# ----------------------------------------------------------------------
# Carregamento
# ----------------------------------------------------------------------

def check_selectors(suites: list[dict]) -> None:
    """Confere se cada seletor esperado encontra elemento(s). Não calcula scores."""
    problems = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for suite in suites:
            page = browser.new_page()
            open_suite(page, suite)
            for case in suite["cases"]:
                n = page.locator(case["expected"]).count()
                if n == 0:
                    problems += 1
                    print(f"  [SEM ALVO] {case['id']}: {case['expected']}")
                elif n > 1:
                    print(f"  [aviso] {case['id']}: seletor casa com {n} elementos (todos aceitos)")
            page.close()
        browser.close()
    total = sum(len(s["cases"]) for s in suites)
    print(f"{total} casos conferidos, {problems} com seletor quebrado.")


def load_suites(site: str | None, offline: bool) -> list[dict]:
    suites = []
    for path in sorted((ROOT / "cases").glob("*.json")):
        suite = json.loads(path.read_text(encoding="utf-8"))
        if site and suite["site"] != site:
            continue
        if offline and suite.get("requires_network"):
            continue
        suites.append(suite)
    return suites


def open_suite(page: Page, suite: dict) -> None:
    if "fixture" in suite:
        page.goto((ROOT / "fixtures" / suite["fixture"]).as_uri())
    else:
        page.goto(suite["url"])
    if suite.get("setup"):
        SETUPS[suite["setup"]](page)


def target_ids(page: Page, selector: str) -> tuple[int, set[str]]:
    """Quantos elementos o seletor esperado encontra e quais foram indexados."""
    ids = page.locator(selector).evaluate_all(
        "els => els.map(e => e.getAttribute('data-er-id'))"
    )
    return len(ids), {i for i in ids if i}


# ----------------------------------------------------------------------
# Avaliação de um caso
# ----------------------------------------------------------------------

def classify(status: str, rank: int | None, indexed: bool) -> str:
    """
    acerto            Executor decidiu e escolheu o alvo.
    erro_silencioso   Executor decidiu, mas escolheu o elemento ERRADO (o pior caso).
    recusa_evitavel   Alvo estava em 1º, mas o Executor recusou (limiar conservador demais).
    recusa_correta    Executor recusou e o 1º não era o alvo (evitou um erro).
    falha_percepcao   O alvo nem foi indexado pelo script.
    """
    if not indexed:
        return "falha_percepcao"
    if status == "success":
        return "acerto" if rank == 1 else "erro_silencioso"
    return "recusa_evitavel" if rank == 1 else "recusa_correta"


def run_case(page: Page, suite: dict, case: dict) -> CaseResult:
    resolver = ElementResolver(page, synonyms=suite.get("synonyms"))
    executor = ActionExecutor(page, resolver=resolver, k=MAX_K)
    resolver_action = RESOLVER_ACTION_MAP.get(case["action"], case["action"])

    t0 = time.perf_counter()
    status, _, matches = executor._resolve(case["query"], resolver_action)
    ms = (time.perf_counter() - t0) * 1000
    matches = matches or []

    n_expected, expected = target_ids(page, case["expected"])
    if n_expected == 0:
        raise ValueError(f"{case['id']}: seletor esperado não encontra nada: {case['expected']}")

    rank = next((i for i, m in enumerate(matches, 1) if m.id in expected), None)
    target = matches[rank - 1] if rank else None
    top1 = matches[0] if matches else None

    return CaseResult(
        suite=suite["site"],
        case_id=case["id"],
        split=case.get("split", "dev"),
        action=case["action"],
        query=case["query"],
        status=status,
        rank=rank,
        target_indexed=bool(expected),
        outcome=classify(status, rank, bool(expected)),
        top1_score=round(top1.score, 4) if top1 else 0.0,
        runner_up_score=round(matches[1].score, 4) if len(matches) > 1 else 0.0,
        target_score=round(target.score, 4) if target else None,
        top1_is_target=rank == 1,
        top1_desc=(f"{top1.role} '{top1.text or top1.label or top1.hint}'"[:60] if top1 else ""),
        n_indexed=len(resolver._records),
        ms=round(ms, 1),
    )


# ----------------------------------------------------------------------
# Métricas
# ----------------------------------------------------------------------

def summarize(results: list[CaseResult]) -> dict:
    n = len(results)
    if n == 0:
        return {"n": 0}
    s = {"n": n}
    for k in KS:
        s[f"recall@{k}"] = sum(r.rank is not None and r.rank <= k for r in results) / n
    s["mrr"] = sum(1 / r.rank for r in results if r.rank) / n
    for outcome in ("acerto", "erro_silencioso", "recusa_evitavel", "recusa_correta", "falha_percepcao"):
        s[outcome] = sum(r.outcome == outcome for r in results) / n
    s["ms_medio"] = sum(r.ms for r in results) / n
    return s


def sweep(results: list[CaseResult]) -> list[dict]:
    """Simula o Executor com outros limiares, usando os scores já calculados."""
    rows = []
    for min_score in (0.15, 0.20, 0.30, 0.40, 0.50, 0.60):
        for gap in (0.02, 0.04, 0.06, 0.08, 0.12, 0.16, 0.20, 0.30):
            ok = err = refused = 0
            for r in results:
                # Mesma regra do Executor: gap relativo ao score do 1º.
                margin = (r.top1_score - r.runner_up_score) / r.top1_score if r.top1_score else 0.0
                decided = r.top1_score >= min_score and margin >= gap
                if not decided:
                    refused += 1
                elif r.top1_is_target:
                    ok += 1
                else:
                    err += 1
            n = len(results)
            rows.append({"min_score": min_score, "gap": gap,
                         "acerto": ok / n, "erro_silencioso": err / n, "recusa": refused / n})
    return rows


# ----------------------------------------------------------------------
# Saída
# ----------------------------------------------------------------------

def pct(x: float) -> str:
    return f"{x * 100:5.1f}%"


def print_summary(title: str, s: dict) -> None:
    if not s["n"]:
        return
    print(f"\n{title}  (n={s['n']})")
    print(f"  recall@1 {pct(s['recall@1'])}   @3 {pct(s['recall@3'])}   "
          f"@5 {pct(s['recall@5'])}   @10 {pct(s['recall@10'])}   MRR {s['mrr']:.3f}")
    print(f"  Executor: acerto {pct(s['acerto'])} | erro silencioso {pct(s['erro_silencioso'])} | "
          f"recusa evitável {pct(s['recusa_evitavel'])} | recusa correta {pct(s['recusa_correta'])} | "
          f"falha de percepção {pct(s['falha_percepcao'])}")
    print(f"  tempo médio por consulta: {s['ms_medio']:.0f} ms")


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "sem-git"


def save(results: list[CaseResult], summary: dict, args) -> Path:
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    tag = "_FINAL" if args.final else ""
    stem = f"{datetime.now():%Y%m%d-%H%M%S}_{git_commit()}{tag}"
    with open(out / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(results[0])))
        w.writeheader()
        w.writerows(asdict(r) for r in results)
    meta = {
        "versao": __version__,
        "commit": git_commit(),
        "data": datetime.now().isoformat(timespec="seconds"),
        "filtros": {"split": args.split, "site": args.site, "offline": args.offline},
        "limiares": {"min_score": DEFAULT_MIN_SCORE, "gap": DEFAULT_AMBIGUITY_GAP},
        "geral": summary,
    }
    (out / f"{stem}.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return out / f"{stem}.csv"


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Avaliação do Resolver")
    ap.add_argument("--split", choices=["dev", "test"])
    ap.add_argument("--site")
    ap.add_argument("--offline", action="store_true", help="pula casos que exigem internet")
    ap.add_argument("--sweep", action="store_true", help="varre score mínimo × gap")
    ap.add_argument("-v", "--verbose", action="store_true", help="mostra cada caso")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--check", action="store_true", help="só confere os seletores esperados")
    ap.add_argument("--final", action="store_true", help="roda o holdout (split test)")
    args = ap.parse_args()

    if args.check:
        check_selectors(load_suites(args.site, args.offline))
        return

    if args.split == "test" and not args.final:
        ap.error('o split "test" é o holdout; use --final (uma vez, no fim do desenvolvimento)')
    if args.final:
        args.split = "test"
        print("*** HOLDOUT: execução final. Registre a data e o commit desta rodada. ***")

    results: list[CaseResult] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        for suite in load_suites(args.site, args.offline):
            page = browser.new_page()
            open_suite(page, suite)
            for case in suite["cases"]:
                split = case.get("split", "dev")
                if args.split and split != args.split:
                    continue
                if not args.split and split == "test":
                    continue  # holdout fica fora por padrão
                r = run_case(page, suite, case)
                results.append(r)
                if args.verbose:
                    mark = {"acerto": "OK ", "erro_silencioso": "ERR", "falha_percepcao": "PER"}.get(r.outcome, "REC")
                    print(f"[{mark}] {r.case_id:9} rank={str(r.rank):4} {r.status:9} "
                          f"top1={r.top1_score:.2f} 2º={r.runner_up_score:.2f}  "
                          f"{r.query!r} → {r.top1_desc}")
            page.close()
        browser.close()

    if not results:
        print("Nenhum caso selecionado.")
        return

    summary = summarize(results)
    print_summary("GERAL", summary)

    by = defaultdict(list)
    for r in results:
        by[f"site: {r.suite}"].append(r)
        by[f"ação: {r.action}"].append(r)
    for key in sorted(by):
        print_summary(key, summarize(by[key]))

    if args.sweep:
        print("\nVARREDURA DE LIMIARES (menor erro silencioso primeiro, depois maior acerto)")
        print("  min_score   gap (relativo)   acerto   erro silencioso   recusa")
        rows = sorted(sweep(results), key=lambda x: (x["erro_silencioso"], -x["acerto"]))
        for row in rows[:12]:
            print(f"    {row['min_score']:.2f}     {row['gap']:.2f}   {pct(row['acerto'])}      "
                  f"{pct(row['erro_silencioso'])}       {pct(row['recusa'])}")

    path = save(results, summary, args)
    print(f"\nResultados salvos em {path.relative_to(ROOT.parent)} (+ .json com o resumo)")


if __name__ == "__main__":
    main()
