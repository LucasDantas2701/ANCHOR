"""
Revisão da memória das escolhas pelo terminal.

    python -m anchor.engine.memory memory/demo.json listar
    python -m anchor.engine.memory memory/demo.json esquecer 2
    python -m anchor.engine.memory memory/demo.json esquecer 1 3
    python -m anchor.engine.memory memory/demo.json limpar

Serve para corrigir o que o assistente aprendeu errado: se uma escolha
memorizada não é a certa, esqueça-a, e na próxima execução ele volta
a perguntar.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from anchor.engine.disambiguation.describe import KIND

from .choices import ChoiceMemory, Entry


def describe_entry(entry: Entry) -> str:
    sig = entry.signature
    kind = KIND.get(sig.get("role", ""), "Elemento")
    name = sig.get("label") or sig.get("text") or sig.get("hint") or "(sem texto)"
    near = " ".join((sig.get("context") or "").split())
    start = near.lower().find(name.lower())
    if start >= 0:
        near = " ".join((near[:start] + near[start + len(name):]).split())
    near = f", perto de: {near[:50]}" if near else ""
    return f'{kind} "{name[:50]}"{near}'


def list_entries(memory: ChoiceMemory, out: Callable[[str], None]) -> None:
    items = memory.ordered()
    if not items:
        out("Nenhuma escolha memorizada.")
        return
    out(f"{len(items)} escolha(s) memorizada(s) em {memory.path}:\n")
    for number, (_, e) in enumerate(items, 1):
        out(f"[{number}] Passo: \"{e.description}\" ({e.action})")
        out(f"    Elemento: {describe_entry(e)}")
        out(f"    Página: {e.url}")
        out(f"    Usada {e.uses} vez(es), última em {e.last_used.replace('T', ' ')}\n")


def main(argv: list[str] | None = None, input_fn=input, out: Callable[[str], None] = print) -> int:
    ap = argparse.ArgumentParser(prog="python -m anchor.engine.memory", description="Revisa a memória das escolhas.")
    ap.add_argument("arquivo", type=Path, help="arquivo da memória (ex.: memory/demo.json)")
    sub = ap.add_subparsers(dest="comando", required=True)
    sub.add_parser("listar", help="mostra as escolhas memorizadas")
    forget = sub.add_parser("esquecer", help="esquece escolhas pelo número mostrado em 'listar'")
    forget.add_argument("numeros", type=int, nargs="+")
    clear = sub.add_parser("limpar", help="esquece todas as escolhas")
    clear.add_argument("--sim", action="store_true", help="não pede confirmação")
    args = ap.parse_args(argv)

    if not args.arquivo.exists():
        out(f"Arquivo não encontrado: {args.arquivo}")
        return 1

    memory = ChoiceMemory(args.arquivo)

    if args.comando == "listar":
        list_entries(memory, out)
        return 0

    if args.comando == "esquecer":
        items = memory.ordered()
        invalid = [n for n in args.numeros if not 1 <= n <= len(items)]
        if invalid:
            out(f"Número(s) inválido(s): {', '.join(map(str, invalid))}. Use 'listar' para ver os números.")
            return 1
        for n in sorted(set(args.numeros)):
            key, entry = items[n - 1]
            memory.forget_key(key)
            out(f"Esquecida [{n}]: \"{entry.description}\" → {describe_entry(entry)}")
        out("Na próxima execução, o assistente vai perguntar de novo nesses passos.")
        return 0

    if args.comando == "limpar":
        total = len(memory.entries)
        if not total:
            out("Nenhuma escolha memorizada.")
            return 0
        if not args.sim and input_fn(f"Esquecer as {total} escolhas? (s/n) ").strip().lower() != "s":
            out("Nada foi apagado.")
            return 0
        memory.clear()
        out(f"{total} escolha(s) esquecida(s).")
        return 0

    return 1
