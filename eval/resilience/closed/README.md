# The closed resilience set

New perturbations on known tasks: the same 30 base tasks, five levels and three executors as the
development benchmark (`eval/resilience/`), with perturbations from a catalog derived from published
sources (`CATALOG.md`, written from `catalog.json`). It runs once, in the final run of the release.

## What is here, and in what order it was committed

1. `catalog.json` / `CATALOG.md`: the operators, their source categories and weights, what is left
   out and why, the seed and the rules (version 1: 47f16d9; version 2: 09e3e50).
2. The generator, before any page was generated: `operators.js` (the 22 operators), `generate.py`
   (the draw, the check, the vetoes, the report and the manifest), `reference.py` (the reference
   executor: plain Playwright on the evaluation's markers, no part of ANCHOR), `targets.py` and
   `reference_targets.json` (the marker of the element each reference step acts on, recorded once on the
   original L0 pages, which are development pages, by running the reference plan through the agent as
   in development). Tests: `tests/resilience_closed/` (every operator keeps every marker on its element;
   no measured executor uses the markers; the generator on a made-up base).
3. The generated set, committed by the author without opening it: the pages
   (`eval/fixtures/resilience_closed/`), the tasks (`eval/plans/resilience_closed_tasks.json`) and, in
   `generated/`, the report, the list of level-2 replacements with the vetoes, and the manifest.

## How the author generates it (once)

```sh
pip install -r requirements.txt
python -m nltk.downloader wordnet omw-2.0
python -m eval.resilience.closed.generate
```

The generator runs only exactly as committed, and refuses to run once the set is committed. It prints
only counts. The one output meant to be read is `generated/level2_replacements.csv` (task, level,
element, original word → replacement): for each replacement that makes no sense, add a line to a
`vetoes.csv` kept outside the repository (`task;level;element;word;replacement`, copied from the list)
and run again with `--vetoes vetoes.csv`. A vetoed replacement is drawn again, at most 3 times per
element; when an element's replacements run out, it gets another operator of level 2. Repeat until a
run brings no replacement to veto. Then commit, without opening them, the pages, the tasks and
`generated/` (the final `vetoes.csv` is copied into `generated/` too, so the vetoes are recorded).

The author does not open the generated pages, the tasks or the report: the set reaches the measured
systems, and the people who wrote them, only in the final run.

## The rules, from the catalog

- For each base task and level 1 to 5, 2 operators of the level, drawn with weights from the
  taxonomy's totals; every operator at least once in the set (the coverage), and, in each task and
  level, at least one operator on an element the reference plan uses. Operators that no base page
  allows, or that no task and level could take without breaking that rule, are recorded in the report.
- Each perturbed task is checked by the reference executor; if a combination makes it impossible, that
  task and level is drawn again with the next seed (at most 10 times), and every redraw is recorded.
- The evaluation's markers stay on the elements they were on; copies never carry one. No measured
  executor uses them.
- The manifest records the generator's commit, the Python, nltk and dictionary versions (the
  dictionaries' zip files by their SHA-256) and the SHA-256 of every file written. The Portuguese
  synonyms come from the OpenWN-PT (licence CC BY-SA 3.0) through the Open Multilingual Wordnet; the set
  uses isolated words and does not redistribute the dictionary.
