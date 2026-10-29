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

0. Every result file records where it was measured (`eval/provenance.py`): the full commit, its
   tag, and whether the working copy had uncommitted changes (then the file's name says `+dirty`
   and the file lists them). A final run (`--final`) refuses to run unless the working copy is clean
   and the commit has the release's tag: so the release is tagged (`git tag v1.0.0`) BEFORE the
   final run, and its results already carry the tag.
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
edit the generated files by hand. These are development perturbations, written by hand by whoever
developed the engine. The closed set will use the same 30 base tasks, the same five levels and the
same three executors, with perturbations from a catalog derived from a published taxonomy of why
web UI tests break, drawn by a generator with a fixed seed; the catalog, the generator and the
generated pages are committed in that order, before any run on them, and it runs once, at the end.

### Closed set of planner tasks

The tasks in `plans/tasks.json` and `tasks_en.json` were used to tune the system, so their numbers
are development numbers. The final numbers come from the closed sets (split `test`):
`plans/holdout_tasks.json` (synthetic), `plans/holdout_controlled_tasks.json` (synthetic_controlled)
and `plans/holdout_human_tasks.json` (human, once drawn), which only run with
`python -m eval.plan_run --final --agent`, a single time, at the end, on the tagged release with a
clean working copy (rule 0 above); the results come out by origin and by generator.

**How it was built (October 2026): the synthetic set.** The 80 requests were generated on 08/10/2026
by three AIs (A, B and C in the file), each in a new conversation with no history of the project:
one ChatGPT (GPT-5.6 Luna) and two Claude (Sonnet 5.5, medium effort, in different accounts). Each got
the zip `pedidos_assistente.zip` attached (a LEIA-ME with the instructions, the 13 pages and
`feedback.js`), the help-request message and the instruction of 2 requests per page, and generated
once, with no correction and no new try: 28, 26 and 26 requests. The letters are: **A = a Claude**
(28 requests), **B = the ChatGPT** (26, as its conversation says) and **C = the other Claude** (26);
in the results, the generators are `claude_a`, `chatgpt` and `claude_c` (named by letter: whether
these are the accounts of the `synthetic_controlled` set's `claude_1` and `claude_2` is not recorded).
The three sheets, as returned, and the ChatGPT conversation are in `synthetic_2026-10-08/` (with
their hashes in its `SHA256SUMS`). The mapping was made on 23/10/2026 by code that compared the
sheets with the tasks file without printing any request: each of the 80 is in exactly one sheet.
What that comparison found, as counts: A has 2 requests on every page except `store.html`, where it
has 4; A and C each have one request identical, word for word, to an example in the LEIA-ME (on
`orders.html`), so copied from the instructions and not written by the generator; and A and C share
one more identical request (on `holdout_blog.html`) that is not in the LEIA-ME.

**Decided on 23/10/2026, before the final run:** the main analysis has the 80 requests, as the
protocol foresaw; a sensitivity analysis leaves out the 2 requests identical to the LEIA-ME's examples
(tasks `t-ord-a1` and `t-ord-c1`, found by comparing with the LEIA-ME of the 08/10 package, kept in
`synthetic_2026-10-08/pacote/`); the pair identical between A and C stays in both analyses, declared
as convergence between generators of the same family; A's 4 requests on the store stay, declared as
a departure from the instruction of 2 per page. The results come out with and without the 2 copies.

**Did the generators see the pages?** Counted on 23/10/2026 by `python -m eval.closed_sets page-items
<origin>` (counts only): a request "cites an item of its page" when it has a word of the page's
visible text that is on no other page of its set (a room, a person, a product, a number...). In the
synthetic set: chatgpt 25 of 26 (96%), claude_a 26 of 28 (93%), claude_c 25 of 26 (96%); a stricter
version (names and numbers only) gives 88%, 86% and 92%. In the synthetic_controlled set: chatgpt 8
of 14 (57%), claude_1 14 of 14, claude_2 14 of 14; strict, 36%, 100% and 93%. So the ChatGPT of 08/10
read the pages (they were HTML files in its package), while the ChatGPT of 22/10 did not, as it said;
the ChatGPT sensitivity analysis applies to synthetic_controlled only. All of them were kept, none selected. Half are on the four `holdout_*.html` pages, never used in
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
  28 of the two Claudes, since the ChatGPT reported it could not render the pages. Its package used
  the LEIA-ME from before the form's revision (see `fixtures/collection/README.md`), so its
  instructions differ from the people's.
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

### Annotating the closed sets: the negative checks come prefilled

A task succeeds when all its checks hold at the end; touching an element outside its allowed list does
not fail it (it is counted as an unrequested step), but an unwanted effect does, through the task's
negative checks. So that these do not depend on the annotator's memory, every skeleton gets, before the
annotation, the negative checks of ALL the irreversible actions of its task's page
(`python -m eval.closed_sets negatives <tasks file>`; for the human set, right after the draw): ONE PER
ELEMENT, each named in a comment, with the row it belongs to when the same action appears more than once
on the page (`!__clicked('table > tbody > tr:nth-of-type(2) > td:nth-of-type(4) > button') /* Excluir —
linha: Bruno Lima */`). The annotator only deletes the one(s) the request asks for (deleting Bruno Lima:
only that row's), so an executor that does the same action on another row fails. The irreversible actions are found from the pages alone, never from a
request, by the start of each control's accessible name: deleting (excluir, apagar, remover, desativar,
bloquear...), cancelling something ("Cancelar pedido"; a bare "Cancelar", which only closes a form, is
not one), sending or recording (enviar, publicar, salvar, reservar, registrar, abrir chamado,
candidatar, assumir...) and paying (pagar, comprar, finalizar, confirmar). On the collection's pages
(25 checks): blog, Salvar rascunho and Publicar; cadastro, Salvar cadastro and Enviar para aprovação;
loja, none; pedidos, Cancelar pedido (2 rows); reservas, Reservar sala and Excluir reserva (2 rows); rh,
Registrar entrada, Registrar saída and Enviar solicitação; suporte, Abrir chamado, Assumir (2 rows) and
Enviar comentário; usuarios, Excluir (3 rows); vagas, Salvar vaga and Candidatura simplificada (3 each).

