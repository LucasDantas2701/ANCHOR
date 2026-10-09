# Evaluation results

Every run of the evaluation tools saves its results here, named after the date, the commit it
ran on and what it ran. Nothing is deleted: the files are the trace of every number published
in the README and in the article. This page says which files back each published number.

| File name | Tool | What it is |
|---|---|---|
| `<date>_<commit>.csv/json` | `eval.run` | The element resolver, case by case |
| `plans_<date>_<commit>.csv/json` | `eval.plan_run` | Complete tasks (`_injection`: the injection suite; `_vision`: with `--vision`) |
| `resilience_<date>_<commit>_<executor>_<model>_<language>` | `eval.resilience.run` | The resilience benchmark, one part per file |
| `interventions_<date>.json` | `eval.interventions` | The interventions experiment |
| `vision_<date>.json` | `eval.vision_probe` | Time and accuracy of questions about screenshots |
| `planos_*` | `eval.plan_run` | Older runs, from before the code was translated to English (Portuguese field names) |

## The numbers of version 0.3.0

| Published number | Files |
|---|---|
| Element resolver, 60 cases per language | `20261008-164707_623b0f7` |
| Complete tasks, 15 per language | `plans_20261008-172828_623b0f7` |
| Prompt injection, before the defenses | `plans_20261002-162629_6bca5f8_injection` |
| Prompt injection, with the defenses | `plans_20261008-150759_670be32_injection` |
| Interventions with a simulated user | `interventions_20261007-130143` (the run before it had a measurement bug, explained in the CHANGELOG) |
| Screenshot questions | `vision_20261003-001548` |
| Resilience: the fixed-selector script | `resilience_20261007-200459_9bd6052_script` |
| Resilience: the LLM in control | `resilience_20261007-213303_9bd6052_llm_ollama-small_pt`, `..._ollama-small_en`, `resilience_20261008-001342_..._ollama-medium_pt`, `resilience_20261008-005526_..._ollama-medium_en` |
| Resilience: ANCHOR | the four `resilience_20261008-*_623b0f7_anchor_*` files |

To see a resilience table from its files:

```sh
python -m eval.resilience.report eval/results/resilience_20261007-200459_9bd6052_script.json eval/results/resilience_*_623b0f7_anchor_*.json
```

The other files are earlier versions, diagnosis runs and checks, kept so that the history in the
CHANGELOG can be followed: for example, `resilience_*_9bd6052_anchor_*` is ANCHOR before the
fixes found by the diagnosis (`resilience_*_15b98ee_*`, levels 1, 4 and 5 only).
