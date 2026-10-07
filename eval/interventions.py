"""
Interventions experiment: does the system ask the user less as it learns?

    python -m eval.interventions --offline -v
    python -m eval.interventions                    # includes SauceDemo (internet)

The resolver's development cases (both languages) are run by the Executor with the choice
memory and a simulated user, an "oracle" that knows the right element of each case: when
asked, it picks the right candidate if it is among the numbered ones, or clicks the right
element on the page otherwise. Each question counts as an intervention.

    round 1: the memory starts empty; the cases in order
    round 2: the same cases, with the memory of round 1
    round 3: the same cases in a shuffled order (fixed seed), with the memory so far

Per round: interventions, right actions, silent errors (the system acted on the wrong element
without asking), and right actions that came from the memory. Each case reopens its page, so
one case does not affect the next; clicks are run as hovers, which the resolver treats the
same way, so that a link does not leave the page. Whether the chosen element is the right one
is checked right before acting, since an action may re-render the page.

The oracle never makes a mistake: this measures the best case of a user. LLM-free.
"""

from __future__ import annotations

import argparse
import json
import random
import tempfile
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from anchor import __version__
from anchor.cli import option
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.element_resolver import ElementResolver
from anchor.engine.element_resolver.match import Match
from anchor.engine.memory import ChoiceMemory
from eval.run import load_suites, open_suite, target_ids

ROOT = Path(__file__).resolve().parent

# How each case's action is run: a click becomes a hover (same resolution, no navigation).
_RUN = {
    "click": lambda ex, q: ex.hover(q),
    "fill": lambda ex, q: ex.fill(q, "teste"),
    "select": lambda ex, q: ex.select(q, index=1),
    "check": lambda ex, q: ex.check(q),
    "extract_text": lambda ex, q: ex.extract_text(q),
}

_POINT_JS = """(e) => {
    if (!e.hasAttribute("data-er-id")) e.setAttribute("data-er-id", "el-oracle-" + Date.now());
    const r = e.getBoundingClientRect();
    return {id: e.getAttribute("data-er-id"), tag: e.tagName.toLowerCase(), role: e.getAttribute("role") || "",
            label: e.getAttribute("aria-label") || "", text: (e.innerText || e.value || "").trim().slice(0, 120),
            rect: {x: r.x, y: r.y, width: r.width, height: r.height}};
}"""


class _NoInterface:
    """The oracle never goes through an interface: nothing is shown."""

    def choose(self, request):
        raise AssertionError("the oracle answers directly")

    def notify(self, message):
        pass


class OracleExecutor(ActionExecutor):
    """An Executor whose user is an oracle that knows the right element (the case's selector)."""

    def __init__(self, page: Page, expected: str, **kwargs):
        super().__init__(page, disambiguator=_NoInterface(), can_point=True, **kwargs)
        self.expected = expected
        self.asked = 0          # interventions
        self.pointed = 0        # of them, how many needed a click on the page
        self.chosen_right = None   # whether the element about to be acted on is the right one

    def _denied(self, action_name, description, match, resolved_by="memory"):
        # Called right before acting, on every path (memory, heuristic, user): check the choice
        # here, because the action may re-render the page and lose the elements' ids (SauceDemo
        # redraws the whole list when sorting).
        _, right = target_ids(self.page, self.expected)
        self.chosen_right = match.id in right
        return super()._denied(action_name, description, match, resolved_by)

    def _ask_user(self, description, action_name, reason, candidates):
        self.asked += 1
        shown = self._choices_to_show(reason, candidates)
        _, right = target_ids(self.page, self.expected)
        for match in shown:
            if match.id in right:
                return match
        # The right element is not among the numbered ones: the user clicks it on the page.
        self.pointed += 1
        target = self.page.locator(self.expected).first
        if target.count() == 0:
            return None
        info = target.evaluate(_POINT_JS)
        captured = Match(id=info["id"], tag=info["tag"], role=info["role"], label=info["label"], text=info["text"],
                         content="", context="", rect=info["rect"], score=0.0, page=self.page)
        return self._enrich_captured(captured, action_name)


