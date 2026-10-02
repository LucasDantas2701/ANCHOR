<a id="readme-top"></a>

<!-- PROJECT SHIELDS -->
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![License][license-shield]][license-url]
[![Python][python-shield]][python-url]

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <!-- Logo: add images/logo.png and uncomment the line below. -->
  <!-- <a href="https://github.com/LucasDantas2701/ANCHOR"><img src="images/logo.png" alt="Logo" width="80" height="80"></a> -->

  <h3 align="center">ANCHOR</h3>

  <p align="center">
    <b>A</b>daptive <b>N</b>atural-language <b>C</b>ontrol with <b>H</b>uman <b>O</b>versight and <b>R</b>ecovery
    <br />
    Web automation from plain-language requests, with a human in the loop.
    <br />
    <br />
    <a href="#getting-started"><strong>Get started »</strong></a>
    <br />
    <br />
    <a href="https://github.com/LucasDantas2701/ANCHOR/issues/new?labels=bug">Report a bug</a>
    &middot;
    <a href="https://github.com/LucasDantas2701/ANCHOR/issues/new?labels=enhancement">Request a feature</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
        <li><a href="#how-it-works">How It Works</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
        <li><a href="#quick-example">Quick Example</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#evaluation">Evaluation</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#feedback">Feedback</a></li>
    <li><a href="#development">Development</a></li>
    <li><a href="#responsible-use">Responsible Use</a></li>
    <li><a href="#known-limitations">Known Limitations</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>



<!-- ABOUT THE PROJECT -->
## About The Project

