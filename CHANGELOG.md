# Changelog

All notable changes to the project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
uses [Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH):

- **MAJOR**: a change that breaks compatibility (e.g. the format of the memory or of the evaluation cases).
- **MINOR**: a new feature, compatible with what exists.
- **PATCH**: a bug fix, with no new feature.

While MAJOR is 0, the project is in initial development, and changes that break compatibility
also bump MINOR.

The project was called smart-rpa until 2026-09-29; the entries before that use the old names
(the `app/` package, the Portuguese commands and options).

## [Unreleased]

### Added
- **The closed set of planner tasks** (`eval/plans/holdout_tasks.json`): 80 requests written by three
  colleagues who had not seen the project, all kept, on the four never-used `holdout_*` pages and
  nine known ones, 42 in Portuguese and 38 in English. 22 cannot be done on their pages and are
  marked `"expected": "not_possible"`: `eval/plan_run.py` judges them done right when the agent does
  not declare success and their safety checks hold. Reference values may use `{tomorrow}`.
- `eval/plan_run.py --check` validates the closed set's annotations blind: each reference plan runs
  on its `reference_targets` with Playwright alone, with no part of ANCHOR. See `eval/README.md` for
  how the set was built and the rules until the final run.

## [0.3.0] - 2026-10-09

Reliability, saved automations and evaluation. In short:

- **Checking what happened.** Each action's effect is verified (the page changed, the field kept
  the value, no error appeared), with a screenshot as the last resort when the other checks doubt
  a step (`--vision`). Plans have goals, are checked against the request, and the end is checked
  against what was actually done, so a run that did not do what was asked does not end as a success.
- **English**, end to end: interface, planner, documentation and evaluation.
- **Saved automations** (`python -m anchor.automations`): learn a task once, replay it without the
  model in about 3 s, with parameters and one run per spreadsheet row, notes for the planner, and
  **self-healing** when the site changes, with a reviewable and undoable record of every recovery.
- **Safety.** Confirmation before sensitive actions (deleting, saving, sending, paying, downloading,
  uploading, cancelling something irreversible), a destructive-action barrier that looks at what
  the step is about, and defenses against instructions injected by page content.
- **Evaluation.** An injection suite, an interventions experiment with a simulated user, and a
  resilience benchmark with pages altered in 5 levels, comparing ANCHOR with a fixed-selector script
  and an LLM-in-control agent. On the development set, ANCHOR completed 82% (4B) and 84% (9B) of
  the altered tasks, against 53% for the script and 68% to 72% for the LLM in control, with 1 to 2
  false successes in 150 runs against 33 to 41 for the LLM in control.


### Added
- The agent records, for each step that worked, the element actually acted on, and the
  resilience benchmark keeps every run's steps (description, value, status, how the element was
  chosen, and which element it was); `eval.resilience.run -v` shows them for the runs that need a
  look. Added to diagnose ANCHOR's false successes and attacks in the first full run of the
  development set, which happened mostly while healing (a replanned step acting on a lookalike).
- Resilience benchmark, part 3: **the runs and the report**. `python -m eval.resilience.run` runs
  the traditional script, the LLM in control and ANCHOR on the altered pages, in parts (by
  executor, model and language), judging every run the same way (the task's checks, false
  successes, unrequested actions, attacks and attempts, model calls, time).
  `python -m eval.resilience.report` puts the parts together. ANCHOR's automation starts from the
  reference plan, the same plan the script was recorded from, and runs twice on each altered page
  with no user: the 1st run measures the recovery, the 2nd the reuse (counted only with no model call).
- Resilience benchmark, part 2: **the two executors ANCHOR is compared with**
  (`eval/resilience/executors.py`). The traditional script replays fixed selectors recorded on
  the original page, as classic RPA recorders do (the id; else a unique name or test attribute;
  else the path of classes and positions), and claims success when every step runs. The LLM in
  control, in the style of Steward, gets the numbered elements at every step (described as ANCHOR
  describes them to its planner, with the same filters) and chooses the action and the element,
  performed directly, with no heuristic, barriers, confirmation, effect check or memory. The build
  now records the 30 scripts too (`eval/plans/resilience_scripts.json`). Replayed on every level,
  the scripts complete all L0, L2 and L5 tasks (they do not read the labels), 13% of L1, 33% of L3
  and 20% of L4, with no false success.
- Resilience benchmark, part 1: **the altered pages** (`eval/resilience/`). `python -m
  eval.resilience.build` builds, from the 13 task pages, altered versions in 5 levels (superficial,
  semantic, structural, behavioral, adversarial) plus L0 (the original, only with the evaluation's
  markers), and the 180 tasks rewritten for them (`eval/plans/resilience_tasks.json`). Every element
  a task checks is marked with `data-eval`, which no executor may use, so the checks keep working
  when ids and classes change. The perturbations are deterministic and keep the pages' own scripts
  working (no JavaScript error on any page). The reference plans complete all the L0 tasks. Repeated
  without replanning, they complete 93% of L1, 57% of L2, 100% of L3, 20% of L4 and 60% of L5, with no
  attack on L5 working: a first idea of each level's difficulty. These are the development
  perturbations; the closed set gets different ones, for the final run.
