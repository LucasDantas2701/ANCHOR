"""
Tables and lists on a page: finding them, naming them, reading them.

Used by the extract_table action and by the page summary that goes to the planner. A table is
a <table> or an element with role table or grid; a list is a <ul>, <ol> or role list with at
least two items. Menus are left out: lists inside <nav>, <header>, <footer> or a role menu,
menubar or navigation, and lists whose items are only links.

Each one gets a name, from what a person would call it: its caption, its aria-label (or
aria-labelledby), or the closest heading or legend before it. The headers of a table come from
its <th> cells (or role columnheader); without them, the columns are numbered.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page

from anchor.engine.element_resolver.tokenizer import STOPWORDS_N, normalize_tokens, tokenize

MAX_ROWS = 5000
MIN_MARGIN = 0.15          # how much the best match must beat the second to be chosen

# Words that say what to do or what kind of thing it is, not which one ("export the table of").
GENERIC_WORDS = {
    "tabela", "tabelas", "lista", "listas", "table", "tables", "list", "lists", "dados", "data",
    "extraia", "extrair", "extraia", "exporte", "exportar", "export", "extract", "copie", "copiar",
    "copy", "pegue", "pegar", "get", "leia", "ler", "read", "baixe", "baixar", "salve", "salvar",
    "save", "csv", "planilha", "spreadsheet", "todas", "todos", "toda", "todo", "all", "inteira",
    "whole", "linhas", "rows", "itens", "items", "me", "passe", "passa", "mostre", "show",
}

_FIND_JS = r"""
() => {
  const MENU = 'nav, header, footer, [role=navigation], [role=menu], [role=menubar], [role=banner], [role=contentinfo]';
  const visible = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const text = (e) => (e ? (e.innerText || e.textContent || '') : '').replace(/\s+/g, ' ').trim();
  const nameOf = (e) => {
    const cap = e.querySelector(':scope > caption'); if (cap && text(cap)) return text(cap);
    if (e.getAttribute('aria-label')) return e.getAttribute('aria-label').trim();
    const lb = e.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(/\s+/).map(id => text(document.getElementById(id))).join(' ').trim(); if (t) return t; }
    // the closest heading or legend before it, going up a few levels
    let node = e;
    for (let up = 0; up < 4 && node; up++) {
      let prev = node.previousElementSibling;
      while (prev) {
        if (/^(H[1-6]|LEGEND)$/.test(prev.tagName) || prev.getAttribute('role') === 'heading') return text(prev);
        const inner = prev.querySelectorAll('h1,h2,h3,h4,h5,h6,legend,[role=heading]');
        if (inner.length) return text(inner[inner.length - 1]);
        if (text(prev).length > 0 && text(prev).length <= 60 && /^(P|SPAN|DIV|STRONG|B|LABEL)$/.test(prev.tagName)
            && !prev.querySelector('table, ul, ol, input, button')) return text(prev);
        prev = prev.previousElementSibling;
      }
      node = node.parentElement;
      if (node && node.tagName === 'FIELDSET') { const lg = node.querySelector(':scope > legend'); if (lg) return text(lg); }
    }
    return '';
  };
  const out = [];
  document.querySelectorAll('table, [role=table], [role=grid]').forEach(t => {
    if (!visible(t) || t.closest(MENU)) return;
    if (t.parentElement && t.parentElement.closest('table, [role=table], [role=grid]')) return;   // nested tables
    const rowEls = [...t.querySelectorAll('tr, [role=row]')].filter(r => r.closest('table, [role=table], [role=grid]') === t);
    let headers = [];
    const head = rowEls.find(r => r.querySelector('th, [role=columnheader]') && !r.querySelector('td, [role=cell], [role=gridcell]'));
    if (head) headers = [...head.querySelectorAll('th, [role=columnheader]')].map(text);
    const rows = rowEls.filter(r => r !== head).map(r => [...r.querySelectorAll('th, td, [role=cell], [role=gridcell], [role=rowheader]')].map(text))
                       .filter(cells => cells.some(c => c));
    if (!rows.length) return;
    out.push({kind: 'table', name: nameOf(t), headers, rows});
  });
  document.querySelectorAll('ul, ol, [role=list]').forEach(l => {
    if (!visible(l) || l.closest(MENU) || l.closest('table')) return;
    if (l.parentElement && l.parentElement.closest('ul, ol, [role=list]')) return;               // nested lists
    const items = [...l.children].filter(c => c.tagName === 'LI' || c.getAttribute('role') === 'listitem').filter(visible);
    if (items.length < 2) return;
    const onlyLinks = items.every(i => { const a = i.querySelectorAll('a'); return a.length === 1 && text(a[0]) === text(i); });
    if (onlyLinks) return;                                                                         // a menu of links
    out.push({kind: 'list', name: nameOf(l), headers: [], rows: items.map(i => [text(i)])});
  });
  return out;
}
"""


_TEXTS_JS = r"""
() => {
  const SKIP = 'nav, header, footer, table, ul, ol, button, a, label, select, option, textarea, [role=navigation], [role=menu], [role=button], [role=table], [role=grid], [role=list]';
  const visible = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const out = [], seen = new Set();
  for (const e of document.querySelectorAll('p, span, div, dd, dt, strong, b, output, [role=status]')) {
    if (!visible(e) || e.closest(SKIP) || e.querySelector('p, div, table, ul, ol, input, button, select, a')) continue;
    const text = (e.innerText || '').replace(/\s+/g, ' ').trim();
    if (text.length < 3 || text.length > 80 || seen.has(text)) continue;
    if (!/\d/.test(text) && !text.includes(':')) continue;          // a value or a "label: value"
    seen.add(text); out.push(text);
    if (out.length >= 8) break;
  }
  return out;
}
"""


def value_texts(page: Page) -> list[str]:
    """Short texts with a value ("Receita total: R$ 182.400"), outside tables, lists and menus."""
    try:
        return page.evaluate(_TEXTS_JS)
    except Exception:
        return []


@dataclass
class TableData:
    kind: str                              # "table" or "list"
    name: str
    headers: list[str]
    rows: list[list[str]] = field(default_factory=list)

    @property
    def columns(self) -> list[str]:
        """The header of each column; columns without one are numbered."""
        width = max([len(self.headers)] + [len(r) for r in self.rows]) if (self.headers or self.rows) else 0
        if self.kind == "list":
            return ["item"]
        return [self.headers[i] if i < len(self.headers) and self.headers[i] else f"column {i + 1}" for i in range(width)]

    def label(self) -> str:
        return self.name or (", ".join(self.headers[:3]) if self.headers else "")


def find_tables(page: Page) -> list[TableData]:
    """The tables and lists on the page, in document order."""
    found = page.evaluate(_FIND_JS)
    return [TableData(kind=t["kind"], name=t["name"], headers=t["headers"], rows=t["rows"][:MAX_ROWS]) for t in found]


def _words(text: str) -> set[str]:
    tokens = tokenize(text or "")
    return (tokens | normalize_tokens(tokens)) - STOPWORDS_N


def match_table(tables: list[TableData], description: str) -> tuple[Optional[TableData], list[TableData]]:
    """
    The table or list the description names, or (None, the candidates) when it is not clear.
    Words that only say "table", "list" or "export" do not count. With one table or list on
    the page, a description that names no other is enough.
    """
    if not tables:
        return None, []
    wanted = _words(description) - _words(" ".join(GENERIC_WORDS))
    if not wanted:
        return (tables[0], []) if len(tables) == 1 else (None, tables)

    def score(t: TableData) -> float:
        name = _words(t.name)
        cols = _words(" ".join(t.headers))
        return (len(wanted & name) * 1.0 + len(wanted & cols) * 0.5) / len(wanted)

    ranked = sorted(tables, key=score, reverse=True)
    best = score(ranked[0])
    second = score(ranked[1]) if len(ranked) > 1 else 0.0
    if best <= 0:
        return (tables[0], []) if len(tables) == 1 else (None, tables)
    if best - second < MIN_MARGIN:
        return None, [t for t in ranked if score(t) >= best - MIN_MARGIN]
    return ranked[0], []


def _slug(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "table"


def save_csv(table: TableData, folder: Path, separator: str = ",") -> Path:
    """Writes the table to a new CSV file in folder (UTF-8 with BOM, so Excel shows the accents)."""
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = folder / f"{_slug(table.label())}_{stamp}.csv"
    n = 2
    while path.exists():
        path = folder / f"{_slug(table.label())}_{stamp}_{n}.csv"
        n += 1
    columns = table.columns
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=separator)
        writer.writerow(columns)
        for row in table.rows:
            writer.writerow((row + [""] * len(columns))[:len(columns)])
    return path
