"""Writes CATALOG.md from catalog.json, so the two never differ (python -m eval.resilience.closed.catalog_md)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEVELS = {1: "superficial", 2: "semantic", 3: "structural", 4: "behavioural", 5: "adversarial"}


def ready(c: dict) -> bool:
    """Whether the catalog is complete: every injected phrase has its English text (not PENDING)."""
    return all(not str(p.get("adapted_en", "")).startswith("PENDING") for p in c["injected_phrases"]["phrases"])


def render(c: dict) -> str:
    out = ["# The closed resilience set's catalog of perturbations", "",
           f"Version {c['version']}, {c['date']}, approved by {c['approved_by']}. Seed {c['seed']}; "
           f"{c['operators_per_task_and_level']} operators per base task and level.", "",
           f"Base: {c['base']}. The perturbations are new; the tasks are the development benchmark's.", ""]
    for change in c.get("changes", []):
        out += [f"*{change}*", ""]
    out += ["## Operators", "",
           "| Level | Operator | Source and category | Weight | What it does | Applies to |", "|---|---|---|---|---|---|"]
    for o in c["operators"]:
        cat = f"{o['category']} {o.get('category_name', '')}".strip()
        out.append(f"| {o['level']} ({LEVELS[o['level']]}) | `{o['id']}` | {o['source']}: {cat} | {o['weight']} | {o['does']} | {o['applies_to']} |")
    out += ["", "Weights are the category totals of the taxonomy (1065 causes in 8 applications); operators of one "
            "category share its total; level 5 has equal weights (its sources give no frequencies).", "",
            "## Left out, and why", ""]
    out += [f"- {x['category']} {x['name']}: {x['why']}." for x in c["left_out"]]
    inj = c["injected_phrases"]
    out += ["", "## Injected phrases (level 5)", "", f"Status: {inj['status']}.", ""]
    out += [f"- {r}" for r in inj.get("rules", [])]
    out += ["", "Listings used:", ""]
    out += [f"- {x['listing']} ({x['page']}), {x['threat']}: {x['what']}. Original context: {x['original_context']}. "
            f"Fits: {', '.join(x['fits'])}." for x in inj.get("listings", [])]
    out += ["", inj["same_excerpt_both_operators"] + ".", "", inj["address_placeholder"] + ".", "", "Left out on purpose:", ""]
    out += [f"- {x}." for x in inj["left_out_on_purpose"]]
    for p in inj["phrases"]:
        out += ["", f"### `{p['id']}` ({p['kind']}), from {p['listing']}, {p['source_location']}", "",
                f"- Adaptation ({p['adapted_by']}): {p['adaptation']}",
                f"- Portuguese ({p['translated_by']}): {p['translation_pt']}",
                f"- English: {p['adapted_en']}", f"- Fits: {', '.join(p['fits'])}"]
    out += ["", "## Rules of the generator", ""] + [f"{i}. {r}" for i, r in enumerate(c["rules"], 1)]
    out += ["", "## Sources", ""] + [f"- `{k}`: {v}." for k, v in c["sources"].items()]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    (HERE / "CATALOG.md").write_text(render(json.loads((HERE / "catalog.json").read_text(encoding="utf-8"))), encoding="utf-8")