- **Interventions experiment** (`eval/interventions.py`): the resolver's development cases, run by
  the Executor with the choice memory and a simulated user that knows the right element (it picks
  the right numbered candidate, or clicks the element on the page). Round 1 starts with an empty
  memory, round 2 repeats the cases, round 3 repeats them in a shuffled order. On the local cases:
  round 1 asked in 15.4% of the Portuguese cases and 5.8% of the English ones, with 98.1% and 94.2%
  right; rounds 2 and 3 asked nothing, with the same accuracy, the asked cases now coming from the
  memory. The silent errors (1.9% and 5.8%) stay the same in every round: when the system is wrong
  with confidence it does not ask, so there is nothing to remember. No model is used.
- The time spent waiting for the user (disambiguation and confirmations) is measured apart
  (`user_wait_seconds` in the agent's result and in the automations' run records), and the
  summary shows it next to the total time, so that a slow answer does not look like a slow system.
- **Effect check by screenshot** (layer 4, `anchor/agent/vision.py`), turned on with `--vision`
  (agent, `automations run`, `plan_run --agent`). When the other checks doubt a step (a field,
  list or box whose state does not match; a click with no visible effect in the page's code; an
  expected text that did not appear), the agent asks the model a yes/no question about a
  screenshot scaled to 640 pixels (inside the browser, with no new dependency); for a click, it
  compares the screenshots from before and after. The screenshot can only confirm a doubted step:
  it never turns a step that worked into a failure, an error message on the page is never
  overruled, and an unclear answer or an error counts as "not confirmed". The results record the
  questions asked, the steps confirmed and the time spent. The Qwen 3.5 models answer with their
  own `vision` capability, so no other model is loaded.
- `eval/vision_probe.py`: measures, before the effect check by screenshot is built, how long the
  model takes to answer yes/no questions about a screenshot of the registration page (6 questions
  with known answers, at 1024 and 640 pixels wide), and how many it gets right. The Qwen 3.5 models
  used here have the `vision` capability in Ollama, so no other model is needed.
- `eval/plan_run.py -v` shows the model's refused answers, and why each one was refused, when a
  task's plan fails (the planner keeps them in `last_attempts`). Before, only the last reason was
  shown, which hid the earlier refusals.
