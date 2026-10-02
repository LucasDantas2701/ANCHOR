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
python -m anchor.agent --profile ollama-small --url eval/fixtures/registration.html "cadastre a Maria Silva no TI e salve"
```

| Option | Meaning |
|---|---|
| `request` (positional) | What to do, in natural language (Portuguese or English). |
| `--profile` | Model profile in `llm_profiles.json` (e.g. `ollama-small`, `ollama-medium`). Required. |
| `--url` | The site's link, or the path of a local `.html` file. Required. |
| `--memory` | File of the choice memory. Default: `memory/agent.json`. |
| `--browser-profile` | Folder of a persistent browser profile, for systems with login (e.g. `profiles/user_001`). |
| `--max-attempts` | Failures before the run is cancelled. Default: 3. |
| `--lang` | Interface language: `en` (default) or `pt`. Overrides `ANCHOR_LANG`. |
| `--prompt-language` | Planner prompt language: `pt` (default, the measured one), `en`, or `auto` (follows the request). |

## Planner (`anchor.planner`)

Only generates a plan (and optionally runs it), without the agent loop.

```sh
python -m anchor.planner --profile ollama-small --url eval/fixtures/registration.html "cadastre a Maria Silva no TI"
python -m anchor.planner --profile ollama-small --url eval/fixtures/registration.html "cadastre a Maria Silva no TI" --run
```

| Option | Meaning |
|---|---|
| `request` (positional) | What to do, in natural language. |
| `--profile` | Model profile in `llm_profiles.json`. Required. |
| `--url` | The site's link, or the path of a local `.html` file. Required. |
| `--run` | Runs the plan in a visible browser, with disambiguation in the terminal. |
| `--no-page` | Does not send the list of the page's elements to the model. |
| `--lang` | Interface language: `en` or `pt`. |
| `--prompt-language` | Planner prompt language: `pt`, `en` or `auto`. |

## Saved automations (`anchor.automations`)

Describe a task once and run it whenever you want. The first run learns the plan with the
LLM; the next runs replay the approved plan without the LLM. When the site changes and a saved
step stops working, the automation heals itself and records the recovery.

```sh
python -m anchor.automations create register-maria --url eval/fixtures/registration.html --profile ollama-small "cadastre a Maria Silva no TI e salve"
python -m anchor.automations run register-maria
python -m anchor.automations list
python -m anchor.automations show register-maria
python -m anchor.automations recoveries register-maria
python -m anchor.automations undo register-maria 1
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

### `list`, `show`, `recoveries`, `undo`

| Command | Meaning |
|---|---|
| `list` | Lists the automations and whether each one has an approved plan. |
| `show name` | Shows the request, the link, the approved plan and the last runs. |
| `recoveries name` | Lists how the automation recovered when the site changed: what failed, what replaced it, how it was solved, whether the effect was confirmed, the confidence; and the elements you picked during replays. |
| `undo name number` | Undoes a recovery: a plan correction brings the previous plan back (and undoes the later corrections); a choice of yours is forgotten, and the next run asks again. |

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
```

| Option | Meaning |
|---|---|
| `--profiles` | Model profiles to evaluate. |
| `--reference` | Includes the hand-written plans (the ceiling, with no LLM). |
| `--agent` | Runs the tasks through the full agent loop (replanning, effect checks, end check). |
| `--language` | Only the tasks in this language: `pt` or `en`. Default: both. |
| `--prompt-language` | Planner prompt language: `pt`, `en` or `auto`. Default: the profile's. |
| `--task` | Runs only one task (by id). |
| `--no-page` | Does not send the list of the page's elements to the model. |
| `--check` | Checks the tasks, without calling models. |
| `--final` | Runs the closed set (split `test`). Once, at the end. |
| `-v`, `--verbose` | Shows each task's plan. |

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
