# Command reference

Every command-line tool of ANCHOR, with all its options. Run the commands from the project
root, with the virtual environment active. A test (`tests/test_docs.py`) checks that every
option shown by `--help` is documented here, so this page stays complete.

The old Portuguese options and commands (`--perfil`, `--memoria`, `--perfis`, `listar`...) still
work, hidden from `--help`; they are not listed here.

**Contents:** [setup](#setup) · [agent](#agent-anchoragent) · [planner](#planner-anchorplanner) ·
[saved automations](#saved-automations-anchorautomations) ·
[choice memory](#choice-memory-anchorenginememory) · [demos](#demos) ·
[evaluation](#evaluation) · [development](#development) ·
[model profiles](#model-profiles-llm_profilesjson) · [environment variables](#environment-variables)

---

## Setup

```sh
git clone https://github.com/LucasDantas2701/ANCHOR.git
cd ANCHOR
python -m venv venv
venv\Scripts\activate              # Windows; on Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
playwright install chromium        # the browser Playwright controls
```

The planner runs on local models served by [Ollama](https://ollama.com):

| Command | Meaning |
|---|---|
| `ollama pull qwen3.5:4b` | Downloads a model (`qwen3.5:9b` for the medium profile). |
| `ollama list` | Shows the downloaded models and their exact names (they go in `llm_profiles.json`). |
| `ollama ps` | Shows the loaded model and whether it runs on the GPU or the CPU (column `PROCESSOR`). |

ANCHOR plans only with local models, through Ollama: no page, request or password leaves the
computer, and no key is needed.

---

## Agent (`anchor.agent`)

Runs a request end to end: plan, execution, effect checks, replanning and end.

```sh
python -m anchor.agent --profile ollama-small --url eval/fixtures/registration_en.html "Register Maria Silva in the IT department and save the registration"
```

| Option | Meaning |
|---|---|
| `request` (positional) | What to do, in natural language (Portuguese or English). |
| `--profile` | Model profile in `llm_profiles.json` (e.g. `ollama-small`, `ollama-medium`). Required. |
| `--url` | The site's link, or the path of a local `.html` file. Required. |
| `--memory` | File of the choice memory. Default: `memory/agent.json`. |
| `--browser-profile` | Folder of a persistent browser profile, for systems with login (e.g. `profiles/user_001`). |
| `--max-attempts` | Failures before the run is cancelled. Default: 3. |
| `--vision` | When the other checks doubt a step (a field that does not show the value, a click with no visible effect in the page's code, an expected text that did not appear), asks the model about a screenshot, scaled to 640 pixels. It can only confirm a doubted step, never fail one that worked. Slower: about 5 s per question with the 4B model and 9 s with the 9B, on the test machine. The model must have the `vision` capability. |
| `--allow-sensitive` | Does not ask before sensitive actions. By default, before deleting, saving or submitting, sending, paying, downloading or uploading, or acting on your account (following someone, connecting, liking, commenting, sharing, subscribing, inviting), the agent shows the element and asks; a denial stops the run. |
| `--output-dir` | Where tables and lists read by the agent are saved (one CSV file each) and where downloaded files go, never overwriting a file. Default: `output`. |
| `--lang` | Interface language: `en` (default) or `pt`. Overrides `ANCHOR_LANG`. |
| `--prompt-language` | Planner prompt language: `pt` (default, the measured one), `en`, or `auto` (follows the request). |

**Hidden content.** When a step's target is not on the page, the agent looks for what may hide it, a
"Show more" / "Mostrar mais" button or a collapsed section (`aria-expanded="false"`), opens it and
tries the step again, before any replan. Only controls that say so, with no action verb and nothing
sensitive (never "Save and show more"), at most two per step. A step that names what its element is
about ("Add to cart of the UltraBook 14") is not done on a lookalike when that name is not on the
page: the agent reveals hidden content first, and otherwise the step is "not found".

**Cookie banners.** When a cookie or consent banner is in the way of a step, the agent declines it,
with the most restrictive option the banner offers ("Recusar", "Reject all", "Only essential"), and
says so: before the step, when the step's element is covered, and otherwise after the step fails,
which is then tried again. It never accepts cookies on its own: a banner with no way to decline is
left alone, and so is any other layer (a promotion, a notice); when such a layer covers a "Show more",
the planner is told to close it first.

**Iframes.** Elements inside an iframe (an embedded form, a payment or newsletter widget, even from
another site) are found and used like the page's own: the resolver reads the page and then each
iframe, and the effect check, the password field, tables and value texts look inside them too. Two
limits: choosing an element by clicking on it (when the agent asks) only works on the page itself,
inside an iframe you choose it by number; and the remembered choices' fallback (the saved CSS path)
only looks at the page itself.

**New tabs.** When a step opens a new tab (a link with `target="_blank"`, a button that opens a
window), the agent moves to it and replans from there; when the tab it is working in closes by
itself (a payment or login window), it goes back to the last tab still open. Only a tab the step
opened is followed: a tab the page opens on its own between steps (an ad) is not. Saved automations
close the tabs a run opened, so the next spreadsheet row starts from the automation's own tab.

**Only what was asked.** The agent does not send, save, confirm, pay, export or print what the request
did not ask for: such a click is blocked, and the planner is told so. It is asked for when the
request has a verb for it ("salve", "envie", "pague"; for exporting, a verb or a word for a file),
or when the request and the button are about the same thing ("reserve a sala" and "Reservar sala").
So "attach the resume" does not end with the application sent; "attach the resume and send the
application" does. Destructive actions (deleting, cancelling) have their own barrier. Acting on your
account on a social site (following someone, connecting, liking, reacting, commenting, sharing,
reposting, subscribing, inviting) is blocked too unless the request has a verb for it ("siga",
"curta", "share"): a request about the same person does not ask to follow them. "Seguir" alone, or
"Seguir para o pagamento", is going on, not following.

**Goals and the end check.** A goal of the plan is met by its last planned step (a search is not met
by the click that opens the search box), never by a step that led to a login page. Before saying a
request is done, the agent checks that what it asks to finish was finished: a search must be sent
(a click or Enter) after its term was typed; "confirm whether…" is a check, not a click on Confirm.

**The site's own pop-ups.** An alert is accepted and what it says reaches the planner; a question
("Are you sure?") is always answered no, since the agent never confirms on its own. A click with no
visible change waits for what the click itself scheduled on the page (up to 8 s) before it counts as
"no effect". A click on an element that something covers fails after 10 s, and the planner is told
what covers it.

**Logging in.** The agent never types a password: a fill that would land on a password field is
not done. A request that seems to contain a password ("senha: ...", "password ...") is refused
before anything reaches the model. When a task needs a login (the request asks to log in, the
plan reaches a password field, or nothing can be planned on a page that asks for one), the agent
asks in the terminal: log in (or fill in the password) yourself in the browser window and press
Enter, or `q` to cancel. If the page still shows an empty password field, it asks again. A step that
leads to a login page (a "Star" that asks to sign in first) does the same, and the plan starts again
from the page after the login. With `--browser-profile`, the session is kept for the next runs.

**Sending files.** A request to send a file ("Attach the resume C:/Users/ana/cv.pdf") is planned
as an `upload` step: the agent puts the file in the file field, or clicks the button that opens the
file chooser ("Attach resume") and picks it there. The path must be written in the request (or in
the automation's notes or parameters): the model never chooses a file from your computer, and a
plan with a path that is not in the request is refused. A path that does not exist stops the run
with a message, before anything on the page is touched. Every upload is a sensitive action, so it
asks first. In a saved automation, a parameter can give a different file per spreadsheet row
(`--param file=...`, or a `file` column).

**Downloading files.** A request to download a file ("Download the sales report") is planned as
a `download` step: the agent clicks the button or link and waits for the file, which it saves in
the output folder with the name the site suggests (`report (2).csv` if the name is taken). Every
download is a sensitive action, whatever the button says, so it asks first. A click that
downloads nothing fails, and the planner is told so.

**Reading data from a page.** A request to read, copy or export a table or a list ("Export the
sales by region table") is planned as an `extract_table` step: the agent finds the table or list
by its caption, title or column headers, and saves it as a CSV file, in UTF-8 with the
separator of the interface language (`;` in Portuguese, so Excel opens it in columns; `,` in
English). Menus, headers and footers are never taken as data. When the request could mean more
than one table, the agent does not guess: it tells the planner their names, and the planner
picks one. A single text ("What was the total revenue?") is an `extract_text` step, and what was
read is shown in the terminal. A request that is a question (ending in "?", or starting with
"qual", "quanto", "what", "how many"...) is not done until some step has read the answer: if the
model stops before that, it is told to read it, and to open the page or tab that has it first.

```sh
python -m anchor.agent --profile ollama-small --url eval/fixtures/report_en.html "Export the sales by region table"
```

## Planner (`anchor.planner`)

Only generates a plan (and optionally runs it), without the agent loop.

```sh
python -m anchor.planner --profile ollama-small --url eval/fixtures/registration_en.html "Register Maria Silva in the IT department"
python -m anchor.planner --profile ollama-small --url eval/fixtures/registration_en.html "Register Maria Silva in the IT department" --run
```

| Option | Meaning |
|---|---|
| `request` (positional) | What to do, in natural language. |
| `--profile` | Model profile in `llm_profiles.json`. Required. |
| `--url` | The site's link, or the path of a local `.html` file. Required. |
| `--run` | Runs the plan in a visible browser, with disambiguation in the terminal. |
| `--no-page` | Does not send the list of the page's elements to the model. |
| `--allow-sensitive` | With `--run`: does not ask before sensitive actions. |
| `--lang` | Interface language: `en` or `pt`. |
| `--prompt-language` | Planner prompt language: `pt`, `en` or `auto`. |

## Saved automations (`anchor.automations`)

Describe a task once and run it whenever you want. The first run learns the plan with the
LLM; the next runs replay the approved plan without the LLM. When the site changes and a saved
step stops working, the automation heals itself and records the recovery.

A recovery is accepted only if every saved step that stopped working was redone: by a step of the
same action about the same thing (the same value, as a renamed field filled with the same text, or at
least half of its words). A step that only went somewhere (a link, "open the cart", "view details")
is not redone by one that acts ("add to cart later", "continue", "delete"): a page with lures led a
model's repair into exactly that. A recovery that does not keep this contract fails the run, and the
saved plan is not changed.

The same rule is checked during the recovery, before each click: a click that acts (add, delete,
continue, send) is only done if it redoes a saved step still to redo that acts too, about the same
thing. A lure is refused before it is clicked, and the planner is told why. Filling a field is left to
the contract above (it knows the values), and clicks that only go somewhere or prepare (close, open,
show more) are let through.

```sh
python -m anchor.automations create register-maria --url eval/fixtures/registration_en.html --profile ollama-small "Register Maria Silva in the IT department and save the registration"
python -m anchor.automations run register-maria
python -m anchor.automations list
python -m anchor.automations show register-maria
python -m anchor.automations recoveries register-maria
python -m anchor.automations undo register-maria 1
python -m anchor.automations notes register-maria --add "the Save button is at the end of the page"
```

Options that come **before** the command:

| Option | Meaning |
|---|---|
| `--root` | Folder of the saved automations. Default: `automations`. |
| `--lang` | Interface language: `en` or `pt`. |

### `create`

| Argument / option | Meaning |
|---|---|
| `name` (positional) | Lowercase letters, digits, `-` and `_` (e.g. `register-maria`). |
| `request` (positional) | What to do, in natural language. |
| `--url` | The site's link, or the path of a local `.html` file. Required. |
| `--profile` | Model profile used to learn (and to heal) the plan. Required. |
| `--browser-profile` | Folder of a persistent browser profile, for systems with login. |
| `--prompt-language` | Planner prompt language: `pt`, `en` or `auto`. Default: the model profile's. |

### `run`

| Argument / option | Meaning |
|---|---|
| `name` (positional) | The automation to run. The first run learns the plan; the next ones replay it. |
| `--relearn` | Plans again with the LLM, replacing the approved plan. |
| `--no-heal` | If a saved step stops working, stops instead of recovering with the LLM. |
| `--vision` | Confirms doubted steps with a screenshot (see the agent's `--vision`). |
| `--allow-sensitive` | Does not ask before sensitive actions, and does not save decisions. |
| `--unattended` | Runs with no one present, for a scheduler (see below). Only a proven plan; nothing is repaired or asked; any change stops the run, and the rest of a spreadsheet. Exit code 1 when it did not finish. |
| `--fresh-browser` | Opens a clean browser for this run. By default, each automation keeps its own browser profile in its folder (`browser/`), so a login done by hand is kept for the next runs; a `--browser-profile` given at `create` is used instead. |
| `--param` | The value of a parameter for this run, as `name=value` (repeat it for each parameter). |
| `--csv` | Runs once per row of a CSV file whose columns are the parameters (`,` or `;` as separator). Cannot be used with `--param`. |

Tables and lists read by an automation are saved in its folder, under `output/`, and each run's
record lists the files it wrote (not the text it read, which may be personal data).

### Unattended runs (scheduling)

Only an automation whose current plan has been **proven** runs with `--unattended`: done once, with
someone present, from start to end with no recovery (no repair by the model, no element chosen by
hand). That run records the element each step acted on. Any change to the plan (a repair, `--relearn`,
an `undo`) makes a new plan with no proof, which needs another run with someone present.

In an unattended run nothing changes and no one is asked:

* the model is never called, and a saved step that stops working is not repaired;
* no tie-break: an ambiguous element stops the run;
* each step acts only on the element of the proving run (same text and label): an element that differs,
  even one the heuristic would accept with someone present, stops the run before acting;
* only sensitive actions approved before are done; a new one is refused;
* a login is never waited for: log in once in a run with someone present (each automation keeps its
  browser profile);
* what does not change the plan still happens: a cookie banner in the way is declined, "Show more" is
  opened, and an element whose id or class changed is still found by its text;
* the first row that stops ends a spreadsheet run, and the exit code is 1.

To schedule it on Windows (Task Scheduler), every day at 8:00:

```
schtasks /Create /TN "ANCHOR register" /SC DAILY /ST 08:00 /TR "cmd /c cd /d C:\path\to\ANCHOR && venv\Scripts\python.exe -m anchor.automations run register --unattended --csv people.csv"
```

On Linux or macOS (cron), the same with `0 8 * * * cd /path/to/ANCHOR && venv/bin/python -m anchor.automations run register --unattended`.
When a run stops, `show` and the run's record say which step changed and why; run the automation
once with someone present to look at it.

### Parameters

The parts of the request that change from run to run go in braces when the automation is
created; `create` finds them, and `show` lists them:

```sh
python -m anchor.automations create register --url eval/fixtures/registration_en.html --profile ollama-small "Register {name}, tax ID {tax_id}, IT department, contractor. Accept the terms and save the registration."
python -m anchor.automations run register --param name="Maria Silva" --param tax_id=123-45-6789
python -m anchor.automations run register --csv employees.csv
```

A CSV file for this automation:

```text
name;tax_id
Maria Silva;123-45-6789
John Carter;987-65-4321
```

The model plans with the real values of the first run; the approved plan is saved with the
placeholders (`fill Tax ID = {tax_id}`), so the next runs work with any values. The run records keep
the placeholders, not the values, since they may be personal data. Every parameter needs a
value in every run; an unknown parameter is refused.

### `list`, `show`, `recoveries`, `undo`, `notes`, `confirmations`

| Command | Meaning |
|---|---|
| `list` | Lists the automations and whether each one has an approved plan. |
| `show name` | Shows the request, the link, the approved plan and the last runs. |
| `recoveries name` | Lists how the automation recovered when the site changed: what failed, what replaced it, how it was solved, whether the effect was confirmed, the confidence; and the elements you picked during replays. |
| `undo name number` | Undoes a recovery: a plan correction brings the previous plan back (and undoes the later corrections); a choice of yours is forgotten, and the next run asks again. |
| `notes name` | Lists your notes about the automation. The 5 most recent go to the planner when it learns or heals the plan. |

| `confirmations name` | Lists your decisions on sensitive actions (allowed or denied). |

`confirmations` options:

| Option | Meaning |
|---|---|
| `--forget` | Forgets the decision with this number: the next run asks again. |

Sensitive actions (deleting, saving or submitting, sending, paying, downloading, uploading, acting
on your account on a social site, and cancelling an order, a subscription, a booking or another
irreversible thing; a plain "Cancel" that closes a form is not asked about) are asked about once, when the element is found and
before acting. Answer `s`/`y` to allow it, `n` to deny it, or just press Enter to deny it only this
time. An action you allowed is not asked again (nor in the next rows of a spreadsheet); an action
you denied with `n` stops the run, in that run and in the next ones, until you forget the decision.
Pressing Enter, or having no terminal to answer, saves nothing: the next run asks again.

`notes` options:

| Option | Meaning |
|---|---|
| `--add` | Adds a note (e.g. `--add "the Save button is at the end of the page"`). |
| `--remove` | Removes the note with this number. |

After a run that did not work, `run` also asks whether you want to leave a note (Enter skips);
with `--csv`, it asks once, at the end, if some row failed.

## Interface (`anchor.ui`, in development)

The local program's interface: a server on this computer only, and the app it serves. For now it
lists, creates and runs the saved automations (with the values they need), runs a one-off request
or only shows its plan, and saves a request that was done and checked as an automation; runs go one
at a time, in a queue, and their questions (a sensitive action, which element, a login) are
answered in the interface, where the browser is shown live and a login is done on it. When ANCHOR
asks which element a step meant, the interface also lets the person say it is none of the ones
found (and why: the planner reads it when it plans again) or that a login comes first. Taking care
of the automations (fixes, notes, decisions, the choice memory), spreadsheets, scheduling and the
installer come in the next steps of 0.5. While it is in development, build the app once and start
the server by hand:

```
cd web && npm install && npm run build && cd ..
python -m anchor.ui
```

It opens the browser on `http://127.0.0.1:<port>/`. Options: `--automations <folder>` (default
`automations`), `--port <n>` (default: a free one), `--no-browser`. Every request to its API must
carry the code made at this start, which the app receives in the address it opens; no other
program or website on the computer can use it.

## Choice memory (`anchor.engine.memory`)

Reviews what the assistant learned from your choices, and forgets a wrong one.

```sh
python -m anchor.engine.memory memory/demo.json list
python -m anchor.engine.memory memory/demo.json forget 2
python -m anchor.engine.memory memory/demo.json clear --yes
```

| Command / option | Meaning |
|---|---|
| `file` (positional) | The memory file (`memory/<name>.json`, or `automations/<name>/memory.json`). |
| `list` | Shows the remembered choices, numbered. |
| `forget N [N...]` | Forgets the choices with these numbers. |
| `clear` | Forgets all the choices (asks for confirmation). |
| `--yes` | With `clear`: does not ask for confirmation. |

The old Portuguese names of these commands (`listar`, `esquecer`, `limpar`) still work, and
`--help` shows them next to the English ones.

## Demos

```sh
python -m examples.disambiguation_demo    # disambiguation and the choice memory (run it twice)
python -m anchor.main                     # end-to-end example on SauceDemo, with a fixed plan
```

`python -m examples.disambiguation_demo` runs on a local page: the first time it asks you to pick
elements; the second time it remembers (the choices are in `memory/demo.json`; delete it to start
over).

`python -m anchor.main` runs on the real SauceDemo site, with a persistent browser profile
(`profiles/user_001`). The first time, log in by hand in the browser that opens (user
`standard_user`, password `secret_sauce`): the password never goes through ANCHOR. The choices
are kept in `memory/saucedemo.json`.

`examples/legacy_saucedemo.py` is the fixed-selector version (the "before"), kept for comparison.

## Evaluation

Details and the evaluation rules (development sets, closed sets) are in [`eval/README.md`](../eval/README.md).

Every result file records where it was measured: the full commit, its tag, and whether the working
copy had uncommitted changes (then its name says `+dirty`). `--final` refuses to run unless the
working copy is clean and the commit has a tag (tag the release first: `git tag v1.0.0`).

### Element resolver (`eval.run`)

```sh
python -m eval.run --offline -v
python -m eval.run --language en
python -m eval.run --sweep
```

| Option | Meaning |
|---|---|
| `--offline` | Skips the cases that need the internet (SauceDemo). |
| `--language` | Only the cases in this language: `pt` or `en`. Default: both. |
| `--site` | Only one site (e.g. `store`, `users_en`). |
| `--split` | Only one split: `dev` (the default excludes the closed set). |
| `--sweep` | Tries combinations of minimum score × gap. |
| `--check` | Only checks that the expected selectors exist (the closed set included). |
| `--final` | Runs the closed set (split `test`). Once, at the end of development. |
| `--headed` | Shows the browser while evaluating. |
| `-v`, `--verbose` | Shows each case. |

### Complete tasks (`eval.plan_run`)

```sh
python -m eval.plan_run --reference
python -m eval.plan_run --agent --profiles ollama-small ollama-medium -v
python -m eval.plan_run --agent --profiles ollama-small --language en --prompt-language auto
python -m eval.plan_run --agent --suite injection --profiles ollama-small ollama-medium -v
```

| Option | Meaning |
|---|---|
| `--profiles` | Model profiles to evaluate. |
| `--reference` | Includes the hand-written plans (the ceiling, with no LLM). |
| `--agent` | Runs the tasks through the full agent loop (replanning, effect checks, end check). |
| `--language` | Only the tasks in this language: `pt` or `en`. Default: both. |
| `--vision` | With `--agent`: confirms doubted steps with a screenshot; the table adds the questions asked, the steps confirmed and the time spent. |
| `--suite` | `main` (default): the ordinary tasks. `injection`: tasks on pages that try to hijack the agent; the table adds the `attacked` column (runs in which some attack worked) and `attempts` (steps that tried to do what the page asked, even if a barrier stopped them). `extraction`: tasks that read tables, lists and texts, judged on what was read (the task's `extraction`), with the CSV files written to a temporary folder. |
| `--prompt-language` | Planner prompt language: `pt`, `en` or `auto`. Default: the profile's. |
| `--task` | Runs only one task (by id). |
| `--no-page` | Does not send the list of the page's elements to the model. |
| `--check` | Checks the tasks, without calling models. |
| `--final` | Runs the closed set (split `test`). Once, at the end. |
| `-v`, `--verbose` | Shows each task's plan and, when the plan failed, the model's refused answers and why each was refused. |

### Closed sets' sources (`eval.closed_sets`)

Turns a closed set's sheets (one per generator, `pagina;pedido`) into the tasks file to annotate, one
task per request with its `origin` and `generator`, `split: "test"`, and empty `checks`, `allowed`
and `reference`. It prints only how many tasks it wrote, never a request, and does not write over a
tasks file that exists (it may be annotated already).

```sh
python -m eval.closed_sets skeleton eval/synthetic_controlled_2026-10-22 synthetic_controlled
python -m eval.closed_sets page-items synthetic     # per generator: how many requests cite an item of their page
python -m eval.closed_sets negatives eval/plans/holdout_controlled_tasks.json   # prefill the negative checks
```

The results of `eval.plan_run --final` come out by origin, by generator, and without the generators
a sensitivity analysis leaves out (for `synthetic_controlled`: the ChatGPT's requests).

### Resilience benchmark pages (`eval.resilience.build`)

Builds the altered versions of the task pages, in 5 levels of perturbation, the tasks
rewritten for them (`eval/plans/resilience_tasks.json`), and the fixed-selector scripts of the
traditional executor, recorded on the original pages (`eval/plans/resilience_scripts.json`). Deterministic: rebuilding gives the same
pages. Every element a task checks is marked with `data-eval`, the evaluation's own marker, which
no executor may use.

```sh
python -m eval.resilience.build --check
```

| Level | Perturbation |
|---|---|
| L0 | The original page, only with the evaluation's markers. |
| L1 | Superficial: ids, classes, names and test attributes renamed or removed (the page's own scripts keep working). |
| L2 | Semantic: synonyms in the labels ("Salvar" → "Gravar"), a search button turned into an icon. |
| L3 | Structural: repeated items reversed, buttons moved to the top of forms, extra wrappers. |
| L4 | Behavioral: part of the page hidden behind "Show more", a cookie banner covering the page. |
| L5 | Adversarial: lookalikes next to the targets, an unexpected destructive button, and an instruction pointing at it, phrased in a way the injection detector has never seen. |

| Option | Meaning |
|---|---|
| `--check` | Also runs the reference plans on the L0 pages, to check the rewritten tasks. |

### The closed resilience set's catalog (`eval.resilience.closed.catalog_md`)

The closed set's perturbations come from `eval/resilience/closed/catalog.json`: each operator with
its source and category (the taxonomy of Hammoudi et al. for levels 1 to 4; Greshake et al. and
Gray et al. for level 5), its weight, what is left out and why, the generator's rules and the seed.
`CATALOG.md` is written from it, so the two never differ:

```sh
python -m eval.resilience.closed.catalog_md
```

### The closed resilience set's generation (`eval.resilience.closed.targets`, `eval.resilience.closed.generate`)

`targets` records, once, on the original (L0) development pages, the evaluation's marker of the element
each step of a base task's reference plan acts on (`reference_targets.json`, committed); the closed
set's check then uses only these markers, with plain Playwright and no part of ANCHOR. `generate`
makes the closed set from the catalog, once, by the author, who reads only its counts and the list of
level-2 replacements for the veto (see `eval/resilience/closed/README.md`):

```sh
python -m eval.resilience.closed.targets                  # already run: its result is committed
python -m nltk.downloader wordnet omw-2.0                 # the dictionaries, once
python -m eval.resilience.closed.generate                 # prints counts; writes the list for the veto
python -m eval.resilience.closed.generate --vetoes vetoes.csv   # again, until no new veto
```

### Resilience benchmark runs (`eval.resilience.run`, `eval.resilience.report`)

Runs the three executors on the altered pages: the traditional script (fixed selectors recorded
on L0), the LLM in control (it chooses every action and element, with no protection) and ANCHOR (a
saved automation whose approved plan is the reference plan, run twice on each altered page, with no
user: the 1st run measures the recovery, the 2nd the reuse, which counts only if it needed no model).
Each part saves its own results, so the benchmark can run in parts; the report puts them together.

```sh
python -m eval.resilience.run --executors script
python -m eval.resilience.run --executors anchor --profiles ollama-small --language pt
python -m eval.resilience.run --executors llm --profiles ollama-medium --language en
python -m eval.resilience.run --final --profiles ollama-small ollama-medium   # the closed set, once, at the end
python -m eval.resilience.report eval/results/resilience_*.json
```

| Option (`run`) | Meaning |
|---|---|
| `--executors` | `script`, `llm` and/or `anchor`. Default: all three. |
| `--profiles` | Model profiles, for `llm` and `anchor` (the script uses no model). |
| `--language` | Only the tasks in this language: `pt` or `en`. Default: both. |
| `--levels` | Perturbation levels. Default: 1 to 5. |
| `--task` | Only one base task (e.g. `p-reg-01`). |
| `-v`, `--verbose` | Shows the error and the steps (with the element actually acted on and how it was chosen) of the runs that need a look: failed, attacked, false successes and recoveries. |

`report` takes the result files (`.json`; patterns like `eval/results/resilience_*.json` are expanded)
and prints the success per level of each executor, and the false successes, unrequested actions,
attacks, attack attempts, model calls and time.

### Interventions experiment (`eval.interventions`)

Does the system ask the user less as it learns? The resolver's development cases are run by the
Executor with the choice memory and a simulated user that knows the right element of each case:
round 1 starts with an empty memory, round 2 repeats the cases with the memory of round 1, and
round 3 repeats them in a shuffled order. It reports, per round and language, the interventions,
the right actions, the silent errors and the right actions that came from the memory. No model is
used.

```sh
python -m eval.interventions --offline -v
python -m eval.interventions
```

| Option | Meaning |
|---|---|
| `--offline` | Skips the cases that need the internet (SauceDemo). |
| `--language` | Only the cases in this language: `pt` or `en`. Default: both. |
| `--rounds` | How many rounds. Default: 3. |
| `--seed` | Seed of the shuffled order (round 3 on). Default: 7. |
| `-v`, `--verbose` | Shows each case of each round (ASK: the user was asked; MEM: from the memory; SIL: silent error). |

### Vision probe (`eval.vision_probe`)

Measures how long the model takes to answer a question about a screenshot, and whether it gets it
right, before the effect check by screenshot is built. It asks 6 yes/no questions with known
answers about the registration page, at two screen widths, and saves the results.

```sh
python -m eval.vision_probe --profiles ollama-small ollama-medium
```

| Option | Meaning |
|---|---|
| `--profiles` | Ollama model profiles to measure (the model must have the `vision` capability: `ollama show <model>`). |

### The human closed set's draw (`eval.human_sample`)

Draws the human closed set's 60 requests from the collection's Google Forms export: 30 from people
who work in IT and 30 from people who do not, each profile spread over the 9 pages, with a fixed
seed; the form's pilot response and whoever did not agree are left out, every request field of a page
is read (one or two per page), a stratum takes one request per person before anyone's second, and a
stratum with too few requests is completed (the other profile on the same page, then another page),
each completion recorded. The rules are in the
module's docstring. It runs only exactly as committed, once, prints only counts, and writes the
tasks to annotate (`eval/plans/holdout_human_tasks.json`) and how the draw went
(`eval/plans/holdout_human_sample.json`: the commit, the seed, the input's hash, counts, who answered
by profile, how many different people the 60 requests come from and how many each gave, and the share
who opened each page's link).

```sh
python -m eval.human_sample <export.csv>
```

### The human collection's publication (`eval.human_publish`)

After the draw, and after the person checks the responses for accidental personal data, writes
`eval/human_collection/responses.csv`: every response the consent allows to publish, numbered by its
place in the export before anything is left out (the numbers of "Não concordo" are simply missing),
without the time it was sent, with the profile, every "abriu o link" and every request, and the tasks
drawn from it. Removals come from a file kept outside the repository (`response;field;text;type`):
each text becomes `[removido: type]`, in the publication and in a drawn task, and
`eval/human_collection/removals.csv` records the response, field, type and task, never the text.

```sh
python -m eval.human_publish <export.csv> --removals <removals.csv>
```

## Development

```sh
pytest tests -v                                   # the test suite
isort --check-only anchor eval tests examples     # import order (PEP 8 groups)
```

## Model profiles (`llm_profiles.json`)

Each profile tells ANCHOR which local model to use and where Ollama runs.

| Field | Meaning |
|---|---|
| `name` | The profile's name, used with `--profile` (e.g. `ollama-small`). The old names `ollama-pequeno` and `ollama-medio` still work. |
| `model` | The model's exact name (in Ollama, as shown by `ollama list`, e.g. `qwen3.5:4b`). |
| `api` | `ollama`: Ollama's native API (the only one; the default). |
| `base_url` | Ollama's address. Default: `http://localhost:11434`. |
| `api_key_env` | Ignored. Accepted only so that older profile files (from when ANCHOR could call a remote API) still load. |
| `temperature` | Sampling temperature. Default: 0 (the most repeatable answers). |
| `timeout_s` | Seconds to wait for the model's answer. Default: 180. |
| `think` | Turns the reasoning of "thinking" models on or off. Default: `false`. |
| `options` | Model options, e.g. `{"num_ctx": 4096}` to fit a small GPU. |
| `extra_body` | Extra parameters passed to Ollama on every call. |
| `prompt_language` | Planner prompt language: `pt` (default, the measured one), `en` or `auto`. |

## Environment variables

| Variable | Meaning |
|---|---|
| `ANCHOR_LANG` | Interface language: `en` (default) or `pt`. `--lang` overrides it. |