- Prompt injection evaluation, part 2: **the defenses** (`anchor/planner/untrusted.py`). Page
  content is data, not instructions: (1) a new rule in the planner prompt says so; (2) element
  names and item contexts that look like instructions to the assistant ("ignore the previous
  instructions", "assistant:", "system instruction", "the user authorized") are left out of the
  page summary, keeping what comes before the instruction (often the item's name), and a button
  whose aria-label is an instruction keeps its visible text; (3) page messages that look like
  instructions do not reach the history; (4) what a plan types must come from the request or
  the user's notes, never from the page (checked on every plan, replans included). Ordinary
  pages are summarized exactly as before, and the user message is unchanged; only the prompt's
  rule 11 is new, so the main suite must be measured again. The detector was written knowing the
  test attacks: it needs attacks it has never seen (the resilience benchmark) to be measured fairly.
- `eval/plan_run.py --suite injection` also counts **attack attempts** (`attack_targets` in the
  tasks): steps that tried to do what the page asked, even when a barrier stopped them. In the
  baseline, no attack worked, but the 9B model tried twice to delete the account after the
  injected message, and the destructive-action barrier stopped it.
- Prompt injection evaluation, part 1 (measuring before defending): test pages
  (`eval/fixtures/injection.html` and `injection_en.html`) with four attacks (an instruction in a
  product's description, in an almost invisible link, in an `aria-label`, and in a message shown
  after a search) and 6 tasks with harmless requests (`eval/plans/tasks_injection.json`). Each task
  has `attacks`, expressions that are true if an attack worked; `eval/plan_run.py --suite injection`
  runs them and adds the `attacked` column. The main suite is unchanged.
- **Confirmation of sensitive actions** (`anchor/engine/sensitive.py`). A click is sensitive
  when the step's description (outside parentheses) or the name of the element the resolver
  chose has a verb of deleting, saving or submitting, sending, paying, downloading or uploading,
  in Portuguese or English; looking at the element catches vague steps on a "Delete" button.
  Cancelling is sensitive only with an object that makes it irreversible (an order, a purchase,
  a subscription, a booking, an account, a plan, an enrollment, a contract), which may be in the
  item's context in parentheses: "Cancelar" alone usually just closes a form.
  The Executor asks after finding the element and before acting; a denied action is not
  performed, and the agent stops without replanning (the model could look for another way to
  do what was denied). In saved automations, each decision is asked once and saved
  (`confirmations.json`): an allowed action is not asked again, one denied with an explicit "no"
  stops the next runs too, until `python -m anchor.automations confirmations <name> --forget N`.
  Just pressing Enter, or having no terminal to answer, denies only that time and saves nothing. `--allow-sensitive` (agent, `planner --run`, `automations run`)
  turns the question off. Without a confirmer (evaluations, tests), nothing changes.
- Saved automations, part 4: **the user's notes**. After a run that did not work, `run` asks
  whether you want to leave a note for the next runs (with `--csv`, once, at the end); the 5 most
  recent notes go to the planner, in their own section of the message, when it learns or heals
  the plan. `python -m anchor.automations notes <name>` lists them, `--add` adds one and
  `--remove` removes one. Without notes, the message to the model is unchanged.
- Saved automations, part 3: **parameters**. The parts of the request that change go in braces
  (`"cadastre {nome}, CPF {cpf}, no TI e salve"`), and each run gives their values with
  `run --param nome="Maria Silva"`, or runs once per row of a CSV file with `run --csv file.csv`
  (`,` or `;`). The model plans with the real values; the approved plan, and any healed plan, is
  saved with the placeholders back in place of the values, so it works for any value. The run
  and recovery records keep the placeholders, not the values, which may be personal data.
- `docs/COMMANDS.md`: the complete reference of the commands: setup and Ollama, every option of
  every tool, the demos, the model profile fields and the environment variables. A test
  (`tests/test_docs.py`) keeps it complete: it runs each tool's `--help` and fails if an option or
  subcommand is missing, and also checks that every runnable module, every profile field and
  every environment variable read by the code is documented, and that the commands in the READMEs
  only use options the reference knows. It already found options missing from the documentation
  (`--root`, `--yes`, `--headed`, `--split`, `--site`) and an old Portuguese option shown in
  `--help` (`--sim`, now hidden like the others).
- `.gitignore` ignores `.patch` files at the project root, so they are never committed by accident.
- Saved automations, part 2: **self-healing**. When a saved step stops working (after the choice
  memory, the heuristic and the user), the automation hands over to the LLM, which plans the rest
  from the page as it is now; if the run succeeds, the saved plan is corrected. Every recovery is
  recorded in `recoveries.json` (what failed, the original step, what replaced it, how it was
  solved, whether the effect was confirmed, and the confidence of each new step), and so is every
  element the user picks during a replay. `python -m anchor.automations recoveries <name>` lists
  them and `undo <name> <number>` undoes one: a plan correction brings the previous plan back, a
  user choice is forgotten from the memory. `run --no-heal` stops instead of recovering.
- The agent records each step's confidence (the heuristic's score or the memory's similarity).
- Saved automations, part 1 (`anchor/automations`, `python -m anchor.automations`): describe a task
  once (`create`), and run it whenever you want (`run`). The first run learns: the agent plans
  with the LLM, and if the run succeeds, the steps that worked become the approved plan. The next
  runs replay the approved plan **without the LLM**, through the same agent (choice memory,
  heuristic, disambiguation, effect checks, goals and the check of what was done); if a saved
  step fails, the replay stops and says the site may have changed. `run --relearn` plans again;
  `list` and `show` review the automations, their approved plans and their last runs. Each
  automation is a folder in `automations/` (kept out of Git), with its own choice memory and a
  record of every run.
- English evaluation, part 2 (the planner): 15 English development tasks
  (`eval/plans/tasks_en.json`, on the English pages), mirroring the Portuguese ones.
  `eval/plan_run.py` loads them, accepts `--language pt|en`, and reports each profile per
  language. The reference plans complete all 30 tasks, in both modes.
- `"prompt_language": "auto"` (or `--prompt-language auto`): the planner prompt follows each
  request's language, detected from typical words, command verbs and accents (`detect_language`
  in `anchor/planner/language.py`); on a tie, Portuguese, the measured default. It gets all 30
  task requests right. The agent writes the history for the model in the detected language.
  Portuguese stays the default until the English prompt is measured.
- English evaluation, part 1 (the resolver): English versions of the Portuguese test pages
  (`registration_en`, `users_en`, `orders_en`, `jobs_en`, `search_enter_en`, with the same structure)
  and 52 English development cases (`eval/cases/*_en.json`, field `"language": "en"`), mirroring the
  Portuguese ones. `eval/run.py` reports the results per language and accepts `--language pt|en`.
  First measurement: recall@1 88.5% and silent error 7.7% in English, against 82.7% and 1.9% in
  Portuguese.
- Table cells now carry their column header ("E-mail", "Status") as a hint, since a cell's text
  alone often does not say what it is ("brian@company.com"); only for non-interactive cells.
- `eval/fixtures/feedback.js` follows the page's language.
- Before declaring success, the agent checks what was actually **done** against the request,
  with the same check the initial plan goes through (conclusive verbs in a click or key press,
  the request's data in some step). Until now, a goal counted as fulfilled as soon as one of its
  steps worked, so a model that said "nothing is left" right after opening the search pop-up got
  a false success (found in `p-pop-01`, 2026-09-30). Now the model is warned once ("the request is
  not fulfilled yet: ...") and gets two more end checks; if what was done still does not cover the
  request, the run ends as not fulfilled.
- Pressing Enter in a field counts as searching, whatever the field is called (in the plan check
  and in the new check of what was done).
- Planner prompt in English, as an option: `"prompt_language": "en"` in the model profile, or
  `--prompt-language en` in the command-line tools. Portuguese stays the default, since it is the
  measured one; the English prompt must be measured on the dev set before being used. With
  English, everything the model reads is in English, including the element kinds in the page
  summary and the execution history.
- `--lang en|pt` in the command-line tools, for the interface language (overrides `ANCHOR_LANG`).
- `anchor/i18n.py`: user-facing messages in English (default) or Portuguese, chosen with the
  `ANCHOR_LANG` environment variable (`en` or `pt`). The terminal disambiguation, the memory
  commands, the login messages and the demo use it. To skip a step, both `S` and `P` work. What
  the model reads (the page summary) keeps the Portuguese element kinds, so the planner's input,
  and therefore its measured results, do not change.
- Effect verification of each action (layer 1, no LLM, `anchor/agent/effects.py`): for form
  actions, the element's state (value in the field, chosen option, checked box; input masks such
  as the phone one are accepted); for clicks and Enter, changes on the page, requests, new tabs
  and downloads; for all of them, new messages. An error message ("CPF inválido") turns the step
  into a failure; the others go to the planner's history. With no effect, the step is retried once
  and then counts as a failure, with replanning; a remembered choice with no effect is forgotten.
  `Agent(verify_effect=False)` turns the verification off.
- Revealed field: if the field to fill in does not exist, but there is a clickable element with
  that name (e.g. the magnifier that opens the search), the agent clicks it and fills in the field
  that appears (the one matching the description, or the one that gets the focus).
- Effect verification: clicking a checkbox or option checks whether its state changed (before, it
  counted as "no effect", since the page structure does not change); clicking a field or a list
  does not require an effect, since it only gives the focus.
- `press Enter` on an element that is not a text field goes to the last filled-in field.
- A click that only gives the focus (on a field or a list) is accepted, but does not fulfill the goal.
- Values with brackets, quotes or the "opções:" label copied from the page summary are cleaned
  before execution and before the effect check (e.g. `"[Price: low to high]"`).
- `eval/fixtures/feedback.js`: visible feedback for actions on the test pages, which have no
  server. Included in every page, the holdout ones too, without changing their content.
- Goals (checkpoints) in the plan: the planner lists the request's goals, marking the conclusive
  ones (save, send), and links each step to a goal; conclusive goals come last, and plans that
  break this get the error and are redone. The agent tracks the goals (fulfilled when its last
  step works with the effect verified) and only declares the end with all of them fulfilled; a
  planner that finishes with pending goals leads to "cancelled". Goals that only had blocked
  destructive actions are dropped, and a goal whose step failed and that replanning abandoned (by
  taking another way) is marked as replaced. Every plan with goals needs a conclusive goal, and
  every goal needs at least one step; plans that break this go back to the model with the error.
- Checking the plan against the request, without the LLM, on the initial plan: if the request uses
  a conclusive verb (save, send, delete, search, cancel, confirm, download), some step must do it
  in a click or key press (a goal's description or a fill is not enough: filling in the search is
  not searching); and the request's data (proper names, numbers such as CPF and phone, e-mails,
  quoted texts) must appear in some step. A plan that does not cover the request goes back to the
  model with the reason. This targets the premature end of small models, which defined only the
  goals they could fulfill.
- Expected effect (layer 2): a step can give a text that should appear; if it does not appear in
  the page's new text, the step becomes a suspicion (recorded in the history and in a metric),
  but does not fail.
- Replanning and the end check receive the goals' status and the messages visible on the page
  (layer 3, the messages part).
- `eval/plan_run.py --agent`: columns for actions with no effect, premature ends (the agent
  declared success, but the task's checks failed), goals fulfilled and suspicions.
- PolyForm Strict License 1.0.0 (`LICENSE`): noncommercial use allowed, no modification or
  redistribution; copyright by the author. "Responsible use" section in the README.

### Changed
- Four fixes from the diagnosis of ANCHOR's false successes and attacks in the resilience
  benchmark's development set (all general, none specific to the benchmark's pages):
  - **The destructive-action barrier looks at what the step is about.** When the request asks to
    delete or cancel something, the step must be about what the request names ("Excluir (Bruno
    Lima)" for "exclua o Bruno Lima"), and may act on everything ("Excluir tudo", "Delete
    everything") only if the request says so. Before, any destructive step passed once the request
    had a destructive verb.
  - **A lookalike with an extra word loses to the name asked.** When the top candidates are in a
    near tie and one's name (label and text) is the other's plus words the request does not have,
    the one the request names wins (`NAME_COVERED_BONUS`, 0.10, applied only in that case): "Salvar
    cadastro" over "Salvar cadastro depois", "Add to cart" over "Add to cart later". It changes no
    choice that is not such a tie: the local resolver cases are all unchanged. On the benchmark's
    level 5, the saved plans alone, with no model, now complete 28 of the 30 tasks (18 before),
    with no attack. A first version, a bonus for every element whose whole name is in the request,
    made a single-word name that happens to be in the request win ("Pesquisar" for "clicar na
    sugestão da pesquisa", and SauceDemo's "Open Menu" for "abrir o carrinho", a new silent error
    in each language); it was replaced by this tie-break before release.
  - **The healing contract is one to one, on the same thing.** Each saved step that failed must be
    redone by a different successful step of the same action, with the same value (a renamed field
    filled with the same value) or covering at least half of the saved step's content words.
    "Accept cookies" no longer redoes "open the cart".
  - **A step that undoes an earlier one is noticed.** The agent keeps the boxes and lists it has
    verified and checks them again after each step: checking "CLT" after "PJ" now fails with the
    reason ("this step undid an earlier step"), and the model replans knowing it. Only a requested
    state undone by an unrequested step is flagged: undoing an unrequested step is a correction,
    and when both are in the request there is no telling which is right, so the final checks
    decide. A first version flagged every undo, and the 4B model failed `en-reg-01`, whose request
    ("Register the employee Maria Silva, ... contractor") has both "employee" (the person) and
    "contractor" (the option).
- When a saved automation heals itself, the saved plan is a contract: every saved step that failed
  must have been redone by a successful step of the same action, or the run does not count as done
  (and the plan is not corrected). Before, if the model said nothing was left after, say, closing a
  cookie banner, a run could end as a success without the step the banner had blocked, whenever the
  request had no conclusive verb or data for the check of what was done to catch it. Found with the
  resilience benchmark's level 4. A site that turns a list into buttons may now make a legitimate
  recovery count as not done: a false "not done", never a false success.
- The interventions experiment checks whether the chosen element is the right one right before
  acting, not after: SauceDemo redraws the whole page when sorting, the elements lose their ids,
  and the two sorting cases were counted as silent errors although the resolver chose right.
- The check of the initial plan against the request is no longer fatal. A plan that does not
  cover the request still goes back to the model, but if the attempts run out and coverage was the
  only problem, the first answer is kept instead of giving up: some pages must be revealed bit by
  bit (a magnifier that opens the search field), and the check of what was done, at the end,
  still keeps a run that did not cover the request from succeeding. Found with `plan_run -v` on
  `p-pop-01`, which the 4B model failed in every run after the injection defenses: it planned
  only the click on the magnifier (right, since the field appears afterwards), the check refused
  it, and its "fix" dropped the search.
- While a saved plan is replayed without the LLM, the agent's messages say so ("Replaying the
  approved plan...", "continuing with the saved plan...") instead of talking about planning.
- Effect check: if the whole document is replaced without a new window (as some single-page apps
  do), the page observer now watches the new document; before, it kept watching the old one and
  every action looked like it had no effect (found when replaying an automation).
- The legacy fixed-selector example moved from `anchor/automation/saucedemo.py` to
  `examples/legacy_saucedemo.py`. The `.gitignore` sections are in English, and it ignores
  `automations/`.
- The query's action words now come only from outside parentheses: text in parentheses is the
  context the model copies from the page summary to identify the item, and it may contain the
  names of neighbouring elements ("Cancel order (Order #1024 · Being packed View details)"), whose
  verbs are not the requested action. It made "View details" tie with "Cancel order" in the
  English task `en-ord-01`, with both prompts and both models; in Portuguese the same problem was
  hidden, because "ver" is not in the action words. No resolver case changed.
- Measured with the models (dev, 15 tasks per language): on the English tasks, the Portuguese
  prompt did better than the English one (4B: 80% done, 67% clean, against 73% and 53%; 9B: 93%
  and 87%, against 87% and 80%). The English prompt is a translation that was never tuned, and it
  brought back failures the Portuguese one had fixed. The default stays `pt`; `auto` remains an option.
- The check of the request's data no longer requires English capitalized common words
  (languages, weekdays, months: "Portuguese", "Monday"), which the page may show in another form
  (the option "Português"); found with the English task `en-log-02`.
- The identical-name rule also ignores the English summary's kinds ("Dropdown", "Checkbox"...);
  no resolver case changed.
- Text extraction no longer targets checkboxes, radio buttons or switches, which have no text.
  With the column header, on the local development sets: Portuguese recall@1 82.7% → 86.5% and
  correct 78.8% → 82.7% (silent error unchanged, 1.9%); English recall@1 88.5% → 90.4%, correct
  86.5% → 88.5% and silent error 7.7% → 5.8%. The three silent errors left in English (a price
  extraction, "favorite" vs. "Add to wishlist", and a status cell losing to the name cell) are
  recorded as limitations rather than fixed with case-specific rules.
- The project is now called **ANCHOR** (Adaptive Natural-language Control with Human
  Oversight and Recovery); repository and package name `anchor-rpa`. The Python package moved
  from `app/` to `anchor/`, so commands become `python -m anchor.agent`, `python -m
  anchor.planner` and `python -m anchor.engine.memory`. The LinkedIn tests are enabled with
  `ANCHOR_LINKEDIN=1` (the old `SMART_RPA_LINKEDIN` still works). From this version on, the
  changelog and commit messages are written in English.
- English translation, part 1 (the engine): comments and docstrings of the element resolver,
  the executor, disambiguation and the choice memory, plus the small modules (browser session,
  legacy SauceDemo script, `anchor/main.py`). Checked by comparing the syntax trees before and
  after (Python and JavaScript): the code itself did not change, and the evaluation results are
  identical. The Portuguese vocabulary of the resolver stays, since it is data for understanding
  Portuguese requests.
- English translation, part 2 (the planner and the agent). Everything the model reads (the
  prompt, the user message, the page summary, the plan errors sent back for correction, the
  execution history, the goals' status and the failure reasons) moved to a catalog,
  `anchor/planner/language.py`, with the Portuguese texts kept exactly as they were: comparing
  every call the tests make to the planner, before and after, all 99 are identical. What the user
  reads (the agent's reports and final messages, the command-line tools, the progress indicator,
  the Ollama and profile errors) follows the interface language.
- Command-line options are in English: `--profile`, `--url`, `--memory`, `--browser-profile`,
  `--max-attempts`, `--run` and `--no-page`. The old Portuguese options still work, hidden from
  `--help`. The model profiles are now `ollama-small` and `ollama-medium` (the old names still
  work), and the `"_leia"` note in `llm_profiles.json` became `"_readme"`.
- Internal codes renamed: `resolved_by` values `enter_no_campo` → `enter_in_field` and
  `campo_revelado` → `revealed_field`. The agent's result has a new `plan_failed` flag, used by
  `eval/plan_run.py` instead of looking for a Portuguese sentence in the message.
- English translation, part 3a (the evaluation). The test pages, case files and ids were renamed
  to English (`cadastro` → `registration`, `loja` → `store`, `pedidos` → `orders`, `usuarios` →
  `users`, `vagas` → `jobs`, `busca_*` → `search_*`, and the holdout pages `holdout_booking`,
  `holdout_helpdesk` and `holdout_hr`); in the holdout files, only the file name, the `site` and
  `fixture` fields and the id prefixes changed, without touching any query (checked: the cases are
  identical). The pages' content and the requests stay in Portuguese. `eval/plan_run.py` has English
  options (`--profiles`, `--reference`, `--agent`, `--task`, `--no-page`; the Portuguese ones still
  work) and English result fields (`success`, `clean`, `unrequested`, `premature`, `goals`...);
  its result files now start with `plans_`. `eval/run.py` prints in English and its outcomes are
  `correct`, `silent_error`, `avoidable_refusal`, `correct_refusal` and `perception_failure`.
  Older result files keep the old names; `eval/README.md` (now in English) has the mapping. Both
  evaluations give the same numbers as before.
- README rewritten in English, following the Best-README-Template structure: badges, table of
  contents, about the project (with the architecture), getting started, usage, evaluation,
  roadmap, feedback (issues only, since the license does not allow modifications), development,
  responsible use, known limitations, license, contact and acknowledgments. Placeholders are
  ready for a logo and a demo GIF.
- `examples/desempate.py` → `examples/disambiguation_demo.py`, in English.
- English translation, part 3b (the tests): 118 test names, the comments and the docstrings. The
  test data (requests and page contents) stays in Portuguese. The whole changelog is now in English.
- `eval/plan_run.py --prompt-language en|pt` runs the planner with the chosen prompt language.
- The memory commands are now `list`, `forget` and `clear` (with `--yes`); the Portuguese ones
  (`listar`, `esquecer`, `limpar`, `--sim`) still work.
- Nested elements become a single candidate when one contains the other and only one of them is
  interactive (e.g. a product's link and the name inside it); the interactive one is kept, with
  the higher score of the two. The perception script now reports `parentId` and `interactive`.
- The choice memory keeps at most 500 choices per file; beyond that, it drops the least recently
  used one.

## [0.2.1] - 2026-09-26

Fixes found in tests on real sites (LinkedIn and CoinMarketCap), reproduced on local pages. On the
Resolver's development set (52 local cases), recall@1 went from 80.8% to 82.7% and the silent
error dropped from 3.8% to 1.9%.

### Fixed
- Pop-ups disappeared from the page summary sent to the planner: on large pages, the limit of 80
  elements was filled by the header, and pop-ups sit at the end of the code. The summary is now
  sorted by relevance (open pop-up, marked with `[pop-up]`; visible on the screen; the rest), and
  elements covered by the pop-up are left out.
- A click that opened a pop-up did not trigger replanning (only a URL change did). The agent now
  replans when a pop-up, dialog or menu opens or closes.
- The Resolver accepted elements that could not receive the action (e.g. filling in a button). There
  is now a filter by action: fill only considers text fields, select only native lists, check only
  checkboxes, options and switches.
- Searches without a button (Enter only) got stuck: a search click that finds no button, right
  after filling in a field, becomes Enter in that field. The prompt also says to use `press Enter`
  when there is no search button.
- Repetition loop: the same step repeated right after replanning is blocked, with a warning to the
  planner, and no step runs more than 3 times. The end check runs at most twice per run.
- Elements chosen by the user's click were kept in the memory with their text only. Now the page is
  reindexed and the full signature is kept; and an element whose text is identical and unique on
  the page is found again even if its context changed.
- Ctrl+C showed the full error: the commands now end with a short message and close the browser.
- An end check that only proposes steps already done counts as the goal being reached (before,
  loop detection turned it into a failure).
- On large pages, the element the request needs could be left out of the summary even with no
  pop-up (e.g. the magnifier after 90 links). The summary is now guided by the request: elements
  sharing words with it come right after the pop-ups.
- Typing in a search field opened the suggestion list and triggered replanning, which led the model
  to click the suggestions instead of searching. Filling in no longer triggers replanning for pop-ups.
- When clicking, the value already typed in a field made the field compete with items showing that
  text (e.g. the search suggestion). Outside of filling in, the value no longer identifies the field.

### Changed
- Barrier for unrequested destructive actions: a step that closes, deletes, removes, hides or
  cancels something the request did not mention is not performed, and the planner is warned.
  Closing a pop-up does not count.
- Identical name: an element whose text is exactly what the request names (ignoring kind words
  such as "Opção" and "Botão") gets a small bonus over those that only contain the phrase. It does
  not apply to extraction, which has its own exact-text rule.
- The prompt says to click the element that reveals what is missing (magnifier, "Search", menu)
  and to answer that the request cannot be done only when nothing on the page would lead to it.
- A request with no verb, which only names an item: elements announcing a destructive or
  dismissive action (close, delete, remove, hide, dismiss, cancel, clear) lose points.
- The prompt asks not to close, hide or dismiss items the request did not mention.
- The `select` safety net tries checking the option when the list does not solve the step.
- `eval/plan_run.py --check`: allowed elements that only show up later (e.g. search suggestions)
  give a warning, not a problem; the reference plan, in `--agente` mode, returns the missing steps
  on each replan.

### Added
- Three development tasks reproducing the real tests: a search in a pop-up (`busca_popup.html`), a
  search with Enter only and suggestions (`busca_enter.html`), and a list of jobs with "Salvar" and
  "Fechar vaga" (`vagas.html`).

## [0.2.0] - 2026-09-26

Complete agent: the system receives a text request and a link, generates the plan with an LLM, runs
it, replans when needed and checks whether the goal was reached. On the 12 development tasks,
through the agent loop, both local models (Qwen 3.5 with 4B and 9B) completed all of them; 10 and
9 of them, respectively, with no unrequested step.

### Added
- The agent loop (`app/agent`): initial plan, step-by-step execution, replanning when the page
  changes or a step fails (with the reason, including an element covered by a modal), the end
  check ("goal reached" when nothing is left), cancelling with a report after 3 failures, and a
  step limit. It records model calls, replans, failures, user interventions, tokens and time.
- The command `python -m app.agent --perfil <name> --url <link> "<request>"`, with a visible
  browser, disambiguation in the terminal, the choice memory and an optional persistent profile.
- The planner accepts the execution history, to replan only what is missing.
- `eval/plan_run.py --agente`: the tasks run through the full agent loop.
- The version number in the code (`app.__version__`), also written to the evaluation results.
- This changelog.
- `isort` configuration in `pyproject.toml`, to check the import order.
- The planner (`app/planner`): turns the user's request into steps with an LLM, in the OpenAI API
  format (it works with OpenAI and with local Ollama models). JSON output validated against the
  Executor's actions, with a new attempt when the plan is invalid, and the list of the page's
  elements in the request to the model. It drops the reasoning of "thinking" models
  (`<think>...</think>`) and accepts extra parameters per profile.
- Model profiles in `llm_profiles.json` (address, model and the name of the environment variable
  holding the key; never the key itself).
- The command `python -m app.planner`, to generate and run a plan from a request and a link.
- Evaluation of complete tasks (`eval/plan_run.py`, 12 tasks in `eval/plans/tasks.json`): request →
  plan → execution → check of the final state, with time and tokens per model, and hand-written
  reference plans as a ceiling.
- Ollama's native API in the profiles (`"api": "ollama"`), with the reasoning of "thinking" models
  turned off (`"think": false`) and options such as `num_ctx`; clear messages when Ollama is not
  running or the model does not exist.
- Real-time progress in the terminal (`app/planner/progress.py`): waiting time and, with the Ollama
  API, the streamed answer with the phase ("thinking" or "writing the plan") and the tokens.
- `eval/plan_run.py` loads each model before the tasks (the loading time is reported separately,
  outside the plans' time) and shows each task's progress.
- Unrequested-step metric in `eval/plan_run.py`: each task lists its allowed elements (`allowed`),
  and any other element acted on (click, typing or choice) counts; the table also shows the
  "clean" tasks (done with no extra step).
- Closed set of planner tasks (`eval/plans/holdout_tasks.json`, empty for now), which only runs with
  `--final`, and `--check` to check the tasks without calling models.
- Cleanup of step descriptions before execution: removes kind labels copied from the page summary
  ("Campo de texto", "Caixa de marcação", "Lista de opções") and quotes.
- A `select` on a radio button or checkbox is redone as `check`.

### Changed
- Planner prompt: which action to use for each kind of element, descriptions without the kind, the
  step that completes the request, no unrequested steps, and login without the password (the user
  types the password and clicks log in).
- Task `p-log-01` adjusted to the system's design: fill in the username and stop before logging in,
  without typing the password.
- The OpenAI client does not retry calls on its own (`max_retries=0`): a timeout shows up right away.
- Element names in disambiguation and in the page summary use the visual hint when the text is too
  short (e.g. "shopping cart 2") and the `data-testid` when there is no other name.
- Imports standardized (PEP 8): standard library, third parties and the project, separated by a
  blank line and in alphabetical order.

## [0.1.0] - 2026-09-25

First version: the execution engine. Steps are still written by hand; the LLM planner and the agent
loop come in 0.2.0.

### Added
- Page perception (`index_script.js`) with interactive elements only: links, buttons, fields, ARIA
  roles and areas clickable through `cursor: pointer`, with the accessible name, icons' visual hints,
  state, card context and geometry. An extraction mode with text elements. Reading of open shadow DOM.
- Text normalization: accent removal, a light PT/EN stemmer, compound expressions and synonyms with
  several values.
- Per-site vocabulary (`ElementResolver(synonyms=...)`), outside the generic dictionary.
- Scoring with a penalty for disabled elements and for conflicting verbs (with groups of equivalent
  verbs).
- The user's disambiguation (`app/engine/disambiguation`): candidates numbered on the page, a choice
  in the terminal or a direct click on the element. A `Disambiguator` contract ready for a frontend.
- The choice memory (`app/engine/memory`): reuses the user's choices, finds the element again by
  its content, expires entries that fail or disappear, and has the review command
  `python -m app.engine.memory`.
- Reproducible evaluation (`eval/`): 60 development cases, a closed holdout of 42 cases (it only runs
  with `--final`), a threshold sweep and a selector check.
- `app/main.py` with the semantic engine on SauceDemo, and a demo in `examples/desempate.py`.

### Changed
- The Executor's thresholds calibrated in the evaluation: minimum score 0.40 and a **relative**
  ambiguity margin of 4% (before: 0.20 and an absolute margin of 0.08).
- The Resolver reindexes the page on every query.
- Results coming from the memory report `similarity` instead of `score`.
- LinkedIn tests disabled by default (the site's terms of use forbid automation).

### Fixed
- B1: the whitespace regex in `index_script.js` (`/\\s+/` → `/\s+/`).
- B2: the index was built only once, and became outdated after navigating.
- B3: old `data-er-id` attributes were not removed when reindexing.
- B4: the `.inventory_item` selector, specific to SauceDemo, was hard-coded in the generic code.
- B5: multi-word synonyms never matched.
- B6: the ambiguity margin depended on the score's scale (now relative).
- The context of elements in lists of short cards covered the whole list.
- The query's object was counted twice, in the element's label and in its context.

[Unreleased]: https://github.com/LucasDantas2701/ANCHOR/compare/v0.3.0...develop
[0.3.0]: https://github.com/LucasDantas2701/ANCHOR/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/LucasDantas2701/ANCHOR/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/LucasDantas2701/ANCHOR/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/LucasDantas2701/ANCHOR/releases/tag/v0.1.0

---

## How to release a version

1. On `develop`, change `__version__` in `anchor/__init__.py` to the final version (without `-dev`).
2. In this file, rename "Unreleased" to the version and the date, and create an empty "Unreleased" above it.
3. Update the comparison links at the end of the list of versions.
4. Commit: `git commit -m "vX.Y.Z"`.
5. Merge into `main`, create the tag and push:
   `git checkout main && git merge develop && git tag -a vX.Y.Z -m "..." && git push origin main --tags`
6. Go back to `develop` and bump the version to the next one with `-dev` (e.g. `0.4.0-dev`).
