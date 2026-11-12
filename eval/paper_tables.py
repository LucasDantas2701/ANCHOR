"""
The article's tables and figures, computed from the result files of the final run.

    python -m eval.paper_tables --final                        # the newest *_FINAL files, all of one commit
    python -m eval.paper_tables --resilience F [F ...] --plans F [F ...] --resolver F --out DIR

Writes, in --out (default eval/paper/):
  fig2_fig3_resilience.csv   success and false success by level, executor and model; the main combinations
                             (level 0 and those that reach the reference plan) and the off-path ones apart
  safety_level5.csv          attacks that worked and attempts at level 5, by executor and model
  table4_closed_sets.tex/csv the closed request sets by set, executor and model: success, false success,
                             runs without unrequested steps (the model in control without the tasks that
                             expect readings, which are reported apart)
  table4_without_readings    the same, ANCHOR also without those tasks: the comparison between executors
  readings_apart.csv         the tasks with expected readings, both executors
  sensitivity.tex/csv        the synthetic set without t-ord-a1 and t-ord-c1; the controlled set without ChatGPT
  synthetic_breakdown.csv    the synthetic set by language and by feasible / infeasible request
  table5_people_vs_ai.tex/csv  controlled (all, without ChatGPT) against human (all, IT, non-IT)
  table6_failures.tex/csv    failed runs by cause and executor (the rule in failure_cause)
  table7_elements.tex/csv    element selection: recall@1/3/5/10, MRR, time per query and the five decisions
  sources.txt                the files read and their commits

It reads result files only (and, for the infeasible mark, the task definitions' "expected" field), and
writes and prints no request text. Test it only with development results, never with closed ones.
"""
from __future__ import annotations

import argparse
import csv
import glob
import math
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"

# Sensitivity analyses (decided before the final run; base técnica)
COPIED_FROM_INSTRUCTIONS = ("t-ord-a1", "t-ord-c1")     # synthetic set, registered on 23/10/2026
WITHOUT_GENERATOR = "chatgpt"                          # synthetic controlled set, decided on 22/10/2026

# ---------------------------------------------------------------------------------------------------------
# Uncertainty: pluggable (the method is to be defined; Wilson 95% is the provisional default)
# ---------------------------------------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float] | None:
    """Wilson score interval for k successes in n trials (95% by default)."""
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


INTERVALS = {"wilson": wilson, "none": lambda k, n: None}


class Rate:
    """k of n, with its interval from the chosen method."""
    method = "wilson"

    def __init__(self, k: int, n: int):
        self.k, self.n = k, n
        self.ci = INTERVALS[Rate.method](k, n)

    @property
    def rate(self) -> float | None:
        return self.k / self.n if self.n else None

    def csv(self) -> list:
        lo, hi = self.ci if self.ci else ("", "")
        return [self.k, self.n, _pct(self.rate), _pct(lo), _pct(hi)]

    def tex(self) -> str:
        if not self.n:
            return "--"
        text = f"{100 * self.rate:.1f}"
        if self.ci:
            text += f" ({100 * self.ci[0]:.1f}--{100 * self.ci[1]:.1f})"
        return text


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
# Figures 2 and 3: resilience
# ---------------------------------------------------------------------------------------------------------

MODEL_NAMES = {"ollama-small": "4B", "ollama-medium": "9B"}
SHORT_EXECUTOR = {"anchor": "ANCHOR", "llm": "LLM"}
ACTION_NAMES = {"all": "All", "click": "click", "fill": "type", "select": "select", "check": "check",
                "uncheck": "uncheck", "hover": "hover", "press": "press a key", "extract_text": "read text",
                "extract_table": "read table", "download": "download", "upload": "upload"}


def model_name(profile: str) -> str:
    return MODEL_NAMES.get(profile, profile) if profile else "-"


EXECUTOR_NAMES = {"script": "Fixed selectors", "llm": "LLM in control", "anchor": "ANCHOR",
                  "anchor1": "ANCHOR, 1st run", "anchor2": "ANCHOR, 2nd run (no model call)"}


def resilience_executor(row: dict) -> str:
    if row["executor"] == "anchor":
        return "anchor1" if row["run"] == "1" else "anchor2"
    return row["executor"]


def resilience_success(row: dict) -> bool:
    """The 2nd ANCHOR run counts as a success only when done again with no model call (as the report does)."""
    if resilience_executor(row) == "anchor2":
        return true(row["success"]) and row.get("llm_calls") in ("0", "")
    return true(row["success"])


def resilience_part(row: dict) -> str:
    """main: level 0 and the combinations that reach the reference plan; off_path: the others. Development
    files have no mark (reaches_plan is empty): every row counts as main there."""
    return "off_path" if row.get("reaches_plan") == "no" else "main"


