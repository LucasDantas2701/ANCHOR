"""
The article's tables and figures, computed from the result files of the final run.

    python -m eval.paper_tables --final                        # the newest *_FINAL files, all of one commit
    python -m eval.paper_tables --resilience F [F ...] --plans F [F ...] --resolver F --out DIR

Writes, in --out (default eval/paper/):
  fig2_fig3_resilience.csv   success and false success by level, executor and model; the main combinations
                             (level 0 and those that reach the reference plan), the off-path ones apart, and
                             the total of all the combinations
  mcnemar_resilience.csv     McNemar's exact test, ANCHOR against each other system, paired task by task
  mcnemar_requests.csv       the same on the request sets, by set and model
  table4_by_pages.csv        the request sets split into known pages (used in development, or made from one)
                             and new pages
  safety_level5.csv          attacks that worked and attempts at level 5, by executor and model
  repetitions_resilience.csv each repetition of a repeated executor (llm_plan in the final run), and the
                             combinations where its repetitions disagree (only when there are repetitions)
  stop_rate.tex/csv          the runs that ended asking a person, by system and model (decided on 19/11/2026)
  human_by_person.tex/csv    the human set's measures with the bootstrap by page and by person, side by side
  table4_closed_sets.tex/csv the closed request sets by set (possible and impossible requests apart, decided
                             on 19/11/2026), executor and model: success, false success,
                             runs without unrequested steps (every task: both executors can read)
  table4_without_readings    a breakdown: the same without the tasks whose answer key expects readings
  readings_apart.csv         a breakdown: only those tasks, both executors
  sensitivity.tex/csv        the synthetic set without t-ord-a1 and t-ord-c1; the controlled set without ChatGPT
  synthetic_breakdown.csv    the synthetic set by language and by feasible / infeasible request
  table5_people_vs_ai.tex/csv  controlled (all, without ChatGPT) against human (all, IT, non-IT)
  table6_failures.tex/csv    failed runs by cause and executor (the rule in failure_cause)
  table7_elements.tex/csv    element selection: recall@1/3/5/10, MRR, time per query and the five decisions
  sources.txt                the files read and their commits

Uncertainty (--ci, decided on 19/11/2026, before the final run): bootstrap, the default (clustered by page in the
request sets and by base task in the resilience benchmark; 10,000 draws, seed 7), with the 95% Wilson interval
where a rate is 0% or 100% (the bootstrap interval has no width there), marked in every CSV (a "ci" column with
"bootstrap" or "wilson") and with a dagger in the LaTeX tables; wilson for every rate; or none. The McNemar
tests give the exact p-value and Holm's adjustment within each family of comparisons (a set and a model in the
requests; a part and a model in the resilience benchmark).

It reads result files only (and, for the infeasible mark, the task definitions' "expected" field), and
writes and prints no request text. Test it only with development results, never with closed ones.
"""
from __future__ import annotations

import argparse
import csv
import glob
import math
import random
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"

# Sensitivity analyses (decided before the final run; base técnica)
COPIED_FROM_INSTRUCTIONS = ("t-ord-a1", "t-ord-c1")     # synthetic set, registered on 23/10/2026
WITHOUT_GENERATOR = "chatgpt"                          # synthetic controlled set, decided on 22/10/2026

# ---------------------------------------------------------------------------------------------------------
# Uncertainty: the clustered bootstrap (decided on 19/11/2026), with Wilson where the rate is 0% or 100%
# ---------------------------------------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float] | None:
    """Wilson score interval for k successes in n trials (95% by default)."""
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 7          # fixed: the same files always give the same intervals (decided on 13/11/2026)


def bootstrap(outcomes: list[bool], clusters: list[str], samples: int = BOOTSTRAP_SAMPLES,
              seed: int = BOOTSTRAP_SEED) -> tuple[float, float] | None:
    """Clustered (cluster) bootstrap, 95% percentile interval: whole clusters are drawn with replacement (a
    base task in the resilience benchmark, a page in the request sets), so runs that share one are not
    counted as independent. Same seed, same interval."""
    if not outcomes:
        return None
    groups = defaultdict(lambda: [0, 0])
    for ok, cluster in zip(outcomes, clusters):
        groups[cluster][0] += bool(ok)
        groups[cluster][1] += 1
    sums = list(groups.values())
    rng = random.Random(seed)
    rates = []
    for _ in range(samples):
        drawn = [sums[rng.randrange(len(sums))] for _ in sums]
        n = sum(d[1] for d in drawn)
        rates.append(sum(d[0] for d in drawn) / n)
    rates.sort()
    return rates[int(0.025 * samples)], rates[min(samples - 1, int(0.975 * samples))]


INTERVALS = {"wilson": wilson, "bootstrap": None, "none": lambda k, n: None}


class Rate:
    """k of n, with its interval from the chosen method (the clustered bootstrap needs each run's outcome and
    cluster; with none given it falls back to one cluster per run)."""
    method = "bootstrap"

    def __init__(self, k: int, n: int, outcomes: list[bool] | None = None, clusters: list[str] | None = None):
        self.k, self.n = k, n
        self.ci_method = Rate.method if n and Rate.method != "none" else ""
        if Rate.method == "bootstrap" and n and 0 < k < n:
            outcomes = outcomes if outcomes is not None else [True] * k + [False] * (n - k)
            clusters = clusters if clusters is not None else [str(i) for i in range(len(outcomes))]
            self.ci = bootstrap(outcomes, clusters)
        elif Rate.method == "bootstrap" and n:
            # 0% or 100%: every bootstrap draw gives the same rate, so its interval has no width; the 95% Wilson
            # interval instead, marked (decided on 19/11/2026)
            self.ci, self.ci_method = wilson(k, n), "wilson"
        else:
            self.ci = INTERVALS[Rate.method](k, n)

    @classmethod
    def of(cls, outcomes: list[bool], clusters: list[str]) -> "Rate":
        return cls(sum(bool(o) for o in outcomes), len(outcomes), outcomes, clusters)

    @property
    def rate(self) -> float | None:
        return self.k / self.n if self.n else None

    @property
    def fallback(self) -> bool:
        """The interval is Wilson's in place of the bootstrap's (a rate of 0% or 100%)."""
        return Rate.method == "bootstrap" and self.ci_method == "wilson"

    def csv(self) -> list:
        lo, hi = self.ci if self.ci else ("", "")
        return [self.k, self.n, _pct(self.rate), _pct(lo), _pct(hi), self.ci_method]

    def tex(self) -> str:
        if not self.n:
            return "--"
        text = f"{100 * self.rate:.1f}"
        if self.ci:
            text += f" ({100 * self.ci[0]:.1f}--{100 * self.ci[1]:.1f})" + (DAGGER if self.fallback else "")
        return text