def run_case(page: Page, suite: dict, case: dict, memory: ChoiceMemory) -> dict:
    open_suite(page, suite)
    executor = OracleExecutor(page, case["expected"], resolver=ElementResolver(page, synonyms=suite.get("synonyms")),
                              memory=memory)
    result = _RUN[case["action"]](executor, case["query"])
    chosen = result.selected_element
    if executor.chosen_right is not None:
        right = executor.chosen_right                 # checked before acting
    else:
        _, right_ids = target_ids(page, case["expected"])
        right = chosen is not None and chosen.id in right_ids
    return {
        "case": case["id"], "suite": suite["site"], "language": suite.get("language", "pt"),
        "action": case["action"], "query": case["query"],
        "asked": executor.asked > 0, "pointed": executor.pointed > 0,
        "from_memory": result.resolved_by == "memory", "right": right,
        "silent_error": executor.asked == 0 and chosen is not None and not right,
        "status": result.status, "resolved_by": result.resolved_by,
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows) or 1
    return {
        "cases": len(rows),
        "interventions": sum(r["asked"] for r in rows),
        "intervention_rate": sum(r["asked"] for r in rows) / n,
        "right": sum(r["right"] for r in rows) / n,
        "silent_errors": sum(r["silent_error"] for r in rows) / n,
        "from_memory": sum(r["from_memory"] for r in rows) / n,
        "pointed": sum(r["pointed"] for r in rows),
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.interventions")
    ap.add_argument("--offline", action="store_true", help="skips the cases that need the internet")
    option(ap, "--language", choices=("pt", "en"), help="only the cases in this language (default: both)")
    option(ap, "--rounds", type=int, default=3, help="rounds over the cases (default: 3)")
    option(ap, "--seed", type=int, default=7, help="seed of the shuffled order of round 3 on")
    ap.add_argument("-v", "--verbose", action="store_true", help="shows each case of each round")
    args = ap.parse_args()

    suites = load_suites(None, args.offline, args.language)
    cases = [(suite, case) for suite in suites for case in suite["cases"] if case.get("split", "dev") == "dev"]
    rows: list[dict] = []
    with tempfile.TemporaryDirectory() as folder, sync_playwright() as p:
        memory = ChoiceMemory(Path(folder) / "memory.json")         # starts empty
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(5000)
        for round_number in range(1, args.rounds + 1):
            order = list(cases)
            if round_number >= 3:
                random.Random(args.seed + round_number).shuffle(order)
            print(f"\n=== Round {round_number} ({'shuffled' if round_number >= 3 else 'in order'}, "
                  f"{len(memory.entries)} remembered choices)")
            for suite, case in order:
                row = run_case(page, suite, case, memory)
                row["round"] = round_number
                rows.append(row)
                if args.verbose:
                    mark = "SIL" if row["silent_error"] else ("ASK" if row["asked"] else
                                                               ("MEM" if row["from_memory"] else ("OK " if row["right"] else "---")))
                    print(f"  [{mark}] {row['case']:12} {row['query'][:60]}")
        browser.close()

    print("\nINTERVENTIONS PER ROUND")
    print(f"{'round':>5} {'language':>9} {'cases':>6} {'asked':>6} {'asked %':>8} {'right':>7} {'silent':>7} {'memory':>7}")
    summaries = {}
    languages = sorted({r["language"] for r in rows})
    for round_number in range(1, args.rounds + 1):
        for language in languages:
            part = [r for r in rows if r["round"] == round_number and r["language"] == language]
            s = summarize(part)
            summaries[f"round {round_number} [{language}]"] = s
            print(f"{round_number:5} {language:>9} {s['cases']:6} {s['interventions']:6} {s['intervention_rate']:8.1%} "
                  f"{s['right']:7.1%} {s['silent_errors']:7.1%} {s['from_memory']:7.1%}")

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    path = out / f"interventions_{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps({"version": __version__, "date": datetime.now().isoformat(timespec="seconds"),
                                "offline": args.offline, "rounds": args.rounds, "seed": args.seed,
                                "summary": summaries, "cases": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved to {path.relative_to(ROOT.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