def fig2_fig3(rows: list[dict]) -> tuple[list[list], list[list]]:
    groups = defaultdict(list)
    for r in rows:
        groups[(resilience_part(r), resilience_executor(r), r.get("profile") or "", int(r["level"]))].append(r)
    table = [["part", "executor", "model", "level", "success_k", "n", "success_%", "success_lo", "success_hi",
              "false_success_k", "n", "false_success_%", "false_lo", "false_hi"]]
    for (part, ex, model, level), g in sorted(groups.items()):
        table.append([part, EXECUTOR_NAMES[ex], model_name(model), level]
                     + Rate(sum(resilience_success(r) for r in g), len(g)).csv()
                     + Rate(sum(true(r.get("false_success")) for r in g), len(g)).csv())
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
    n = len(rows)
    return [Rate(sum(true(r["success"]) for r in rows), n), Rate(sum(true(r["premature"]) for r in rows), n),
            Rate(sum(true(r["clean"]) for r in rows), n)]


def comparable(rows: list[dict], anchor_too: bool = False) -> list[dict]:
    """The rule of 07/11/2026: the model in control is compared without the tasks that expect readings."""
    return [r for r in rows if not (reads(r) and (anchor_too or plans_executor(r) == "llm"))]


def by_set_executor_model(rows: list[dict], label=request_set) -> dict:
    groups = defaultdict(list)
    for r in rows:
        groups[(label(r), plans_executor(r), r["profile"])].append(r)
    return groups


def measure_table(groups: dict, set_names: dict) -> list[list]:
    out = [["set", "executor", "model", "success_k", "n", "success_%", "lo", "hi", "false_success_k", "n",
            "false_success_%", "lo", "hi", "clean_k", "n", "clean_%", "lo", "hi"]]
    for (s, ex, model), g in sorted(groups.items(), key=group_order):
        out.append([set_names.get(s, s), EXECUTOR_NAMES.get(ex, ex), model_name(model)] + sum((m.csv() for m in measures(g)), []))
    return out


SET_ORDER = ["synthetic", "synthetic_controlled", "human", "development"]


def group_order(item) -> tuple:
    """Sets in the article's order, then ANCHOR before the LLM in control, then 4B before 9B."""
    (s, ex, model), _ = item
    return (SET_ORDER.index(s) if s in SET_ORDER else len(SET_ORDER), str(s), ex, model_name(model))


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
    out = [["group", "n", "recall@1_%", "lo", "hi", "recall@3_%", "recall@5_%", "recall@10_%", "MRR", "ms_per_query"]
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
        out.append([ACTION_NAMES.get(name, name), n, r1[2], r1[3], r1[4], at(3).csv()[2], at(5).csv()[2], at(10).csv()[2],
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


NUMBER = re.compile(r"^(--|-|-?\d+(\.\d+)?( \(\d+(\.\d+)?--\d+(\.\d+)?\))?)$")
INTERVAL_TEXT = {"wilson": "the 95% Wilson score interval", "none": ""}


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
    path.write_text("\n".join(lines), encoding="utf-8")


def interval_note() -> str:
    text = INTERVAL_TEXT.get(Rate.method, Rate.method)
    return f"Values are percentages, with {text} in parentheses" if text else "Values are percentages"


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
        r1 = f"{r[2]} ({r[3]}--{r[4]})" if r[3] != "" else r[2]
        body.append([r[0], r[1], r1, r[5], r[6], r[7], r[8], r[9]] + [x or "--" for x in r[10:15]])
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
    ap.add_argument("--ci", choices=sorted(INTERVALS), default="wilson", help="the uncertainty interval (default: wilson, 95%%)")
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
        fig, safety = fig2_fig3(read_rows(resilience))
        write_csv(out / "fig2_fig3_resilience.csv", fig)
        write_csv(out / "safety_level5.csv", safety)
        written += ["fig2_fig3_resilience.csv", "safety_level5.csv"]

    if plans:
        rows = read_rows(plans)
        main_rows = comparable(rows)
        write_csv(out / "table4_closed_sets.csv", measure_table(by_set_executor_model(main_rows), SET_NAMES))
        write_tex(out / "table4_closed_sets.tex", measures_caption(
                      "Results on the closed request sets, by set, executor and model; the LLM in control without the "
                      "tasks that expect readings, reported apart."),
                  MEASURE_HEADER, measures_tex(by_set_executor_model(main_rows), SET_NAMES), "tab:closed-sets")
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
        written += ["table4_closed_sets.csv/.tex", "table4_without_readings.csv", "readings_apart.csv",
                    "sensitivity.csv/.tex", "synthetic_breakdown.csv", "table5_people_vs_ai.csv/.tex",
                    "table6_failures.csv/.tex"]

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