DAGGER = "\u2020"     # in a LaTeX cell, write_tex turns it into \textsuperscript{\dag}


def _pct(x) -> str:
    return "" if x is None or x == "" else f"{100 * x:.1f}"


# ---------------------------------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------------------------------


def read_rows(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        for row in csv.DictReader(open(path, encoding="utf-8")):
            row["_file"] = path.name
            rows.append(row)
    return rows


def commit_of(path: Path) -> str:
    """The commit in a result file's name (plans_<date>_<commit>..., resilience_..., <date>_<commit>...)."""
    m = re.search(r"\d{8}-\d{6}_([0-9a-f]{7,40}(?:\+dirty)?)", path.name)
    return m.group(1) if m else "?"


def true(value) -> bool:
    return str(value) == "True"


def newest(pattern: str, exclude: tuple[str, ...] = ()) -> list[Path]:
    found = sorted(p for p in map(Path, glob.glob(str(RESULTS / pattern))) if not p.name.startswith(exclude))
    return found


# ---------------------------------------------------------------------------------------------------------
# Known and new pages (decided on 13/11/2026): a page is known when it, or the page it was made from, was used
# in development (by a development task or resolver case); else it is new. The nine pages of the human
# collection are made from earlier pages: six have the same visible text, three the same structure (they are
# translated), as checked on 13/11/2026.
# ---------------------------------------------------------------------------------------------------------

COLLECTION_ORIGIN = {
    "collection/cadastro.html": "registration.html", "collection/pedidos.html": "orders.html",
    "collection/usuarios.html": "users.html", "collection/vagas.html": "jobs.html", "collection/loja.html": "store.html",
    "collection/reservas.html": "holdout_booking.html", "collection/suporte.html": "holdout_helpdesk.html",
    "collection/blog.html": "holdout_blog.html", "collection/rh.html": "holdout_hr.html",
}
_TASKS: dict | None = None


def task_index() -> dict:
    """Each task's id -> its fixture, base task, whether the request is impossible and, for the human set, the
    person (their answer's row in the sheet, anonymous), from the task definitions (only those fields)."""
    global _TASKS
    if _TASKS is None:
        import json
        _TASKS = {}
        try:
            from eval.plan_run import load_tasks
            for t in load_tasks():
                _TASKS[t["id"]] = {"fixture": t.get("fixture", ""), "base": t.get("base_task", ""),
                                   "impossible": t.get("expected") == "not_possible",
                                   "person": f"row{t['response_row']}" if t.get("response_row") is not None else ""}
        except Exception:
            pass
        for name in ("resilience_tasks.json", "resilience_closed_tasks.json"):
            path = ROOT / "plans" / name
            if path.exists():
                for t in json.loads(path.read_text(encoding="utf-8"))["tasks"]:
                    _TASKS[t["id"]] = {"fixture": t.get("fixture", ""), "base": t.get("base_task", "")}
    return _TASKS


def development_pages() -> set[str]:
    import json
    pages = set()
    try:
        from eval.plan_run import load_tasks
        pages |= {t["fixture"] for t in load_tasks() if t.get("split", "dev") == "dev"}
    except Exception:
        pass
    for path in (ROOT / "cases").glob("*.json"):
        if path.name.startswith("holdout"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("fixture"):
            pages.add(data["fixture"])
    return pages


def page_kind(fixture: str, known: set[str]) -> str:
    origin = COLLECTION_ORIGIN.get(fixture, fixture)
    if origin.startswith(("resilience/", "resilience_closed/")):
        return "known"                       # every resilience page is a development page, perturbed or not
    return "known" if origin in known else "new"


def cluster_of(row: dict) -> str:
    """The bootstrap's cluster: the base task in the resilience benchmark, the page in the request sets."""
    if row.get("base_task"):
        return row["base_task"]
    info = task_index().get(row.get("task", ""), {})
    return COLLECTION_ORIGIN.get(info.get("fixture", ""), info.get("fixture", "")) or row.get("task", "")


def person_of(row: dict) -> str:
    """The bootstrap's cluster by person, in the human set (decided on 19/11/2026): the answer the request came
    from; elsewhere, or when unknown, the page's cluster."""
    return task_index().get(row.get("task", ""), {}).get("person") or cluster_of(row)


def impossible(row: dict) -> bool:
    return bool(task_index().get(row.get("task", ""), {}).get("impossible"))


def claimed(row: dict) -> bool:
    """Whether the run said the task was done. The request runner records it through its other columns, exactly:
    a false success ("premature") is a claim on an impossible request or with a failed check, so a claim is a
    false success, or a success on a possible request. The resilience benchmark records it as claimed_success."""
    if "claimed_success" in row:
        return true(row["claimed_success"])
    return true(row.get("premature")) or (true(row.get("success")) and not impossible(row))


# The stops that, in real use, turn into a question to the person (decided on 19/11/2026): the element was not
# found or was ambiguous (the person picks it, or points at it), a password is needed (the person logs in), or a
# confirmation was denied (the person's answer). During a measurement no one answers, so the run stops there.
ASKS_A_PERSON = {"not_found", "ambiguous", "credential", "denied"}


def last_stop(row: dict) -> str:
    """The status of the run's last step that did not succeed ("" when every step succeeded)."""
    if "stopped_at" in row:
        return row.get("stopped_at") or ""
    import json
    try:
        steps = json.loads(row.get("steps") or "[]")
    except ValueError:
        return ""
    return next((step[3] for step in reversed(steps) if len(step) > 3 and step[3] != "success"), "")


def stopped_for_a_person(row: dict) -> bool:
    """The run ended asking a person: it did not say the task was done, and its last stop asks one."""
    return not claimed(row) and last_stop(row) in ASKS_A_PERSON


def asks(executor: str) -> bool:
    """Only ANCHOR and its variants ask a person; the scripts and the model in control never do."""
    return executor.startswith("anchor")


def stop_rate_table(plan_rows: list[dict], resilience_rows: list[dict]) -> list[list]:
    out = [["source", "set_or_part", "executor", "model", "stopped_k", "n", "stopped_%", "lo", "hi", "ci"]]
    groups = defaultdict(list)
    for r in plan_rows:
        if asks(plans_executor(r)):
            groups[("Requests", request_set(r), plans_executor(r), r["profile"])].append(r)
    for r in resilience_rows:
        if asks(r["executor"]):
            groups[("Resilience", "all", resilience_executor(r), r.get("profile") or "")].append(r)
    for (source, part, ex, model), g in sorted(groups.items(), key=lambda kv: (kv[0][0] != "Requests",) + group_order(
            ((kv[0][1], kv[0][2], kv[0][3]), None))):
        rate = Rate.of([stopped_for_a_person(r) for r in g], [cluster_of(r) for r in g])
        out.append([source, SET_NAMES.get(part, part), EXECUTOR_NAMES.get(ex, ex), model_name(model)] + rate.csv())
    return out


def interval_cell(pct, lo, hi, ci) -> str:
    """A CSV rate and its interval as a LaTeX cell, with the dagger when the interval is Wilson's in place of the
    bootstrap's."""
    if pct in ("", None):
        return "--"
    if lo in ("", None):
        return f"{pct}"
    return f"{pct} ({lo}--{hi})" + (DAGGER if Rate.method == "bootstrap" and ci == "wilson" else "")


def human_by_person_table(rows: list[dict]) -> list[list]:
    """The human set's three measures, by executor, model and profile (all, IT, non-IT), each with the bootstrap by
    page and by person (decided on 19/11/2026)."""
    head = ["executor", "model", "profile", "n", "people"]
    for m in ("success", "false_success", "clean"):
        head += [f"{m}_%", f"{m}_lo_page", f"{m}_hi_page", f"{m}_ci_page", f"{m}_lo_person", f"{m}_hi_person",
                 f"{m}_ci_person"]
    out = [head]
    human = [r for r in rows if r.get("origin") == "human"]
    groups = defaultdict(list)
    for r in human:
        for profile in ("all", r.get("generator") or ""):
            if profile:
                groups[(plans_executor(r), r["profile"], profile)].append(r)
    for (ex, model, profile), g in sorted(groups.items(), key=lambda kv: (kv[0][0], model_name(kv[0][1]),
                                                                          ("all", "it", "non_it").index(kv[0][2])
                                                                          if kv[0][2] in ("all", "it", "non_it") else 9)):
        line = [EXECUTOR_NAMES.get(ex, ex), model_name(model), PROFILE_NAMES.get(profile, profile), len(g),
                len({person_of(r) for r in g})]
        for f in ("success", "premature", "clean"):
            outcomes = [true(r[f]) for r in g]
            by_page, by_person = Rate.of(outcomes, [cluster_of(r) for r in g]), Rate.of(outcomes, [person_of(r) for r in g])
            line += by_page.csv()[2:6] + by_person.csv()[3:6]
        out.append(line)
    return out


PROFILE_NAMES = {"all": "All", "it": "IT", "non_it": "Non-IT"}


# ---------------------------------------------------------------------------------------------------------
# Figures 2 and 3: resilience
# ---------------------------------------------------------------------------------------------------------

MODEL_NAMES = {"ollama-small": "4B", "ollama-medium": "9B"}
SHORT_EXECUTOR = {"anchor": "ANCHOR", "llm": "LLM", "llm_plan": "LLM+plan", "anchor_noverify": "No check",
                  "anchor_modelpick": "Model picks", "anchor_nosafety": "No barriers"}
ACTION_NAMES = {"all": "All", "click": "click", "fill": "type", "select": "select", "check": "check",
                "uncheck": "uncheck", "hover": "hover", "press": "press a key", "extract_text": "read text",
                "extract_table": "read table", "download": "download", "upload": "upload"}


def model_name(profile: str) -> str:
    return MODEL_NAMES.get(profile, profile) if profile else "-"


EXECUTOR_NAMES = {"script": "Fixed selectors", "roles": "Role and text locators", "llm": "LLM in control",
                  "llm_plan": "LLM in control, with the plan", "anchor": "ANCHOR",
                  "anchor_noverify": "ANCHOR without the effect check", "anchor_modelpick": "ANCHOR, element chosen by the model",
                  "anchor1": "ANCHOR, 1st run", "anchor2": "ANCHOR, 2nd run (no model call)",
                  "anchor_noverify1": "ANCHOR without the effect check, 1st run",
                  "anchor_noverify2": "ANCHOR without the effect check, 2nd run (no model call)",
                  "anchor_modelpick1": "ANCHOR, element chosen by the model, 1st run",
                  "anchor_modelpick2": "ANCHOR, element chosen by the model, 2nd run (no model call)",
                  "anchor_nosafety": "ANCHOR without the safety barriers",
                  "anchor_nosafety1": "ANCHOR without the safety barriers, 1st run",
                  "anchor_nosafety2": "ANCHOR without the safety barriers, 2nd run (no model call)"}


def resilience_executor(row: dict) -> str:
    """ANCHOR and its ablations have two runs each (the 1st recovers, the 2nd reuses): anchor1, anchor2..."""
    if row["executor"].startswith("anchor"):
        return row["executor"] + ("1" if row["run"] == "1" else "2")
    return row["executor"]


def resilience_success(row: dict) -> bool:
    """The 2nd ANCHOR run counts as a success only when done again with no model call (as the report does)."""
    if resilience_executor(row).startswith("anchor") and resilience_executor(row).endswith("2"):
        return true(row["success"]) and row.get("llm_calls") in ("0", "")
    return true(row["success"])


def resilience_part(row: dict) -> str:
    """main: level 0 and the combinations that reach the reference plan; off_path: the others. Development
    files have no mark (reaches_plan is empty): every row counts as main there."""
    return "off_path" if row.get("reaches_plan") == "no" else "main"


# ---------------------------------------------------------------------------------------------------------
# Repetitions (decided on 18/11/2026, before the final run): an executor whose two development runs differed
# (only llm_plan) runs three times. Each combination counts once, by majority: a success (or a false success)
# in at least two of the three repetitions; a level-5 attack that worked in any of them counts as one. So the
# executor has as many combinations as the others in every rate, interval and McNemar test, and each
# repetition is reported apart (repetitions_resilience.csv).
# ---------------------------------------------------------------------------------------------------------

def repetition_of(row: dict) -> int:
    return int(row.get("repetition") or 1)


def collapse_repetitions(rows: list[dict]) -> tuple[list[dict], list[list]]:
    """The rows with each repeated combination made one (by majority), and the per-repetition report."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["executor"], r.get("profile") or "", r["task"], r.get("language", ""), r["run"])].append(r)
    repeated = {k[:2] for k, g in groups.items() if len({repetition_of(r) for r in g}) > 1}
    if not repeated:
        return rows, []
    out, report = [], [["executor", "model", "repetition", "success_k", "false_success_k", "n"]]
    disagree = defaultdict(int)
    for key, g in groups.items():
        if key[:2] not in repeated:
            out += g
            continue
        reps = sorted({repetition_of(r) for r in g})
        if reps != [1, 2, 3] or len(g) != 3:
            raise SystemExit(f"{key[0]} {key[1]} {key[2]}: repetitions {reps} ({len(g)} rows); expected 1, 2 and 3 once each")
        g = sorted(g, key=repetition_of)
        one = dict(g[0])
        wins = sum(true(r["success"]) for r in g)
        one["success"] = str(wins >= 2)
        one["false_success"] = str(sum(true(r.get("false_success")) for r in g) >= 2)
        one["attacked"] = str(any(true(r.get("attacked")) for r in g))
        one["attack_attempts"] = str(max(int(r.get("attack_attempts") or 0) for r in g))
        one["_repetitions"] = "".join("1" if true(r["success"]) else "0" for r in g)
        out.append(one)
        if 0 < wins < 3:
            disagree[key[:2]] += 1
    by = defaultdict(list)
    for key, g in groups.items():
        if key[:2] in repeated:
            for r in g:
                by[key[:2] + (repetition_of(r),)].append(r)
    for (ex, model, rep), g in sorted(by.items()):
        report.append([EXECUTOR_NAMES.get(ex, ex), model_name(model), rep, sum(true(r["success"]) for r in g),
                       sum(true(r.get("false_success")) for r in g), len(g)])
    report.append([])
    report.append(["executor", "model", "combinations where the repetitions disagree"])
    for ex, model in sorted(repeated):
        report.append([EXECUTOR_NAMES.get(ex, ex), model_name(model), disagree[(ex, model)]])
    return out, report


def fig2_fig3(rows: list[dict]) -> tuple[list[list], list[list]]:
    groups = defaultdict(list)
    for r in rows:
        key = (resilience_executor(r), r.get("profile") or "", int(r["level"]))
        groups[(resilience_part(r),) + key].append(r)
        groups[("all",) + key].append(r)              # the total of the 150 combinations, besides the parts
    table = [["part", "executor", "model", "level", "success_k", "n", "success_%", "success_lo", "success_hi",
              "success_ci", "false_success_k", "n", "false_success_%", "false_lo", "false_hi", "false_ci"]]
    for (part, ex, model, level), g in sorted(groups.items()):
        table.append([part, EXECUTOR_NAMES[ex], model_name(model), level]
                     + Rate.of([resilience_success(r) for r in g], [cluster_of(r) for r in g]).csv()
                     + Rate.of([true(r.get("false_success")) for r in g], [cluster_of(r) for r in g]).csv())
    safety = [["executor", "model", "level5_runs", "attacked_runs", "attack_attempts"]]
    by = defaultdict(list)
    for r in rows:
        if int(r["level"]) == 5:
            by[(resilience_executor(r), r.get("profile") or "")].append(r)
    for (ex, model), g in sorted(by.items()):
        safety.append([EXECUTOR_NAMES[ex], model_name(model), len(g), sum(true(r.get("attacked")) for r in g),
                       sum(int(r.get("attack_attempts") or 0) for r in g)])
    return table, safety


# ---------------------------------------------------------------------------------------------------------
# Tables 4, 5 and 6: the closed request sets
# ---------------------------------------------------------------------------------------------------------

SET_NAMES = {"synthetic": "Synthetic", "synthetic_controlled": "Synthetic controlled", "human": "Human",
             "development": "Development"}


def request_set(row: dict) -> str:
    if row.get("split", "dev") != "test":
        return "development"
    return row.get("origin") or "synthetic"


def plans_executor(row: dict) -> str:
    """Files from before --executor have no column: their runs are ANCHOR's (or the model in control's,
    when the file name says _llm)."""
    return row.get("executor") or ("llm" if "_llm" in row["_file"] else "anchor")


def reads(row: dict) -> bool:
    return true(row.get("reads"))


def measures(rows: list[dict]) -> list[Rate]:
    clusters = [cluster_of(r) for r in rows]
    return [Rate.of([true(r[f]) for r in rows], clusters) for f in ("success", "premature", "clean")]


def comparable(rows: list[dict], anchor_too: bool = False) -> list[dict]:
    """Every task is compared directly since the model in control can read (decided on 13/11/2026); with
    anchor_too, the breakdown without the tasks whose answer key expects readings, for both executors."""
    return [r for r in rows if not (anchor_too and reads(r))]


def by_set_executor_model(rows: list[dict], label=request_set) -> dict:
    groups = defaultdict(list)
    for r in rows:
        groups[(label(r), plans_executor(r), r["profile"])].append(r)
    return groups


def measure_table(groups: dict, set_names: dict) -> list[list]:
    out = [["set", "executor", "model", "success_k", "n", "success_%", "lo", "hi", "ci", "false_success_k", "n",
            "false_success_%", "lo", "hi", "ci", "clean_k", "n", "clean_%", "lo", "hi", "ci"]]
    for (s, ex, model), g in sorted(groups.items(), key=group_order):
        out.append([set_names.get(s, s), EXECUTOR_NAMES.get(ex, ex), model_name(model)] + sum((m.csv() for m in measures(g)), []))
    return out


SET_ORDER = ["synthetic", "synthetic_controlled", "human", "development"]


def group_order(item) -> tuple:
    """Sets in the article's order (possible requests before impossible ones), then ANCHOR before the LLM in
    control, then 4B before 9B."""
    (s, ex, model), _ = item
    base, _, kind = str(s).partition("|")
    return (SET_ORDER.index(base) if base in SET_ORDER else len(SET_ORDER), base, kind != "possible", kind, ex,
            model_name(model))


KIND_NAMES = {"possible": "possible", "impossible": "impossible"}


def by_kind(groups: dict) -> dict:
    """Table 4's groups with the possible and the impossible requests apart (decided on 19/11/2026)."""
    out = defaultdict(list)
    for (s, ex, model), g in groups.items():
        for r in g:
            out[(f"{s}|{'impossible' if impossible(r) else 'possible'}", ex, model)].append(r)
    return out


def kind_names(set_names: dict, groups: dict) -> dict:
    return {key[0]: f"{set_names.get(key[0].split('|')[0], key[0].split('|')[0])}, {KIND_NAMES[key[0].split('|')[1]]}"
            for key in groups}


def failure_cause(row: dict) -> str:
    """Table 6 (the rule decided by the author before the final run; base técnica): for a failed run, by
    code and in this order, the cause of its stop: a safety stop (a step blocked by a barrier or a denied
    confirmation); element resolution (the element was not found, or was ambiguous); effect verification
    (a step had no effect, or the wrong one); planning (no failing step: the plan was invalid, the model
    called a feasible request impossible, the request's coverage failed, or every step succeeded but the
    checks did not hold); other (any other stop: an action error, a missing file, a login page...).
    A perception failure is not recorded in a task run; it is reported in Table 7 only."""
    stop = row.get("stopped_at") or ""
    if stop in ("blocked", "changed", "denied", "credential"):
        return "safety stop"
    if stop in ("not_found", "ambiguous"):
        return "element resolution"
    if stop in ("no_effect", "wrong_effect"):
        return "effect verification"
    if not stop or not true(row.get("plan_valid", "True")):
        return "planning"
    return "other"


CAUSES = ["safety stop", "element resolution", "effect verification", "planning", "other"]


def table6(rows: list[dict]) -> list[list]:
    failed = [r for r in rows if not true(r["success"])]
    columns = sorted({(plans_executor(r), r["profile"]) for r in rows}, key=lambda c: (c[0], model_name(c[1])))
    out = [["Cause"] + [f"{SHORT_EXECUTOR.get(e, e)} {model_name(m)}" for e, m in columns]]
    for cause in CAUSES:
        out.append([cause.capitalize()] + [sum(1 for r in failed if failure_cause(r) == cause and (plans_executor(r), r["profile"]) == c)
                              for c in columns])
    out.append(["Of which false success"] + [sum(1 for r in failed if true(r["premature"])
                                                        and (plans_executor(r), r["profile"]) == c) for c in columns])
    out.append(["Failed runs"] + [sum(1 for r in failed if (plans_executor(r), r["profile"]) == c) for c in columns])
    out.append(["Runs"] + [sum(1 for r in rows if (plans_executor(r), r["profile"]) == c) for c in columns])
    return out


def infeasible_ids() -> set[str]:
    """Task ids whose answer key expects the request to be impossible (only that field is read)."""
    try:
        from eval.plan_run import load_tasks
        return {t["id"] for t in load_tasks() if t.get("expected") == "not_possible"}
    except Exception:
        return set()


# ---------------------------------------------------------------------------------------------------------
# Paired comparisons: McNemar's exact test between ANCHOR and each other system (decided on 13/11/2026)
# ---------------------------------------------------------------------------------------------------------


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value: b and c are the discordant pairs (only one of the two succeeded)."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def holm(p_values: list[float]) -> list[float]:
    """Holm's step-down adjustment of the p-values of one family of tests (same order as given)."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted, running = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def with_holm(family: list[list]) -> list[list]:
    """The family's lines with the exact p-value formatted and Holm's adjusted one after it (decided on
    19/11/2026: a family is the comparisons of ANCHOR with every other system in one set, or part, and model)."""
    adjusted = holm([line[-1] for line in family])
    return [line[:-1] + [f"{line[-1]:.4g}", f"{a:.4g}"] for line, a in zip(family, adjusted)]


def paired(success: dict, anchor_key, other_key, label: str, model: str) -> list | None:
    """success maps (system, task) to True or False; pairs are the tasks both systems ran."""
    tasks = sorted({t for (s, t) in success if s == anchor_key} & {t for (s, t) in success if s == other_key})
    if not tasks:
        return None
    b = sum(1 for t in tasks if success[(anchor_key, t)] and not success[(other_key, t)])
    c = sum(1 for t in tasks if not success[(anchor_key, t)] and success[(other_key, t)])
    return [label, model_name(model), len(tasks), b, c, mcnemar_exact(b, c)]


MCNEMAR_HEADER = ["comparison", "model", "pairs", "ANCHOR_only", "other_only", "p_exact", "p_holm"]


def mcnemar_requests(rows: list[dict]) -> list[list]:
    out = [["set"] + MCNEMAR_HEADER]
    for s in sorted({request_set(r) for r in rows}, key=lambda x: SET_ORDER.index(x) if x in SET_ORDER else 99):
        for model in sorted({r["profile"] for r in rows}, key=model_name):
            success = {(plans_executor(r), r["task"]): true(r["success"]) for r in rows
                       if request_set(r) == s and r["profile"] == model}
            family = []
            for other in sorted({e for e, _ in success} - {"anchor"}):
                line = paired(success, "anchor", other, f"ANCHOR vs {EXECUTOR_NAMES.get(other, other)}", model)
                if line:
                    family.append(line)
            out += [[SET_NAMES.get(s, s)] + line for line in with_holm(family)]
    return out


def mcnemar_resilience(rows: list[dict]) -> list[list]:
    """ANCHOR's first run against each other system, per model; a system with no model (a script) is paired
    with each model's ANCHOR runs. All 150 combinations, and the subset that reaches the plan."""
    out = [["part"] + MCNEMAR_HEADER]
    for part in ("all", "main"):
        chosen = [r for r in rows if part == "all" or resilience_part(r) == "main"]
        for model in sorted({r.get("profile") for r in chosen if r.get("profile")}, key=model_name):
            success = {}
            for r in chosen:
                ex = resilience_executor(r)
                if r.get("profile") in (model, "", None) and not (ex.startswith("anchor") and ex.endswith("2")):
                    success[(ex, r["task"])] = resilience_success(r)
            family = []
            for other in sorted({e for e, _ in success} - {"anchor1"}):
                line = paired(success, "anchor1", other, f"ANCHOR vs {EXECUTOR_NAMES.get(other, other)}", model)
                if line:
                    family.append(line)
            out += [[part] + line for line in with_holm(family)]
    return out


# ---------------------------------------------------------------------------------------------------------
# Table 7: element selection
# ---------------------------------------------------------------------------------------------------------

DECISIONS = ["correct", "silent_error", "avoidable_refusal", "correct_refusal", "perception_failure"]


def table7(rows: list[dict]) -> list[list]:
    """The closed cases (split test) when the file has them, else the development ones (for testing)."""
    closed = [r for r in rows if r.get("split") == "test"]
    rows = closed or rows
    groups = {"all": rows}
    for action in sorted({r["action"] for r in rows}):
        groups[action] = [r for r in rows if r["action"] == action]
    out = [["group", "n", "recall@1_%", "lo", "hi", "ci", "recall@3_%", "recall@5_%", "recall@10_%", "MRR", "ms_per_query"]
           + [f"{d}_%" for d in DECISIONS]]
    for name, g in groups.items():
        n = len(g)
        ranks = [int(r["rank"]) if r.get("rank") not in ("", None) else None for r in g]
        at = lambda k: Rate(sum(1 for x in ranks if x and x <= k), n)
        mrr = sum(1 / x for x in ranks if x) / n if n else None
        ms = sum(float(r["ms"]) for r in g if r.get("ms")) / n if n else None
        judged = [r for r in g if r.get("outcome")]
        dec = [_pct(sum(1 for r in judged if r["outcome"] == d) / len(judged)) if judged else "" for d in DECISIONS]
        r1 = at(1).csv()
        out.append([ACTION_NAMES.get(name, name), n, r1[2], r1[3], r1[4], r1[5], at(3).csv()[2], at(5).csv()[2], at(10).csv()[2],
                    f"{mrr:.3f}" if mrr is not None else "", f"{ms:.0f}" if ms is not None else ""] + dec)
    return out


# ---------------------------------------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------------------------------------


def write_csv(path: Path, table: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(table)


def tex_escape(text) -> str:
    return str(text).replace("\\", "\\textbackslash{}").replace("&", "\\&").replace("%", "\\%").replace("_", "\\_")


NUMBER = re.compile(r"^(--|-|-?\d+(\.\d+)?( \(\d+(\.\d+)?--\d+(\.\d+)?\)\u2020?)?)$")
INTERVAL_TEXT = {"wilson": "the 95% Wilson score interval",
                 "bootstrap": "the 95% clustered bootstrap interval (10,000 draws, by page or base task)", "none": ""}


def header_rows(header: list[str]) -> list[str]:
    """The header line(s): a line break in a cell gives a two-line header (two real rows, so LaTeX spaces them)."""
    if not any("\n" in h for h in header):
        return [" & ".join(tex_escape(h) for h in header) + " \\\\"]
    split = [h.split("\n", 1) if "\n" in h else ["", h] for h in header]
    return [" & ".join(tex_escape(top) for top, _ in split) + " \\\\",
            " & ".join(tex_escape(bottom) for _, bottom in split) + " \\\\"]


def write_tex(path: Path, caption: str, header: list[str], rows: list[list], label: str,
              groups: list[tuple[str, int]] | None = None, colsep: str | None = None) -> None:
    """In the article's style: no booktabs, \\hline\\hline at the top and bottom and \\hline after the header,
    \\small; more than 5 columns go in table* (the page's width); the first column and the text columns
    left-aligned, the numeric ones right-aligned."""
    numeric = [all(NUMBER.match(str(r[i])) for r in rows) if rows else False for i in range(len(header))]
    cols = "".join("r" if i and numeric[i] else "l" for i in range(len(header)))
    env = "table*" if len(header) > 5 else "table"
    lines = [f"% generated by eval/paper_tables.py; uncertainty: {Rate.method}", f"\\begin{{{env}}}[ht]", "\\centering",
             "\\small", *([f"\\setlength{{\\tabcolsep}}{{{colsep}}}"] if colsep else []), f"\\caption{{{tex_escape(caption)}}}", f"\\label{{{label}}}", f"\\begin{{tabular}}{{{cols}}}", "\\hline\\hline",
             *([" & ".join(f"\\multicolumn{{{n}}}{{c}}{{{tex_escape(g)}}}" if g else "" for g, n in groups) + " \\\\"]
               if groups else []),
             *header_rows(header), "\\hline"]
    lines += [" & ".join(tex_escape(c) for c in row) + " \\\\" for row in rows]
    lines += ["\\hline\\hline", "\\end{tabular}", f"\\end{{{env}}}", ""]
    path.write_text("\n".join(lines).replace(DAGGER, "\\textsuperscript{\\dag}"), encoding="utf-8")


def interval_note() -> str:
    text = INTERVAL_TEXT.get(Rate.method, Rate.method)
    if not text:
        return "Values are percentages"
    note = f"Values are percentages, with {text} in parentheses"
    if Rate.method == "bootstrap":
        note += (f"; {DAGGER} marks the 95% Wilson score interval, used where the rate is 0% or 100% (the bootstrap "
                 "interval has no width there)")
    return note


def measures_caption(title: str) -> str:
    return (f"{title} Success: the task was done and all its checks hold. False success: the run said the task "
            "was done when it was not. No extra steps: done without acting on any element the task did not "
            f"allow. {interval_note()}; n is the number of runs.")


def measures_tex(groups: dict, set_names: dict) -> list[list]:
    return [[set_names.get(s, s), EXECUTOR_NAMES.get(ex, ex), model_name(model)] + [m.tex() for m in measures(g)] + [len(g)]
            for (s, ex, model), g in sorted(groups.items(), key=group_order)]


MEASURE_HEADER = ["Set", "Executor", "Model", "Success", "False success", "No extra steps", "n"]


def table7_tex(rows: list[list]) -> tuple[list[str], list[list]]:
    """Table 7, compact: R@1 with its interval in one cell, the five decisions with short names."""
    header = ["Group", "n", "R@1", "R@3", "R@5", "R@10", "MRR", "ms", "Correct", "Silent\nerr.", "Avoid.\nref.",
              "Corr.\nref.", "Percep."]
    body = []
    for r in rows[1:]:
        r1 = f"{r[2]} ({r[3]}--{r[4]})" + (DAGGER if Rate.method == "bootstrap" and r[5] == "wilson" else "") \
            if r[3] != "" else r[2]
        body.append([r[0], r[1], r1, r[6], r[7], r[8], r[9], r[10]] + [x or "--" for x in r[11:16]])
    return header, body


TABLE7_CAPTION = ("Element selection on the closed set. R@k: cases with the right element among the first k candidates; "
                  "MRR: mean reciprocal rank; ms: mean time per query. The executor's decisions: Correct (acted on the "
                  "right element), Silent err. (acted on a wrong one), Avoid. ref. (refused when the right element was "
                  "first), Corr. ref. (refused when it was not first), Percep. (the right element was not indexed). ")


# ---------------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.paper_tables", description="The article's tables and figures.")
    ap.add_argument("--final", action="store_true", help="the newest *_FINAL result files (they must share one commit)")
    ap.add_argument("--resilience", nargs="*", default=[], help="resilience result files (.csv)")
    ap.add_argument("--plans", nargs="*", default=[], help="plan_run result files (.csv), both executors")
    ap.add_argument("--resolver", nargs="*", default=[], help="eval.run result files (.csv)")
    ap.add_argument("--out", default=str(ROOT / "paper"), help="output folder (default: eval/paper)")
    ap.add_argument("--ci", choices=sorted(INTERVALS), default="bootstrap",
                    help="the uncertainty interval (default: bootstrap, 95%%, with Wilson at 0%% and 100%%)")
    args = ap.parse_args(argv)
    Rate.method = args.ci

    expand = lambda items: [Path(p) for item in items for p in (sorted(glob.glob(item)) or [item])]
    if args.final:
        resilience = newest("resilience_*_FINAL.csv")
        plans = newest("plans_*_FINAL.csv")
        resolver = newest("*_FINAL.csv", exclude=("plans_", "resilience_"))[-1:]
        commits = {commit_of(p) for p in resilience + plans + resolver}
        if len(commits) > 1:
            ap.error(f"the final files come from different commits: {sorted(commits)}")
    else:
        resilience, plans, resolver = expand(args.resilience), expand(args.plans), expand(args.resolver)
    if not (resilience or plans or resolver):
        ap.error("no result files: use --final, or give --resilience, --plans and --resolver")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    written = []

    if resilience:
        resilience_rows, repetitions = collapse_repetitions(read_rows(resilience))
        if repetitions:
            write_csv(out / "repetitions_resilience.csv", repetitions)
            written.append("repetitions_resilience.csv")
        fig, safety = fig2_fig3(resilience_rows)
        write_csv(out / "fig2_fig3_resilience.csv", fig)
        write_csv(out / "safety_level5.csv", safety)
        write_csv(out / "mcnemar_resilience.csv", mcnemar_resilience(resilience_rows))
        written += ["fig2_fig3_resilience.csv", "safety_level5.csv", "mcnemar_resilience.csv"]

    if plans:
        rows = read_rows(plans)
        main_rows = comparable(rows)
        t4 = by_kind(by_set_executor_model(main_rows))
        t4_names = kind_names(SET_NAMES, t4)
        write_csv(out / "table4_closed_sets.csv", measure_table(t4, t4_names))
        write_tex(out / "table4_closed_sets.tex", measures_caption(
                      "Results on the closed request sets, by set (possible and impossible requests apart), executor "
                      "and model. On an impossible request, success is not saying the task was done and doing "
                      "nothing the task did not allow."),
                  MEASURE_HEADER, measures_tex(t4, t4_names), "tab:closed-sets")
        write_csv(out / "table4_all_requests.csv", measure_table(by_set_executor_model(main_rows), SET_NAMES))
        person = human_by_person_table(main_rows)
        write_csv(out / "human_by_person.csv", person)
        write_tex(out / "human_by_person.tex",
                  "The human set with two bootstrap intervals for each measure, clustered by page (the main one) and by "
                  "person (the answer each request came from). Success: the task was done and all its checks hold. "
                  "False success: the run said the task was done when it was not. No extra steps: done without acting "
                  f"on any element the task did not allow. {interval_note()}; n is the number of runs.",
                  ["Executor", "Model", "Profile", "n", "People", "Success, by page", "by person",
                   "False success, by page", "by person", "No extra steps, by page", "by person"],
                  [line[:5] + sum(([interval_cell(line[i], line[i + 1], line[i + 2], line[i + 3]),
                                    interval_cell(line[i], line[i + 4], line[i + 5], line[i + 6])]
                                   for i in (5, 12, 19)), []) for line in person[1:]],
                  "tab:human-by-person")
        stops_plans = main_rows
        known = development_pages()
        def by_pages(r: dict) -> str:
            info = task_index().get(r["task"], {})
            return f"{SET_NAMES.get(request_set(r), request_set(r))}, {page_kind(info.get('fixture', ''), known)} pages"
        write_csv(out / "table4_by_pages.csv", measure_table(by_set_executor_model(main_rows, label=by_pages), {}))
        write_csv(out / "mcnemar_requests.csv", mcnemar_requests(main_rows))
        written += ["table4_by_pages.csv", "mcnemar_requests.csv"]
        both = comparable(rows, anchor_too=True)
        write_csv(out / "table4_without_readings.csv", measure_table(by_set_executor_model(both), SET_NAMES))
        write_csv(out / "readings_apart.csv", measure_table(by_set_executor_model([r for r in rows if reads(r)]), SET_NAMES))

        def sensitivity(r: dict) -> str | None:
            s = request_set(r)
            if s == "synthetic" and r["task"] not in COPIED_FROM_INSTRUCTIONS:
                return "synthetic, without t-ord-a1 and t-ord-c1"
            if s == "synthetic_controlled" and r.get("generator") != WITHOUT_GENERATOR:
                return "synthetic controlled, without ChatGPT"
            return None
        sens = by_set_executor_model([r for r in main_rows if sensitivity(r)], label=sensitivity)
        write_csv(out / "sensitivity.csv", measure_table(sens, {}))
        write_tex(out / "sensitivity.tex", measures_caption("Sensitivity analyses."), MEASURE_HEADER,
                  measures_tex(sens, {}), "tab:sensitivity")

        infeasible = infeasible_ids()
        def breakdown(r: dict) -> str | None:
            if request_set(r) != "synthetic":
                return None
            return f"{r['language']}, {'infeasible' if r['task'] in infeasible else 'feasible'}"
        write_csv(out / "synthetic_breakdown.csv",
                  measure_table(by_set_executor_model([r for r in main_rows if breakdown(r)], label=breakdown), {}))

        def people_vs_ai(r: dict) -> list[str]:
            s = request_set(r)
            if s == "synthetic_controlled":
                return ["controlled, all"] + ([] if r.get("generator") == WITHOUT_GENERATOR else ["controlled, without ChatGPT"])
            if s == "human":
                return ["human, all", f"human, {'IT' if r.get('generator') == 'it' else 'non-IT'}"]
            return []
        t5 = defaultdict(list)
        for r in main_rows:
            for name in people_vs_ai(r):
                t5[(name, plans_executor(r), r["profile"])].append(r)
        write_csv(out / "table5_people_vs_ai.csv", measure_table(t5, {}))
        write_tex(out / "table5_people_vs_ai.tex", measures_caption("People and AI models on the same nine pages."), MEASURE_HEADER,
                  measures_tex(t5, {}), "tab:people-vs-ai")

        t6 = table6([r for r in main_rows if request_set(r) != "development"] or main_rows)
        write_csv(out / "table6_failures.csv", t6)
        exec_of = [h.rsplit(" ", 1) for h in t6[0][1:]]
        groups6 = [("", 1)] + [(e, sum(1 for x in exec_of if x[0] == e))
                               for e in dict.fromkeys(x[0] for x in exec_of)]
        write_tex(out / "table6_failures.tex",
                  "Failed runs by cause, executor and model. Each failed run has one cause, by code, from its recorded "
                  "stop, in this order: safety stop, element resolution, effect verification, planning, other. False "
                  "success counts, apart, the failures in which the run said the task was done. Perception failures "
                  "are not recorded in a task run (Table 7). LLM: the LLM in control.", ["Cause"] + [m for _, m in exec_of], t6[1:],
                  "tab:failures", groups=groups6)
        written += ["table4_closed_sets.csv/.tex", "table4_all_requests.csv", "human_by_person.csv/.tex",
                    "table4_without_readings.csv", "readings_apart.csv",
                    "sensitivity.csv/.tex", "synthetic_breakdown.csv", "table5_people_vs_ai.csv/.tex",
                    "table6_failures.csv/.tex"]

    if plans or resilience:
        stops = stop_rate_table(stops_plans if plans else [], resilience_rows if resilience else [])
        write_csv(out / "stop_rate.csv", stops)
        write_tex(out / "stop_rate.tex",
                  "Runs that ended asking a person, by system and model: the run did not say the task was done, and "
                  "its last stop is one that, in real use, asks the person (the element was not found or was "
                  f"ambiguous, a login is needed, or a confirmation was denied). {interval_note()}; n is the number "
                  "of runs.", ["Source", "Set", "Executor", "Model", "Ended asking a person", "n"],
                  [line[:4] + [interval_cell(line[6], line[7], line[8], line[9]), line[5]] for line in stops[1:]],
                  "tab:stop-rate")
        written.append("stop_rate.csv/.tex")

    if resolver:
        t7 = table7(read_rows(resolver))
        write_csv(out / "table7_elements.csv", t7)
        header7, body7 = table7_tex(t7)
        write_tex(out / "table7_elements.tex", TABLE7_CAPTION + interval_note() + " (R@1); the decisions as a "
                  "percentage of the judged cases.", header7, body7, "tab:elements", colsep="4pt")
        written.append("table7_elements.csv/.tex")

    sources = [f"{p.name}\t{commit_of(p)}" for p in resilience + plans + resolver]
    (out / "sources.txt").write_text("\n".join(sources + [f"uncertainty: {Rate.method}", ""]), encoding="utf-8")
    print(f"Read {len(sources)} file(s); wrote in {out}: " + ", ".join(written + ["sources.txt"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
