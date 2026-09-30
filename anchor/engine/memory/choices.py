"""
Memória das escolhas do usuário (aprendizado entre execuções).

Quando o usuário desempata um passo e a ação dá certo, a escolha é
guardada. Na próxima execução do mesmo passo, na mesma página, o
Executor usa a escolha direto, sem perguntar de novo.

O elemento é reencontrado pelo CONTEÚDO (papel, texto, rótulo, pistas
visuais, data-testid e contexto), não pela posição: continua funcionando
se a ordem dos itens mudar. Um caminho CSS fica como plano B.

Para não contaminar execuções futuras:
    - se a ação falha com um elemento vindo da memória, a entrada é apagada;
    - se o elemento não é encontrado `max_misses` vezes seguidas
      (o site mudou), a entrada também é apagada;
    - a memória guarda no máximo `max_entries` escolhas (500, por padrão);
      ao passar disso, sai a usada há mais tempo.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from anchor.engine.element_resolver.tokenizer import normalize_text, tokenize

SIGNATURE_FIELDS = ("role", "tag", "label", "text", "hint", "test_id", "context")


@dataclass
class Entry:
    url: str
    action: str
    description: str
    signature: dict
    css_path: str = ""
    created: str = ""
    last_used: str = ""
    uses: int = 0
    misses: int = 0
    source: str = "user"


@dataclass
class Found:
    """Resultado da busca de uma entrada na página atual."""
    record: Optional[dict] = None     # registro do index_script.js
    css_path: Optional[str] = None    # ou: caminho CSS (plano B)
    similarity: float = 0.0


def page_key(url: str) -> str:
    """Página sem query string nem âncora (ex.: .../pedidos?id=3 → .../pedidos)."""
    parts = urlsplit(url or "")
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def step_key(url: str, action: str, description: str) -> str:
    return f"{page_key(url)}|{action}|{' '.join(normalize_text(description).split())}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _same(a: str, b: str) -> bool:
    return bool(a) and " ".join(normalize_text(a).split()) == " ".join(normalize_text(b).split())


def _jaccard(a: str, b: str) -> float:
    ta, tb = tokenize(a or ""), tokenize(b or "")
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def similarity(signature: dict, record: dict) -> float:
    """Quão parecido um elemento da página é com o elemento memorizado."""
    if signature.get("role") != record.get("role") or signature.get("tag") != record.get("tag"):
        return 0.0
    score = 0.0
    if signature.get("test_id") and signature["test_id"] == record.get("testId"):
        score += 3.0
    for f in ("label", "text", "hint"):
        if _same(signature.get(f, ""), record.get(f, "")):
            score += 1.5
    score += 2.0 * _jaccard(signature.get("context", ""), record.get("context", ""))
    return score


class ChoiceMemory:
    MIN_SIMILARITY = 2.5   # papel+tag iguais, texto igual e algum contexto em comum
    MIN_MARGIN = 0.5       # distância mínima para o 2º mais parecido

    def __init__(self, path: str | Path, max_misses: int = 3, max_entries: int = 500):
        """
        max_entries: ao passar desse número de escolhas, sai a usada há mais tempo.
        """
        self.path = Path(path)
        self.max_misses = max_misses
        self.max_entries = max_entries
        self.entries: dict[str, Entry] = {}
        self._load()

    # ------------------------------------------------------------ persistência

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.entries = {k: Entry(**v) for k, v in data.get("entries", {}).items()}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": 1, "entries": {k: asdict(e) for k, e in self.entries.items()}}
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------ operações

    def lookup(self, url: str, action: str, description: str) -> Optional[Entry]:
        return self.entries.get(step_key(url, action, description))

    def remember(
        self,
        url: str,
        action: str,
        description: str,
        signature: dict,
        css_path: str = "",
    ) -> Entry:
        key = step_key(url, action, description)
        now = _now()
        entry = Entry(
            url=page_key(url),
            action=action,
            description=description,
            signature={f: signature.get(f, "") for f in SIGNATURE_FIELDS},
            css_path=css_path,
            created=now,
            last_used=now,
            uses=1,
        )
        self.entries[key] = entry
        while len(self.entries) > self.max_entries:
            oldest = min(self.entries, key=lambda k: (self.entries[k].last_used, self.entries[k].created))
            del self.entries[oldest]
        self.save()
        return entry

    def mark_used(self, url: str, action: str, description: str) -> None:
        entry = self.lookup(url, action, description)
        if entry:
            entry.uses += 1
            entry.misses = 0
            entry.last_used = _now()
            self.save()

    def mark_missed(self, url: str, action: str, description: str) -> None:
        """O elemento memorizado não está na página. Após max_misses seguidas, esquece."""
        key = step_key(url, action, description)
        entry = self.entries.get(key)
        if not entry:
            return
        entry.misses += 1
        if entry.misses >= self.max_misses:
            del self.entries[key]
        self.save()

    def forget(self, url: str, action: str, description: str) -> None:
        if self.entries.pop(step_key(url, action, description), None):
            self.save()

    def ordered(self) -> list[tuple[str, Entry]]:
        """Entradas em ordem estável (da mais antiga para a mais nova), para numerar."""
        return sorted(self.entries.items(), key=lambda kv: (kv[1].created, kv[0]))

    def forget_key(self, key: str) -> bool:
        if self.entries.pop(key, None) is None:
            return False
        self.save()
        return True

    def clear(self) -> None:
        self.entries = {}
        self.save()

    # ------------------------------------------------------------ busca na página

    def find(self, entry: Entry, records: list[dict]) -> Found:
        """Procura o elemento memorizado entre os registros da página atual."""
        scored = sorted(
            ((similarity(entry.signature, r), r) for r in records),
            key=lambda x: x[0],
            reverse=True,
        )
        if scored and scored[0][0] >= self.MIN_SIMILARITY:
            best = scored[0][0]
            second = scored[1][0] if len(scored) > 1 else 0.0
            if best - second >= self.MIN_MARGIN:
                return Found(record=scored[0][1], similarity=best)
            return Found()  # dois elementos igualmente parecidos: melhor perguntar

        # Texto idêntico e único na página, com o mesmo tipo de elemento: é ele, mesmo
        # que o contexto tenha mudado (ex.: sugestões de pesquisa recriadas a cada busca).
        sig = entry.signature
        name = sig.get("text") or sig.get("label")
        if name:
            same = [r for r in records
                    if r.get("role") == sig.get("role") and r.get("tag") == sig.get("tag")
                    and (_same(name, r.get("text", "")) or _same(name, r.get("label", "")))]
            if len(same) == 1:
                return Found(record=same[0], similarity=round(similarity(sig, same[0]), 2))
        if entry.css_path:
            return Found(css_path=entry.css_path)
        return Found()
