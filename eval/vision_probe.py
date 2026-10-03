"""
How long does the model take to answer a question about a screenshot, and does it get it
right? This probe answers that before the effect check by screenshot is built.

    python -m eval.vision_probe --profiles ollama-small ollama-medium

It opens the registration test page, takes screenshots before and after a few actions, and
asks yes/no questions whose answers are known, at two screen widths. It reports, per model
and width, the time per question, the tokens and the right answers. Ollama profiles only
(images go in the message, as Ollama's native API expects).
"""

from __future__ import annotations

import argparse
import base64
import json
import time
from datetime import datetime
from pathlib import Path
from statistics import mean

from playwright.sync_api import sync_playwright

from anchor import __version__
from anchor.cli import option
from anchor.planner import ConfigError, get_profile

ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "fixtures" / "registration.html"
WIDTHS = (1024, 640)


def _questions(page) -> list[tuple[str, bytes, bool]]:
    """(question, screenshot, the right answer) for a few states of the page."""
    shots = []
    page.goto(PAGE.as_uri())
    shots.append(("O campo \"Nome completo\" está preenchido com o texto \"Maria Silva\"?", page.screenshot(), False))
    page.fill("#nome", "Maria Silva")
    shots.append(("O campo \"Nome completo\" está preenchido com o texto \"Maria Silva\"?", page.screenshot(), True))
    shots.append(("A caixa \"Li e aceito os termos de uso\" está marcada?", page.screenshot(), False))
    page.check("#termos")
    shots.append(("A caixa \"Li e aceito os termos de uso\" está marcada?", page.screenshot(), True))
    page.select_option("#dep", label="TI")
    shots.append(("Na lista \"Departamento\", a opção escolhida é \"TI\"?", page.screenshot(), True))
    shots.append(("Na lista \"Departamento\", a opção escolhida é \"RH\"?", page.screenshot(), False))
    return shots


def ask(client, model: str, question: str, image: bytes) -> tuple[bool | None, float, int, int, str]:
    """(the answer, seconds, tokens in, tokens out, the raw answer)."""
    start = time.perf_counter()
    response = client.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "user",
                   "content": f"Olhe a captura de tela de uma página web. {question} "
                              "Responda só com uma palavra: sim ou não.",
                   "images": [base64.b64encode(image).decode("ascii")]}],
    )
    seconds = time.perf_counter() - start
    raw = (response.choices[0].message.content or "").strip()
    word = raw.lower().strip(" .!\n")
    answer = True if word.startswith(("sim", "yes")) else False if word.startswith(("não", "nao", "no")) else None
    usage = getattr(response, "usage", None)
    return (answer, seconds, getattr(usage, "prompt_tokens", 0) or 0, getattr(usage, "completion_tokens", 0) or 0,
            raw[:80])


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.vision_probe")
    option(ap, "--profiles", nargs="+", required=True, help="Ollama profiles from llm_profiles.json")
    args = ap.parse_args()

    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in args.profiles:
            try:
                profile = get_profile(name)
            except ConfigError as exc:
                print(f"[{name}] {exc}")
                return 1
            if profile.api != "ollama":
                print(f"[{name}] the probe needs an Ollama profile (\"api\": \"ollama\")")
                return 1
            client = profile.client()
            print(f"\n=== {name} ({profile.model})")
            start = time.perf_counter()
            client.chat.completions.create(model=profile.model, messages=[{"role": "user", "content": "ok"}],
                                           temperature=0)
            print(f"  model ready in {time.perf_counter() - start:.1f} s (not counted)")
            for width in WIDTHS:
                page = browser.new_page(viewport={"width": width, "height": round(width * 0.625)})
                for question, image, expected in _questions(page):
                    answer, seconds, t_in, t_out, raw = ask(client, profile.model, question, image)
                    right = answer == expected
                    rows.append({"profile": name, "model": profile.model, "width": width, "question": question,
                                 "expected": expected, "answer": answer, "right": right,
                                 "seconds": round(seconds, 2), "tokens_in": t_in, "tokens_out": t_out, "raw": raw})
                    print(f"  [{'OK ' if right else 'ERR'}] {width:5}px {seconds:5.1f}s {t_in:5} tokens  "
                          f"{question[:60]} → {raw}")
                page.close()
        browser.close()

    print("\nSUMMARY")
    print(f"{'profile':16} {'width':>6} {'right':>7} {'s/question':>11} {'tokens in':>10}")
    for name in args.profiles:
        for width in WIDTHS:
            part = [r for r in rows if r["profile"] == name and r["width"] == width]
            if part:
                print(f"{name:16} {width:6} {sum(r['right'] for r in part):3}/{len(part):<3} "
                      f"{mean(r['seconds'] for r in part):11.1f} {mean(r['tokens_in'] for r in part):10.0f}")

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    path = out / f"vision_{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps({"version": __version__, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved to {path.relative_to(ROOT.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
