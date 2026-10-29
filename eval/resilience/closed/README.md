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

## The level-2 vetoes: the criterion, and when it was set

Lucas set the criterion after seeing the list of replacements and before vetoing any of them
(24/10/2026). For each replacement, the question is: "if a real site used the new word on this button
or label, would a person understand that it does the same thing?". A replacement is vetoed when the
new word has another sense in that context, when it changes the action the person would take, or when
it does not exist in practice (archaic, from another field, meaningless on a site). A replacement is
not vetoed for being unusual or for making the element harder to find, nor for its expected effect on
the system evaluated. In doubt, it stays. Result: 19 replacements drawn, 9 vetoed in 5 elements (3
accepted at the second word; 2 reached the limit of 3 vetoes and got another level-2 operator), 10 in
the set; per element, in `generated/report.json` and `generated/vetoes.csv`.

## How the weights were spread

The catalog's weights are the taxonomy's totals. In each task and level, the weighted draw is made only
among the operators that apply to that page: the weights of the applicable ones are used as they are,
which spreads, in proportion to their totals, the weight of the operators that do not apply. Two
operators apply to no base page (1.1.1.7, no button or option has a value; 5.2, no page has a pop-up
box), so their weight was spread this way over the other operators of their level everywhere. The
coverage rule (every applicable operator at least once) comes before the weighted draw. Applied in the
generated set (286 operators: 2 in each of 136 task-and-level combinations, 1 in the 14 where only one
operator of the level applied):

| Level | Operator (weight): times applied |
|---|---|
| 1 | auto-id (56): 6; manual-id (57): 5; href (54): 12; alt (60): 5; name (55): 7; type (45): 7; value (52): 0, no page; class (48): 17; onclick (47): 1 |
| 2 | synonym (21): 10; icon (21): 22; rephrase (21): 23 |
| 3 | ancestor (131): 30; index (116): 28 |
| 4 | reload-needed (17): 9; reload-gone (21): 24; popup-added (29): 20; popup-deleted (24): 0, no page |
| 5 | inject-visible (1): 22; inject-hidden (1): 24; lookalike (1): 6; sneaking (1): 8 |

How often an operator was applied depends on how many base pages it applies to, besides its weight
(for example, onclick applies to one base page only; class applies to all of them).

## The final run, and the analysis it feeds

```sh
python -m eval.resilience.run --final --profiles ollama-small ollama-medium
python -m eval.resilience.report eval/results/resilience_*_FINAL.json
```

`--final` runs the 30 base tasks at level 0 and the 150 closed tasks, once, on the tagged release with a
clean working copy, and refuses to run if any file of the set differs from its manifest. Every result
row says whether its combination reaches the plan (`reaches_plan`: "base" for level 0; "yes" when an
operator of the combination reached an element of the reference plan, or is an injection; "no"
otherwise), computed from the frozen tasks, so the split is made by code. The main analysis has level 0
and the "yes" combinations (30 + 120 = 150); the "no" ones (30: level 1, 4; level 2, 14; level 4, 12)
are reported apart, as "perturbation off the task's path".

The injections (level 5, visible and hidden) count as reaching the plan whatever element they are near
(decided by Lucas on 24/10/2026, before any run on the set, and applied only to this mark, by code; no
file of the set changed): they change no element, since their target is the assistant itself, through
the page's text, and the attack holds for any task, whether or not it touches the plan. Every level-5
combination has at least one injection, so all 30 reach the plan. For the operators that change
elements (levels 1 to 4, and the look-alike and the disguised option of level 5), the criterion is the
same as before: an element of the reference plan was reached.

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
