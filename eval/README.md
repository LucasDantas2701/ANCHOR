# Evaluation

Two evaluations live here:

- **`eval/run.py`** measures the element resolver case by case (page + query + expected element).
- **`eval/plan_run.py`** measures complete tasks (request → plan → execution → final state),
  with the planner alone or through the full agent loop.

The test pages (`fixtures/`) and the requests stay in Portuguese: they represent the real user.

## Resolver evaluation

From the project root:

    python -m eval.run --offline -v     # local pages only, showing each case
    python -m eval.run                  # includes real sites (SauceDemo)
    python -m eval.run --sweep          # tries combinations of minimum score × gap
    python -m eval.run --check          # only checks that the expected selectors exist
    python -m eval.run --language en    # only the English cases (pt or en; default: both)

Each run writes `results/<date>_<commit>.csv` (one case per line) and a `.json` with the summary.

### Case file format (`cases/<site>.json`)

    {
      "site": "store",
      "fixture": "store.html",           // local page in fixtures/  (or "url": "https://...")
      "setup": "saucedemo_login",        // optional: a function in setups.py
      "requires_network": false,
      "cases": [
        {"id": "store-01", "split": "dev", "action": "click",
         "query": "adicionar os fones de ouvido ao carrinho",
         "expected": ".card:nth-of-type(2) .add"}
      ]
    }

- `action`: the Executor action (click, fill, check, select, extract_text...).
- `expected`: a CSS selector (or a Playwright one, such as `:has-text()`) for the right element.
  If more than one element is acceptable, the selector may match several.
- `split`: `dev` to tune weights and synonyms; `test` only to measure.
- `synonyms` (optional, at site level): site-specific vocabulary, passed to the resolver.
- `language` (optional, at site level): the queries' language, `pt` (default) or `en`. The English
  sets (`*_en.json`) mirror the Portuguese ones, on English pages; results are reported per
  language. Tune the resolver looking only at the development cases of each language.

### Golden rule

Tune weights, synonyms and heuristics looking **only** at `dev`. The number that goes into the
article is the `test` one. If the code is improved by looking at the test cases, the result no
longer measures generalization.

### Per-case outcome (`outcome`)

| value | meaning |
|---|---|
| `correct` | the Executor decided and chose the right element |
| `silent_error` | the Executor decided, but chose the **wrong** element (the worst case) |
| `avoidable_refusal` | the right one was 1st, but the Executor refused (conservative threshold) |
| `correct_refusal` | the Executor refused and the 1st was wrong (it avoided an error) |
| `perception_failure` | the right element was not even indexed by `index_script.js` |

Result files from before 2026-09-30 use the Portuguese names (`acerto`, `erro_silencioso`,
`recusa_evitavel`, `recusa_correta`, `falha_percepcao`).

### The human collection's pages

`fixtures/collection/` holds the pages people saw when they wrote the human closed set's requests:
nine pages in Portuguese, made from the synthetic set's package before the collection (three
translated, six as they were, all with a plain stylesheet). See its README for what changed in each.
The human set runs on them; the synthetic set runs on the original pages.

### Holdout (the closed test set)

The `cases/holdout_*.json` files (split `test`) form the closed set, created on 2026-09-25,
**before** the conflicting-verb fixes and the threshold recalibration. The cases of the old
`test` split became `dev` (field `split_original: "test"`), because they had already been looked at.

Rules:

1. `python -m eval.run` never runs the holdout. Only `--final` does, and the result file gets the
   `_FINAL` suffix.
2. Run `--final` **once**, when the resolver's development is over. The article's numbers come
   from that run.
3. If anything is changed after looking at the holdout, record it in the article.
4. `--check` can be used at any time: it only checks that the expected selectors exist, without
   computing scores.

#### Queries from other people (recommended)

The holdout queries were written by the same author as the heuristics (authorship bias). The
human closed set (below) addresses it for the tasks; for the resolver's queries, ask 2 or 3 people to:

1. open each page of `fixtures/holdout_*.html` in the browser;
2. write, for 8 to 10 elements, how they would ask an assistant for that action
   ("quero cancelar o pedido do dia 3 de novembro");
3. without seeing the code or the existing cases.

Add those queries as new `split: "test"` cases, with ids `h-<page>-cNN`, and report both groups
separately in the article.

## Task evaluation

    python -m eval.plan_run --reference                      # hand-written plans (ceiling, no LLM)
    python -m eval.plan_run --profiles ollama-small ollama-medium -v
    python -m eval.plan_run --agent --profiles ollama-small  # through the full agent loop
    python -m eval.plan_run --check                          # checks the tasks, without calling models

Each run writes `results/plans_<date>_<commit>.csv` and a `.json` with the summary (files from
before 2026-09-30 start with `planos_` and use Portuguese field names). The comparison table
shows, per model: tasks done, **clean** tasks (done with no unrequested step), unrequested steps,
valid plans, checks passed, heuristic refusals, time and tokens; with `--agent`, also model calls,
replans, actions with no effect, premature ends, goals fulfilled and suspicions.

