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

#### Queries from colleagues (recommended)

The holdout queries were written by the same author as the heuristics (authorship bias). To
reduce it, ask 2 or 3 people to:

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

`--prompt-language en` runs the planner with the English prompt; the measured results so far use
the Portuguese one (the default).

### Closed set of planner tasks

The tasks in `plans/tasks.json` were used to tune the planner prompt, so their numbers are
development numbers. The final numbers come from `plans/holdout_tasks.json` (split `test`),
which only runs with `python -m eval.plan_run --final`, a single time.

How to build the set:

1. **Requests written by other people.** Ask 2 or 3 colleagues to open the pages in `fixtures/`
   in the browser and write, for each one, 5 to 8 requests as they would ask an assistant
   ("quero reservar a sala Amazonas para amanhã às 10h"), without seeing the code or the
   existing tasks. The goal is 30 to 40 requests.
2. **Half on new pages, half on old ones.** Use the `holdout_*.html` pages (never seen by the
   planner) and the development ones, with new requests. This way the article separates
   generalization to new requests from generalization to new pages. The `holdout_*` pages are
   also the resolver's closed set, and both `--final` runs happen at the end.
3. **Turn each request into a task**, in the `tasks.json` format: `checks` (the expected final
   state), `allowed` (the elements the task may act on), `reference` (the right plan, written by
   hand) and `"split": "test"`. Ambiguous requests, or requests impossible on the page, may stay,
   with `checks` describing the right behavior (for example, no click).
4. **Check without running anything:** `python -m eval.plan_run --check` validates fields, pages,
   selectors and checks, without calling models or the heuristic.
5. **Do not run the models on these tasks, and do not tune the prompt looking at them,** until
   the final run. If something changes after looking, record it in the article.

## Visible feedback on the test pages (`fixtures/feedback.js`)

The test pages have no server, so many buttons would produce no visible effect. Since the agent
checks the effect of each action, `feedback.js` shows a discreet notice ("Ação registrada") on
each click and on each Enter in a field, as a real site would respond. The notice is not
interactive and is not indexed; the resolver's results do not change. It was also included in the
`holdout_*` pages, without changing their content (2026-09-26).

## File names (renamed on 2026-09-30)

The pages, case files and ids were renamed to English; only labels changed, and the content of
the cases is identical. Older result files use the old names:

| old | new | case ids |
|---|---|---|
| `cadastro` | `registration` | `cad-` → `reg-` |
| `loja` | `store` | `loja-` → `store-` |
| `pedidos` | `orders` | `ped-` → `ord-` |
| `usuarios` | `users` | `usr-` (unchanged) |
| `vagas`, `busca_popup`, `busca_enter` | `jobs`, `search_popup`, `search_enter` | |
| `holdout_agenda` | `holdout_booking` | `h-age-` → `h-book-` |
| `holdout_chamados` | `holdout_helpdesk` | `h-cha-` → `h-help-` |
| `holdout_rh` | `holdout_hr` | `h-rh-` → `h-hr-` |

Task ids: `p-cad-` → `p-reg-`, `p-loja-` → `p-store-`, `p-ped-` → `p-ord-`, `p-vag-` → `p-jobs-`.
