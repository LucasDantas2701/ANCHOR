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

For the paid OpenAI profile, set the key in an environment variable, never in a file. On
Windows: `setx OPENAI_API_KEY "your-key"`, then open a new terminal.

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
| `--allow-sensitive` | Does not ask before sensitive actions. By default, before deleting, saving or submitting, sending, paying, downloading or uploading, the agent shows the element and asks; a denial stops the run. |
| `--output-dir` | Where tables and lists read by the agent are saved, one CSV file each (never overwritten). Default: `output`. |
| `--lang` | Interface language: `en` (default) or `pt`. Overrides `ANCHOR_LANG`. |
| `--prompt-language` | Planner prompt language: `pt` (default, the measured one), `en`, or `auto` (follows the request). |

**Reading data from a page.** A request to read, copy or export a table or a list ("Export the
sales by region table") is planned as an `extract_table` step: the agent finds the table or list
by its caption, title or column headers, and saves it as a CSV file, in UTF-8 with the
separator of the interface language (`;` in Portuguese, so Excel opens it in columns; `,` in
English). Menus, headers and footers are never taken as data. When the request could mean more
than one table, the agent does not guess: it tells the planner their names, and the planner
picks one. A single text ("What was the total revenue?") is an `extract_text` step, and what was
read is shown in the terminal.

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
| `--param` | The value of a parameter for this run, as `name=value` (repeat it for each parameter). |
| `--csv` | Runs once per row of a CSV file whose columns are the parameters (`,` or `;` as separator). Cannot be used with `--param`. |

Tables and lists read by an automation are saved in its folder, under `output/`, and each run's
record lists the files it wrote (not the text it read, which may be personal data).

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

Sensitive actions (deleting, saving or submitting, sending, paying, downloading, uploading, and
cancelling an order, a subscription, a booking or another irreversible thing; a plain "Cancel"
that closes a form is not asked about) are asked about once, when the element is found and
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

## Development

```sh
pytest tests -v                                   # the test suite
isort --check-only anchor eval tests examples     # import order (PEP 8 groups)
```

## Model profiles (`llm_profiles.json`)

Each profile tells ANCHOR where the model is and how to call it. The file never stores keys.

| Field | Meaning |
|---|---|
| `name` | The profile's name, used with `--profile` (e.g. `ollama-small`). The old names `ollama-pequeno` and `ollama-medio` still work. |
| `model` | The model's exact name (in Ollama, as shown by `ollama list`, e.g. `qwen3.5:4b`). |
| `api` | `ollama` (Ollama's native API, recommended for local models) or `openai` (the OpenAI format; default). |
| `base_url` | The server's address (e.g. `http://localhost:11434` for Ollama); empty for the OpenAI API. |
| `api_key_env` | The **name** of the environment variable holding the key (e.g. `OPENAI_API_KEY`); `null` for local models. |
| `temperature` | Sampling temperature. Default: 0 (the most repeatable answers). |
| `timeout_s` | Seconds to wait for the model's answer. Default: 180. |
| `think` | `ollama` API only: turns the reasoning of "thinking" models on or off. Default: `false`. |
| `options` | `ollama` API only: model options, e.g. `{"num_ctx": 4096}` to fit a small GPU. |
| `extra_body` | Extra parameters passed to the server on every call. |
| `prompt_language` | Planner prompt language: `pt` (default, the measured one), `en` or `auto`. |

## Environment variables

| Variable | Meaning |
|---|---|
| `ANCHOR_LANG` | Interface language: `en` (default) or `pt`. `--lang` overrides it. |
| `ANCHOR_LINKEDIN` | Set to `1` to run the LinkedIn tests (disabled by default: the site forbids automation). The old name `SMART_RPA_LINKEDIN` still works. |
| `OPENAI_API_KEY` | The OpenAI key, if you use the `openai` profile (the name is set by `api_key_env` in `llm_profiles.json`). |