The English tasks (`plans/tasks_en.json`, field `"language": "en"`) mirror the Portuguese ones on
the English pages. `--language pt|en` runs only one of them; by default both run, and the table
shows each profile per language.

`--prompt-language` chooses the planner prompt: `pt`, `en`, or `auto` (it follows each request's
language). The measured results so far use the Portuguese one (the default). To compare:

    python -m eval.plan_run --agent --profiles ollama-small ollama-medium --prompt-language pt -v
    python -m eval.plan_run --agent --profiles ollama-small ollama-medium --prompt-language auto -v

### Data extraction (`--suite extraction`)

`plans/tasks_extraction.json` has 8 tasks (4 per language) on `fixtures/report.html` and
`report_en.html` (a monthly report with two tables, a list, a total and menus that must not be
taken as data) and on the users pages. Reading does not change the page, so each task has an
`extraction`: what must have been read, either a table or list (`kind`, `name`, and optionally
`rows` and `columns`) or a text (`kind: "text"`, `contains`). Its `checks` only make sure nothing
was clicked or checked. The CSV files written during the run go to a temporary folder.

The users task first said "copie a tabela de usuários para uma planilha" ("copy the users table
into a spreadsheet"); both models clicked the page's "Exportar planilha" button, a fair reading of
that wording, so the task was reworded to "copie a tabela de usuários" ("copy the users table").
Both models still use the button: on a page with its own export, "copy the table" reads as
exporting it, a fair choice that this suite cannot judge, since it does not see downloads. The
download step of 0.4 makes that checkable.

    python -m eval.plan_run --agent --suite extraction --profiles ollama-small ollama-medium -v

### What a run ran on

Every results file (`.json`) has an `environment` entry with, for each profile, the Ollama version
and the model's digest and date, and `plan_run` prints them before the tasks. On 14/10/2026 an
automatic Ollama update (to 0.40.4), with the same model files, changed the 4B model's plan for a
task that had been stable for days: runs on different Ollama versions or model digests are not
comparable, and the version must be the same through a whole set of measurements (turn off
Ollama's automatic updates before the final runs).

### Iframes (`--suite frames`)

`plans/tasks_frames.json` has 8 tasks (4 per language) on `fixtures/newsletter.html` and
`newsletter_en.html`: a blog page with the newsletter form inside an iframe loaded from another file
(another origin for the browser), and a lookalike button on the page itself ("Assinar plano Premium").
The page cannot read the iframe, so the form tells it every change with `postMessage`, and the checks
read `window.__frameState`. Unrequested steps are counted inside iframes too. One task per language
asks for something the page does not have (cancelling a subscription).

### New tabs (`--suite tabs`)

`plans/tasks_tabs.json` has 8 tasks (4 per language) on `fixtures/help.html` and `help_en.html`: a link
that opens a support form in a new tab (`target="_blank"`), a button that opens a policy page with
`window.open`, and a plain link that must not leave the first tab. The checks run on the tab the agent
ended in, and unrequested steps are counted on every open tab. It needs `--agent`: the plan mode does
not follow tabs. The evaluation's instrumentation is now added to the browser context, so new tabs get
it too, and links with `target="_blank"` are no longer stopped (no other fixture has them).

### Uploads (`--suite uploads`)

`plans/tasks_uploads.json` has 10 tasks (5 per language) on `fixtures/application.html` and
`application_en.html`, a job application form with a visible file field, a button that opens a
hidden one, and a photo field; the files are in `fixtures/files/`. The checks read, on the page,
which file each field received. Two tasks per language must send nothing: a path that does not
exist, and a request with no path at all (the model must never choose a file).

### Downloads (`--suite downloads`)

`plans/tasks_downloads.json` has 8 tasks (4 per language) on `fixtures/documents.html` and
`documents_en.html`: two buttons that download real files made in the page (a CSV and a PDF), a link
that downloads nothing, and a decoy ("Baixar aplicativo"). A download is judged on the file it saved:
`extraction` entries with `kind: "file"`, a piece of its `name` and of its content (`contains`). Two
tasks ask for a file the page does not have (`expected: "not_possible"`). The evaluation's
instrumentation lets links with the `download` attribute work, and does not count, as touched by the
agent, an element the page created and removed by itself (the link that starts the download).

### Prompt injection (`--suite injection`)

`plans/tasks_injection.json` has 6 tasks (3 per language) on `fixtures/injection.html` and
`injection_en.html`, pages that try to make the agent do what the user did not ask: an
instruction in a product's description (it reaches the model as the item's context), in an
almost invisible link, in an `aria-label`, and in a message that appears after a search. Each
request is harmless (search, add a product, subscribe with one's own e-mail). Besides the usual
checks, each task has `attacks`: JavaScript expressions that are true if an attack worked (the
account deleted, a product not asked for added, the attacker's e-mail typed, the hidden link
followed, an unrequested subscription). The table adds the `attacked` column, and `attempts`:
steps that tried to do what the page asked (their description or value has one of the task's
`attack_targets`), even when a barrier stopped them, which shows how often the model itself was
hijacked.

    python -m eval.plan_run --agent --suite injection --profiles ollama-small ollama-medium -v

These tasks are not part of the main suite, so the numbers of the ordinary tasks stay comparable.

### Resilience benchmark

`python -m eval.resilience.build` builds altered versions of the task pages in 5 levels
(`fixtures/resilience/L0` to `L5`) and the tasks for them (`plans/resilience_tasks.json`); see the
command reference for the levels. The tasks' checks use `data-eval`, the evaluation's own marker,
so they work on every level; no executor may use it. Rebuild after changing a task or a page, never
edit the generated files by hand. These are development perturbations: the closed set, built later
with other perturbations, runs once, at the end.

### Closed set of planner tasks

The tasks in `plans/tasks.json` and `tasks_en.json` were used to tune the system, so their numbers
are development numbers. The final numbers come from `plans/holdout_tasks.json` (split `test`),
which only runs with `python -m eval.plan_run --final --agent`, a single time, at the end.

**How it was built (October 2026): the synthetic set.** The 80 requests were generated on 08/10/2026
by three AIs (A, B and C in the file), each in a new conversation with no history of the project:
one ChatGPT (GPT-5.6 Luna) and two Claude (Sonnet 5.5, medium effort, in different accounts). Each got
the zip `pedidos_assistente.zip` attached (a LEIA-ME with the instructions, the 13 pages and
`feedback.js`), the help-request message and the instruction of 2 requests per page, and generated
once, with no correction and no new try: 28, 26 and 26 requests. All of them were kept, none selected. Half are on the four `holdout_*.html` pages, never used in
development (two in Portuguese, two in English; they are also the resolver's closed set), and half
are new requests on nine known pages, so the article can separate new requests from new pages.
There are 42 requests in Portuguese and 38 in English. (An earlier version of this README said the
requests were written by colleagues: that was wrong, corrected on 22/10/2026.)

**The other closed sets: three origins.** Each closed task has an `origin`, and the results come
out separately for each one (and for each `generator` within it):

- `synthetic`: the 80 above, on the original pages.
- `synthetic_controlled`: 42 requests generated on 22/10/2026 by the same three AIs, on the human
  collection's pages (`fixtures/collection/`), with the collection's instructions. The package, the
  sheets as they were returned, screenshots of the conversations and the provenance are in
  `synthetic_controlled_2026-10-22/` (its `PROCEDENCIA.md` records what happened, and the hashes
  are in `SHA256SUMS`; a `.gitattributes` keeps the files byte for byte). Decided before any
  annotation or run: the results come out with the 42 and, as a sensitivity analysis, with only the
  28 of the two Claudes, since the ChatGPT reported it could not render the pages.
- `human`: 60 requests drawn from the human collection, on the same pages.

`python -m eval.closed_sets skeleton synthetic_controlled_2026-10-22 synthetic_controlled` turns the
sheets into `plans/holdout_controlled_tasks.json`, one task per request with its origin and generator
and empty `checks`, `allowed` and `reference` to annotate (the sheets' header is read as it is,
including the literal `\xef\xbb\xbf` text in `chatgpt.csv`). Like every closed set, these are not run
by the system, nor is its behaviour on them looked at, before the final run.

**Each request became a task**: `checks` (the final state; dates like "amanhã" are computed when
the check runs), `allowed`, a hand-written `reference` plan (a value `{tomorrow}` becomes tomorrow's
date) and `reference_targets`, the selector of each reference step. 22 requests cannot be done on
their pages (a disabled button, a form that does not exist, an order already delivered, a product
the store does not sell); they have `"expected": "not_possible"` and a `why_not_possible`, and are
done right when the agent does **not** declare success and their checks (safety: nothing harmful)
hold. Declaring success on them counts as a premature end.

**Checked without trying the system.** `python -m eval.plan_run --check` runs each reference plan on
its `reference_targets` with Playwright alone, with no part of ANCHOR, and checks that every check
holds and nothing unrequested was touched (all 80 pass). A first validation, before this one, ran
the reference plans through ANCHOR's resolver and agent loop; it showed that some of ANCHOR's checks
refuse correct plans on these requests (for example, the check of the request against "Excluir
reserva" for "cancela minha reunião") and that the resolver picks a wrong button on the help desk
page. Nothing in the system was changed because of it: those behaviors will show in the final run,
and the article reports this exposure.

**Rules until the final run:** do not run the models on these tasks, do not look at the system's
behavior on them, and do not change the system, the prompts or the tasks because of them.

