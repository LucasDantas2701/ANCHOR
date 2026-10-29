"""
The annotation recorder: the person annotates a closed set's tasks by doing each request on its page.

    python -m eval.annotate eval/plans/holdout_controlled_tasks.json
    python -m eval.annotate eval/plans/holdout_controlled_tasks.json --task sc-p05-claude_1-1 --redo

For each task still to annotate, a browser window opens on the task's page, with the request in a
panel at the bottom. The person does the request as a user would (fills, chooses, ticks, clicks), then:
- "Pronto": the steps become the reference plan, the elements touched become the allowed ones, and the
  final state becomes the checks (each field's value, the option chosen, the box ticked, the button
  clicked, and any text the person selected with "Conferir também o texto selecionado");
- "É uma pergunta": the text the person selected on the page is the expected answer;
- "Não é possível": the task is marked not possible, with the reason, and nothing may be sent.
The checks are run on the spot; the task is saved at once, so the work can stop and resume. It prints
only task ids and counts, never a request (the request is shown only in the browser, to the person).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RECORDER = (ROOT / "annotate_recorder.js").read_text(encoding="utf-8")
NOTHING_SENT = "!__clicked('button, input[type=submit], [role=button]')"


def to_annotate(task: dict) -> bool:
    return not task.get("checks") and not task.get("expected")


def build(steps: list[dict], state: str, answer: str = "", reason: str = "", texts: list[str] | None = None) -> dict:
    """The annotation of a task from what the person did (pure: tested without a browser)."""
    if state == "impossible":
        return {"reference": [], "allowed": [], "checks": [NOTHING_SENT], "expected": "not_possible", "why_not_possible": reference_text(reason)}
    reference = [[s["action"], s["label"], s["value"]] for s in steps if s["action"] != "uncheck"]
    allowed = list(dict.fromkeys(s["selector"] for s in steps))
    checks = []
    for s in steps:
        q = f"document.querySelector({json.dumps(s['selector'])})"
        if s["action"] == "fill":
            checks.append(f"{q}.value === {json.dumps(s['value'])}")
        elif s["action"] == "select":
            checks.append(f"{q}.selectedOptions[0].text.trim() === {json.dumps(s['value'])}")
        elif s["action"] == "check":
            checks.append(f"{q}.checked")
        elif s["action"] == "click":
            checks.append(f"__clicked({json.dumps(s['selector'])})")
    checks += [f"document.body.innerText.includes({json.dumps(t)})" for t in texts or []]
    out = {"reference": reference, "allowed": allowed, "checks": list(dict.fromkeys(checks))}
    if state == "answer":
        out["reference"] = reference + [["extract_text", answer[:60], None]]
        out["extraction"] = [{"kind": "text", "contains": answer}]
        if not out["checks"]:
            out["checks"] = [NOTHING_SENT]
    return out


def reference_text(text: str) -> str:
    return " ".join(text.split())


def annotate(path: Path, only: str | None = None, redo: bool = False) -> dict:
    from playwright.sync_api import sync_playwright

    from eval.plan_run import FIXTURES, INSTRUMENT

    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    todo = [t for t in tasks if (t["id"] == only if only else to_annotate(t)) and (redo or to_annotate(t) or only)]
    done = {"annotated": 0, "not_possible": 0, "questions": 0, "skipped": 0}
    print(f"{len(todo)} task(s) to annotate in {path.name}.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        for task in todo:
            while True:
                ctx = browser.new_context(viewport={"width": 1280, "height": 860})
                ctx.add_init_script(INSTRUMENT)
                ctx.add_init_script("window.__annot_task = " + json.dumps({"id": task["id"], "request": task["request"]}) + ";")
                ctx.add_init_script(RECORDER)
                page = ctx.new_page()
                page.on("dialog", lambda d: d.accept())
                page.goto((FIXTURES / task["fixture"]).as_uri())
                page.wait_for_function("() => window.__annot && window.__annot.state !== 'working'", timeout=0, polling=300)
                result = page.evaluate("() => ({...window.__annot, steps: JSON.parse(sessionStorage.getItem('__annot_steps') || '[]')})")
                if result["state"] == "restart":
                    ctx.close()
                    continue
                if result["state"] == "skip":
                    done["skipped"] += 1
                    ctx.close()
                    break
                note = build(result["steps"], result["state"], result.get("answer", ""), result.get("reason", ""), result.get("texts"))
                failing = [c for c in note["checks"] if not page.evaluate(f"() => Boolean({c})")]
                ctx.close()
                if failing:
                    print(f"  {task['id']}: {len(failing)} check(s) not true at the end; do it again (Recomeçar).")
                    continue
                task.update(note)
                task.pop("note", None)
                path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                done["not_possible" if result["state"] == "impossible" else "questions" if result["state"] == "answer" else "annotated"] += 1
                print(f"  {task['id']}: saved ({result['state']}, {len(note['reference'])} step(s), {len(note['checks'])} check(s)).")
                break
        browser.close()
    left = sum(to_annotate(t) for t in tasks)
    print(f"Done: {done}. Still to annotate in the file: {left}. Then: python -m eval.plan_run --check")
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.annotate", description="Annotates a closed set's tasks by doing them.")
    ap.add_argument("file", help="the tasks file to annotate (for example eval/plans/holdout_controlled_tasks.json)")
    ap.add_argument("--task", help="only this task (by id)")
    ap.add_argument("--redo", action="store_true", help="with --task: annotate again a task already annotated")
    args = ap.parse_args(argv)
    annotate(Path(args.file), args.task, args.redo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