<!-- Screenshot or GIF of the agent at work: add images/demo.gif and uncomment the line below. -->
<!-- [![ANCHOR at work][product-screenshot]](https://github.com/LucasDantas2701/ANCHOR) -->

Traditional RPA depends on fixed selectors, written by a developer:

```python
page.locator('[data-test="add-to-cart"]').click()
```

It works while the page stays the same, and breaks as soon as it changes. Each automation also
needs a developer to create and maintain it, which keeps it away from the person who actually
knows the task.

ANCHOR lets a non-technical person describe the task in plain language, give the site's link,
and let the system do the rest:

```text
"Cadastre a Maria Silva, CPF 123.456.789-00, no TI, contrato PJ, aceite os termos e salve"
```

What sets it apart is **who controls what**:

* **The LLM only plans.** It turns the request into goals and steps, using the names of the
  elements on the page. It never clicks anything directly.
* **A heuristic finds each element**, without spending tokens, and refuses when it is not sure.
* **The user breaks ties.** When the heuristic refuses, the candidates are numbered on the page,
  and the user picks one, or clicks the right element.
* **Choices are remembered** and reused on the next runs, so interventions go down over time.
* **Every action is verified**: the agent checks that the field got the value, that the page
  reacted, and that no error message appeared, and only declares the end when all goals are met.
* **Safety barriers**: destructive actions the request did not mention (close, delete, hide...)
  are blocked, and plans that do not cover the request are sent back to the model.
* **Local models.** The planner runs on small local models (Qwen 3.5 via Ollama), so requests
  and page contents do not leave the computer or the company network. Logins use persistent
  browser profiles: credentials never go through the AI.

> **Status:** version 0.3.0 in development. The engine, the planner, the agent loop, effect
> verification and goals are done; saved automations, confirmation of sensitive actions and the
> frontend are next. See the [roadmap](#roadmap) and the [changelog](CHANGELOG.md).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

* [![Python][python-shield]][python-url]
* [![Playwright][playwright-shield]][playwright-url]
* [![Ollama][ollama-shield]][ollama-url]

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### How It Works

```text
Request in plain language + link
        │
        ▼
LLM plans goals and steps ──► does the plan cover the request? ── no ──► back to the LLM
        │ yes
        ▼
For each step:
   destructive action the request did not ask for? ── yes ──► blocked
        │ no
        ▼
   Memory: has the user chosen this element before? ── yes ──┐
        │ no                                                  │
        ▼                                                     │
   Perception + resolver rank the candidates                  │
        │                                                     │
   Confident? ── no ──► the user picks (number or click) ─────┤
        │ yes                                                 │
        ▼                                                     ▼
   Playwright performs the action ◄───────────────────────────┘
        │
        ▼
   Effect check: value in the field? page reacted? error message?
        │                                 │
       ok                          failed (3 failures cancel)
        │                                 │
        ▼                                 ▼
   page or pop-up changed? ── yes ──► LLM replans with what happened
        │ no
        ▼
End of plan ──► LLM checks whether anything is left ──► all goals met? ──► done
```

What the model reads and what the user reads are separate, each with its own language: the
planner prompt is in Portuguese by default (the measured one) or English; the interface is in
English by default or Portuguese.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- GETTING STARTED -->
## Getting Started

### Prerequisites

* Python 3.10 or newer
* [Ollama](https://ollama.com), to run the planner locally (free). The engine and the
  disambiguation demo work without it.

### Installation

1. Clone the repository
   ```sh
   git clone https://github.com/LucasDantas2701/ANCHOR.git
   cd ANCHOR
   ```
2. Create a virtual environment and install the dependencies
   ```sh
   python -m venv venv
   venv\Scripts\activate            # Windows (Linux/macOS: source venv/bin/activate)
   pip install -r requirements.txt
   playwright install chromium
   ```
3. Download the models (the names go in `llm_profiles.json`; check them with `ollama list`)
   ```sh
   ollama pull qwen3.5:4b
   ollama pull qwen3.5:9b
   ```
4. Check that everything works
   ```sh
   pytest tests -v
   ```

### Quick Example

The repository comes with local test pages, so you can try it without touching a real site:

```sh
python -m anchor.agent --profile ollama-small --url eval/fixtures/registration.html "cadastre a Maria Silva, CPF 123.456.789-00, no TI, contrato PJ, aceite os termos e salve"
```

The browser opens, the agent plans and runs each step, asks in the terminal when it is not sure,
and at the end shows the result: steps, model calls, replans, failures, user interventions,
tokens and time.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- USAGE -->
## Usage

The main commands are below; **every** command and option is in the
[command reference](docs/COMMANDS.md).

**Run a request end to end** (plan, execution, replanning and end):

```sh
python -m anchor.agent --profile ollama-small --url <link or .html file> "<request>"
```

* `--memory memory/<name>.json` chooses where the choices are remembered (default `memory/agent.json`).
* `--browser-profile profiles/<name>` uses a persistent browser profile, for systems with login:
  log in by hand once, and the session stays on your computer.
* `--lang pt` shows the messages in Portuguese (or set `ANCHOR_LANG=pt`).
* `--prompt-language` chooses the planner prompt's language: `pt` (default), `en`, or `auto` (it
  follows the request). Requests can be in English or Portuguese either way: the default
  Portuguese prompt did better than the English one on the English tasks too.

**Save an automation** and run it whenever you want. The first run learns the plan with the LLM;
the next ones replay the approved plan without the LLM, much faster:

```sh
python -m anchor.automations create register-maria --url eval/fixtures/registration.html --profile ollama-small "cadastre a Maria Silva, CPF 123.456.789-00, no TI, contrato PJ, aceite os termos e salve"
python -m anchor.automations run register-maria       # 1st time: learns; then: replays
python -m anchor.automations list
python -m anchor.automations show register-maria      # approved plan and last runs
python -m anchor.automations run register-maria --relearn
```

If the site changes and a saved step no longer works, the automation **heals itself**: the LLM
plans the rest from the page as it is now and, if the run succeeds, the saved plan is corrected.
Every recovery is recorded, and you can review it and undo it:

```sh
python -m anchor.automations recoveries register-maria   # what failed, what replaced it, how, confidence
python -m anchor.automations undo register-maria 1       # bring the previous plan back
python -m anchor.automations run register-maria --no-heal
```

**Only generate a plan**, and optionally run it:

```sh
python -m anchor.planner --profile ollama-small --url eval/fixtures/registration.html "cadastre a Maria Silva no departamento de TI"
python -m anchor.planner --profile ollama-small --url eval/fixtures/registration.html "cadastre a Maria Silva no departamento de TI" --run
```

**See the disambiguation and the memory at work** (run it twice: the first time it asks, the
second time it remembers):

```sh
python -m examples.disambiguation_demo
```

**Review what the assistant learned**, and forget a wrong choice:

```sh
python -m anchor.engine.memory memory/demo.json list
python -m anchor.engine.memory memory/demo.json forget 2
python -m anchor.engine.memory memory/demo.json clear
```

**Model profiles** live in `llm_profiles.json`, one per model. The file never stores keys:
`api_key_env` is the name of the environment variable holding the key. For Ollama, use the native
API (`"api": "ollama"`), which turns off the reasoning of "thinking" models (`"think": false`) and
reduces the context (`"options": {"num_ctx": 4096}`) to fit a small GPU:

```json
{
  "name": "ollama-small",
  "model": "qwen3.5:4b",
  "api": "ollama",
  "base_url": "http://localhost:11434",
  "think": false,
  "options": {"num_ctx": 4096},
  "api_key_env": null
}
```

To see whether the model runs on the GPU or the CPU: `ollama ps` (column `PROCESSOR`). An OpenAI
profile is also supported (paid): set the key with `setx OPENAI_API_KEY "your-key"` on Windows
and fill in the model of the `openai` profile.

The old Portuguese options (`--perfil`, `--memoria`, `--perfis`...) and profile names
(`ollama-pequeno`, `ollama-medio`) still work.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- EVALUATION -->
## Evaluation

```sh
python -m eval.run --offline -v                                       # element resolver, local pages
python -m eval.run --sweep                                            # tries threshold combinations
python -m eval.plan_run --reference                                   # hand-written plans (ceiling)
python -m eval.plan_run --agent --profiles ollama-small ollama-medium -v   # complete tasks, full agent
```

Every result is saved with the version and the commit. The closed test sets (holdout) only run
with `--final`, once, at the end of development. Details in [`eval/README.md`](eval/README.md).

**Element resolver** — development set, 60 cases per language on 7 pages (6 local pages and
SauceDemo), version 0.3.0 in development:

| Metric | Portuguese | English |
|---|---|---|
| Right element first (recall@1) | 88.3% | 91.7% |
| Right element among the first 5 (recall@5) | 91.7% | 96.7% |
| The Executor decides and gets it right | 81.7% | 86.7% |
| The Executor decides and gets it wrong (silent error) | 1.7% | 5.0% |
| The Executor refuses and asks the user | 16.7% | 8.3% |

**Complete tasks** — 15 development tasks per language, on local pages, through the full agent
loop, with no human help and the default (Portuguese) planner prompt, version 0.3.0 in development
(i7-7700HQ, 16 GB RAM, GTX 1050 Ti 4 GB):

| Model (Ollama) | Requests | Tasks done | Done with no unrequested step | Premature ends |
|---|---|---|---|---|
| Qwen 3.5, 4B | Portuguese | 93% | 87% | 0 |
| Qwen 3.5, 4B | English | 80% | 67% | 0 |
| Qwen 3.5, 9B | Portuguese | 93% | 80% | 0 |
| Qwen 3.5, 9B | English | 93% | 87% | 0 |

A task takes about 35 s with the 4B model and 55 s with the 9B one.

These are development numbers: the code and the prompt were tuned looking at these cases. The
final numbers will come from the closed sets.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ROADMAP -->
## Roadmap

- [x] **0.1** — Engine: page perception, heuristic element resolver, executor, user
  disambiguation, choice memory, persistent browser profiles, reproducible evaluation
- [x] **0.2** — LLM planner (local models via Ollama) and the agent loop with replanning; fixes
  from tests on real sites (pop-ups, Enter-only searches, loops, destructive actions)
- [ ] **0.3** — Reliability and saved automations
    - [x] Effect verification of each action, goals, and checking the plan against the request
    - [x] English translation, with the planner prompt in Portuguese or English
    - [x] Saved automations that **heal themselves**: when a saved plan breaks and is recovered,
      the fix is kept, with a reviewable (and undoable) record of what changed
    - [ ] Parameters and runs from a spreadsheet, and the user's notes after a failed run
    - [ ] Confirmation of sensitive actions (delete, send, save, download, upload, pay)
    - [ ] Defense against instructions injected by page content
    - [ ] Screenshot analysis by a vision model, when the other checks disagree
    - [ ] Intervention experiment with a simulated user
    - [ ] Resilience benchmark: changed versions of the pages, comparing fixed-selector scripts,
      an LLM-in-control agent and ANCHOR
- [ ] **0.4** — Uploads, downloads, new tabs, data extraction and iframes
- [ ] **0.5** — Local frontend (runs on your computer, opens in the browser), with a "Run"
  button for each saved automation
- [ ] **1.0** — Evaluated version: final runs on the closed sets

See the [changelog](CHANGELOG.md) for what changed in each version, and the
[open issues](https://github.com/LucasDantas2701/ANCHOR/issues) for known problems.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- FEEDBACK -->
## Feedback

Feedback is very welcome, especially from real use. Please
[open an issue](https://github.com/LucasDantas2701/ANCHOR/issues) with:

1. the request you typed and the site (or the kind of system) you ran it on;
2. what you expected and what happened;
3. the terminal output (remove any personal data first);
4. your setup: operating system, model profile and, if you know it, your GPU.

Suggestions and ideas are welcome as issues too. The [license](#license) does not allow
modifying or redistributing the code, so pull requests cannot be accepted for now.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- DEVELOPMENT -->
## Development

```sh
pytest tests -v                                   # the test suite
isort --check-only anchor eval tests examples     # import order (PEP 8 groups)
```

The tests in `tests/real_sites/` (LinkedIn) are disabled by default, because the site's terms of
use forbid automation; set `ANCHOR_LINKEDIN=1` to run them.

```text
ANCHOR/
├── anchor/
│   ├── agent/                     # the agent loop: plan, execution, effect checks, replanning, end
│   ├── planner/                   # LLM: request → goals and steps (profiles, prompt, validation)
│   ├── engine/
│   │   ├── element_resolver/      # perception (index_script.js) + ranking
│   │   ├── action_executor/       # validation and execution of actions
│   │   ├── disambiguation/        # the user's disambiguation (terminal; contract for the frontend)
│   │   └── memory/                # choice memory + review commands
│   ├── browser/                   # persistent profiles, session and login
│   ├── i18n.py                    # interface messages (English and Portuguese)
│   ├── main.py                    # end-to-end example on SauceDemo, with a fixed plan
│   └── automations/               # saved automations: learn once, replay, heal
├── eval/                          # evaluation: test pages, cases, tasks, results, closed sets
├── docs/COMMANDS.md               # the complete command reference
├── examples/                      # demos (and legacy_saucedemo.py, fixed selectors: the "before")
├── tests/
├── profiles/                      # browser profiles (not in Git)
├── memory/                        # remembered choices (not in Git)
└── llm_profiles.json              # model profiles (no keys)
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- RESPONSIBLE USE -->
## Responsible Use

ANCHOR is a general-purpose tool. **Whoever uses it is responsible for what it does**, as they
would be if they performed the same actions by hand. Before automating a site:

* **Respect the site's terms of use.** Many forbid automation (LinkedIn, for example), and the
  account used may be restricted. The project's evaluation uses only its own pages and sites
  that allow automation.
* **Respect data-protection laws** (such as the LGPD in Brazil) **and your company's rules**:
  automate only what you are allowed to do by hand.
* **Review sensitive actions.** The system blocks destructive actions the request did not
  mention and, from version 0.3.0 on, asks for confirmation before deleting, sending, saving,
  downloading, uploading files or paying.
* **Keep the browser profiles (`profiles/`) on your computer.** They hold the systems' sessions
  and work like passwords; they are kept out of Git.

The project does not include, and will not include, features aimed at abuse, such as solving
CAPTCHAs, creating accounts in bulk or scraping data at scale. With a local model (Ollama),
requests and page contents do not leave the computer or the company network.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- KNOWN LIMITATIONS -->
## Known Limitations

* Text matching is word-based, with a synonym dictionary; there is no real semantics. Data
  extraction ("the price of product X") is the weakest point.
* Iframes and closed shadow DOM are not read.
* When the heuristic is wrong with confidence (a silent error), the user is not asked.
* Unattended runs stop when there is an ambiguity, until the memory learns the answer.
* The English planner prompt is a translation that was not tuned; on English requests, the default
  Portuguese prompt does better, so it stays the default.
* In English, the resolver gets more elements right first but also makes more silent errors,
  mostly in data extraction.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- LICENSE -->
## License

Copyright (c) 2026 Lucas dos Santos Dantas. All copyrights belong to the author.

Distributed under the [PolyForm Strict License 1.0.0](LICENSE): you may download and use ANCHOR
for noncommercial purposes, such as study, testing and evaluation. Modifying, redistributing or
using the software commercially is not allowed without the author's permission. The software is
provided without warranty of any kind. This is not an open-source license.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CONTACT -->
## Contact

Lucas dos Santos Dantas — [@LucasDantas2701](https://github.com/LucasDantas2701)

Project: [https://github.com/LucasDantas2701/ANCHOR](https://github.com/LucasDantas2701/ANCHOR)

Research project at Faculdade Matias Machline (Manaus, Brazil).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

* [Playwright](https://playwright.dev) and [Ollama](https://ollama.com)
* The Qwen team, for the Qwen 3.5 models
* Steward (Tang & Shin, 2024) and RPAI (Nikkari, 2025), which inspired the comparison between
  LLM-driven and controlled web automation
* [Best-README-Template](https://github.com/othneildrew/Best-README-Template) and
  [Shields.io](https://shields.io)

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- MARKDOWN LINKS & IMAGES -->
[stars-shield]: https://img.shields.io/github/stars/LucasDantas2701/ANCHOR.svg?style=for-the-badge
[stars-url]: https://github.com/LucasDantas2701/ANCHOR/stargazers
[issues-shield]: https://img.shields.io/github/issues/LucasDantas2701/ANCHOR.svg?style=for-the-badge
[issues-url]: https://github.com/LucasDantas2701/ANCHOR/issues
[license-shield]: https://img.shields.io/badge/license-PolyForm%20Strict%201.0.0-blue.svg?style=for-the-badge
[license-url]: LICENSE
[python-shield]: https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white
[python-url]: https://www.python.org
[playwright-shield]: https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white
[playwright-url]: https://playwright.dev
[ollama-shield]: https://img.shields.io/badge/Ollama-000000?style=for-the-badge&logo=ollama&logoColor=white
[ollama-url]: https://ollama.com
[product-screenshot]: images/demo.gif
