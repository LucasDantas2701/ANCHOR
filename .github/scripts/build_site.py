"""
Builds the documentation site's pages from the repository's own files, so the site never says
something the repository does not:
- a landing page (template home.html): the README's tagline and its "Why ANCHOR" list as cards;
- "Docs": the README cut into short pages (its sections, its subsections, and the bold-led
  paragraphs of "Usage" as guides);
- "Command reference": docs/COMMANDS.md, one page per section;
- "Evaluation", the changelog, and the Portuguese README, as they are.

    python .github/scripts/build_site.py      # writes site_src/ and the nav in site_nav.yml; then: mkdocs build

Run by .github/workflows/pages.yml on every push to main (the released version).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site_src"
REPO = "https://github.com/LucasDantas2701/ANCHOR/blob/main/"
# The site's root path (site_url in mkdocs.yml). Links inside raw HTML (<img src>, <a href>) are not
# adjusted by MkDocs, so they are written from the root, which works on every page at any depth.
BASE = "/ANCHOR/"

# Docs pages: (file, title, README section, subsection or None). A subsection page holds that "###".
SECTION_PAGES = [
    ("docs/introduction.md", "Introduction", "About The Project", None),
    ("docs/installation.md", "Installation", "Getting Started", "Prerequisites+Installation+Open ANCHOR+Keeping ANCHOR Up To Date"),
    ("docs/quick-example.md", "A first try", "Getting Started", "A First Try"),
    ("docs/responsible-use.md", "Responsible use", "Responsible Use", None),
    ("docs/limitations.md", "Known limitations", "Known Limitations", None),
    ("docs/roadmap.md", "Roadmap", "Roadmap", None),
    ("docs/faq.md", "FAQ", "FAQ", None),
    ("docs/contributing.md", "Contributing", "Feedback+Development", None),
    ("docs/license.md", "License and contact", "License+Contact+Acknowledgments", None),
    ("evaluation.md", "Evaluation", "Evaluation", None),
]
PROJECT_PAGES = slice(3, 9)          # the "Project" group of the navigation: responsible use ... license
# Guides: the subsections of "Using ANCHOR", one page each, in order, and the command line.
GUIDES = [
    ("docs/guides/run-a-request.md", "Run a request", "Run a request"),
    ("docs/guides/outputs.md", "What a run brings back", "What a run brings back"),
    ("docs/guides/watch.md", "Watch it run", "Watch it run"),
    ("docs/guides/questions.md", "When ANCHOR asks", "When ANCHOR asks"),
    ("docs/guides/logins.md", "Saved logins", "Saved logins"),
    ("docs/guides/automations.md", "Automations", "Automations"),
    ("docs/guides/schedules.md", "Schedules", "Schedules"),
    ("docs/guides/models.md", "Which model", "Which model"),
]
FILES = {"CHANGELOG.md": "changelog.md"}


def slug(heading: str) -> str:
    s = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return re.sub(r"\s+", "-", s).strip("-")


def sections(text: str, level: int = 2) -> dict[str, str]:
    marker = "#" * level + " "
    parts = re.split(rf"(?m)^{marker}", text)
    return {p.split("\n", 1)[0].strip(): p.split("\n", 1)[1] if "\n" in p else "" for p in parts[1:]}


def clean(text: str) -> str:
    return re.sub(r'<p align="right">\(<a href="#readme-top">back to top</a>\)</p>\s*', "", text).strip()


def up(text: str, levels: int) -> str:
    """Headings moved up (a subsection's "####" becomes "##" on its own page)."""
    return re.sub(r"(?m)^(#{2,6}) ", lambda m: "#" * max(2, len(m.group(1)) - levels) + " ", text)


class Site:
    def __init__(self):
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.commands = (ROOT / "docs" / "COMMANDS.md").read_text(encoding="utf-8")
        self.pages: dict[str, str] = {}                 # file -> markdown
        self.anchor_page: dict[str, str] = {}           # heading anchor -> file
        self.command_pages: list[tuple[str, str]] = []

    # ------------------------------------------------------------------ cutting
    def section(self, names: str) -> str:
        parts = sections(self.readme)
        out = []
        for name in names.split("+"):
            if name not in parts:
                raise SystemExit(f"README section not found: {name!r} (the site's pages follow the README's headings)")
            out.append(clean(parts[name]))
        return "\n\n".join(out)

    def why(self) -> list[dict]:
        block = re.search(r"\*\*Why ANCHOR:\*\*\s*\n((?:\* .*\n(?:  .*\n)*)+)", self.readme)
        if not block:
            raise SystemExit("README's 'Why ANCHOR:' list not found")
        cards = []
        for item in re.findall(r"(?m)^\* (.*(?:\n  .*)*)", block.group(1)):
            text = " ".join(item.split())
            m = re.match(r"\*\*(.+?)\*\*\s*(.*)", text)
            title, rest = (m.group(1), m.group(2)) if m else (text, "")
            rest = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", rest).strip(" ,")
            rest = rest[:1].upper() + rest[1:]
            cards.append({"title": title.rstrip("."), "text": rest})
        return cards

    def build(self) -> None:
        for file, title, names, sub in SECTION_PAGES:
            body = self.section(names)
            if sub:
                subs = sections(body, 3)
                picked = []
                for name in sub.split("+"):
                    if name not in subs:
                        raise SystemExit(f"README subsection not found: {name!r}")
                    picked.append(f"## {name}\n\n{subs[name].strip()}" if "+" in sub else subs[name].strip())
                body = up("\n\n".join(picked), 0)
            else:
                body = up(body, 1) if "+" not in names else re.sub(r"(?m)^## ", "## ", body)
                if "+" in names:
                    body = "\n\n".join(f"## {n}\n\n{up(clean(sections(self.readme)[n]), 1)}" for n in names.split("+"))
            self.pages[file] = f"# {title}\n\n{body}\n"
        usage = self.section("Using ANCHOR")
        intro = re.split(r"(?m)^### ", usage, maxsplit=1)[0].strip()
        subs = sections(usage, 3)
        for n, (file, title, name) in enumerate(GUIDES):
            if name not in subs:
                raise SystemExit(f"README subsection of 'Using ANCHOR' not found: {name!r}")
            text = up(subs[name].strip(), 1)
            if n == 0 and intro:
                text = intro + "\n\n" + text
            self.pages[file] = f"# {title}\n\n{text}\n"
        cmd_parts = sections(self.commands)
        cmd_intro = re.split(r"(?m)^## ", self.commands, maxsplit=1)[0]
        cmd_intro = re.sub(r"(?m)^# .*\n", "", cmd_intro).strip()
        self.pages["commands/index.md"] = f"# Command reference\n\n{cmd_intro}\n"
        self.command_pages.append(("Overview", "commands/index.md"))
        for name, body in cmd_parts.items():
            file = f"commands/{slug(name.split(' (')[0].replace('`', '')) or 'section'}.md"
            self.pages[file] = f"# {name}\n\n{up(body.strip(), 1)}\n"
            self.command_pages.append((name.replace("`", ""), file))
        for src, dst in FILES.items():
            self.pages[dst] = (ROOT / src).read_text(encoding="utf-8")
        self.home()
        self.home_pt()

    def home(self) -> None:
        tagline = re.search(r"(The ANCHOR web automation agent:[\s\S]*?you stay in control\.)", self.readme)
        cards = self.why()
        meta = ["---", "template: home.html", "title: ANCHOR web automation agent, self-healing and local (Ollama, Playwright)",
                "hide: [navigation, toc]",
                f"tagline: {quote(' '.join(tagline.group(1).split()) if tagline else '')}", "cards:"]
        for c in cards:
            meta += [f"  - title: {quote(c['title'])}", f"    text: {quote(c['text'])}"]
        meta.append("---")
        self.pages["index.md"] = "\n".join(meta) + "\n"

    def home_pt(self) -> None:
        """The Portuguese page: the same landing page, from README.pt-BR.md, with the rest of it below."""
        text = (ROOT / "README.pt-BR.md").read_text(encoding="utf-8")
        parts = sections(text)
        why = parts.get("Por que o ANCHOR")
        if why is None:
            raise SystemExit("README.pt-BR.md section not found: 'Por que o ANCHOR'")
        cards = []
        for item in re.findall(r"(?m)^\* (.*(?:\n  .*)*)", why):
            m = re.match(r"\*\*(.+?)\*\*\s*(.*)", " ".join(item.split()))
            if m:
                rest = m.group(2).strip(" ,")
                cards.append({"title": m.group(1).rstrip(":."), "text": rest[:1].upper() + rest[1:]})
        intro = text.split("## ", 1)[0]
        lead = [p for p in re.split(r"\n\s*\n", intro) if p.strip().startswith("O agente")]
        lead = re.sub(r"\*\*([^*]+)\*\*", r"\1", " ".join(lead[0].split())) if lead else ""
        meta = ["---", "template: home.html", "lang: pt", "title: ANCHOR, agente de automação web com RPA com IA e LLM local",
                "hide: [navigation, toc]", f"tagline: {quote(lead)}", "cards:"]
        for c in cards:
            meta += [f"  - title: {quote(c['title'])}", f"    text: {quote(c['text'])}"]
        meta.append("---")
        rest = "\n\n".join(f"## {name}\n\n{body.strip()}" for name, body in parts.items() if name != "Por que o ANCHOR")
        self.pages["pt-BR.md"] = "\n".join(meta) + "\n\n" + rest + "\n"

    # ------------------------------------------------------------------ links
    def link_map(self) -> None:
        for file, text in self.pages.items():
            for h in re.findall(r"(?m)^#{1,4} (.+)$", text):
                self.anchor_page.setdefault(slug(h), file)
        # The README's own section anchors land on the page made from them.
        for file, _, names, _ in SECTION_PAGES:
            for name in names.split("+"):
                self.anchor_page.setdefault(slug(name), file)
        self.anchor_page.setdefault("usage", GUIDES[0][0])
        self.anchor_page.setdefault("using-anchor", GUIDES[0][0])
        self.anchor_page.setdefault("the-command-line", "docs/contributing.md")
        self.anchor_page.setdefault("running-from-the-code", "docs/contributing.md")
        for file, _, name in GUIDES:
            self.anchor_page.setdefault(slug(name), file)
        self.anchor_page.setdefault("getting-started", "docs/installation.md")
        self.anchor_page["readme-top"] = "index.md"

    @property
    def references(self) -> dict:
        """The README's reference-style link definitions: [name]: url."""
        if not hasattr(self, "_references"):
            self._references = dict(re.findall(r"(?m)^\[([^\]]+)\]:\s*(\S+)", self.readme))
        return self._references

    def rel(self, here: str, target: str) -> str:
        depth = here.count("/")
        return "../" * depth + target

    def rewrite(self, text: str, here: str, commands_doc: bool = False) -> str:
        def fix_html(target: str) -> str:
            """A link inside raw HTML: from the site's root, to the page's address (not its .md file)."""
            out = fix(target)
            if re.match(r"^[a-z]+://|^mailto:|^#", out):
                return out
            path, _, frag = out.partition("#")
            path = re.sub(r"^(\.\./)+", "", path)
            if path.endswith(".md"):
                path = "" if path == "index.md" else path[:-3] + "/"
                path = path.replace("index/", "")
            return BASE + path + (f"#{frag}" if frag else "")

        def fix(target: str) -> str:
            if target.startswith("#"):
                page = self.anchor_page.get(target[1:])
                return target if page in (None, here) else self.rel(here, page) + target
            if re.match(r"^[a-z]+://|^mailto:", target):
                return target
            path, _, frag = target.partition("#")
            if commands_doc and not path.startswith(("docs/", "../")):     # COMMANDS.md links relative to docs/
                path = "docs/" + path if path and not path.startswith("..") else path
            path = path.replace("../", "")
            if path.startswith("docs/images/"):
                return self.rel(here, path.replace("docs/images/", "images/")) + (f"#{frag}" if frag else "")
            if path in ("docs/COMMANDS.md", "COMMANDS.md"):
                page = self.anchor_page.get(frag, "commands/index.md") if frag else "commands/index.md"
                return self.rel(here, page) + (f"#{frag}" if frag else "")
            if path in FILES:
                return self.rel(here, FILES[path]) + (f"#{frag}" if frag else "")
            if path == "README.md":
                return self.rel(here, self.anchor_page.get(frag, "index.md")) + (f"#{frag}" if frag else "")
            return REPO + target.replace("../", "")
        text = re.sub(r"\]\(([^)\s]+)\)", lambda m: f"]({fix(m.group(1))})", text)
        text = re.sub(r'(href|src|srcset)="([^"]+)"', lambda m: f'{m.group(1)}="{fix_html(m.group(2))}"', text)
        # Reference-style links ([![Python][python-shield]][python-url]) are defined at the README's end: each page
        # carries the definitions it uses, or they show as raw text.
        used = set(re.findall(r"\]\[([^\]]+)\]", text))
        defs = [f"[{name}]: {fix(url)}" for name, url in self.references.items() if name in used]
        return text + ("\n\n" + "\n".join(defs) + "\n" if defs else "")

    # ------------------------------------------------------------------ writing
    def write(self) -> None:
        if OUT.exists():
            shutil.rmtree(OUT)
        self.link_map()
        for file, text in self.pages.items():
            target = OUT / file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.rewrite(text, file, commands_doc=file.startswith("commands/")), encoding="utf-8")
        shutil.copytree(ROOT / "docs" / "images", OUT / "images")
        shutil.copytree(ROOT / "docs" / "site" / "assets", OUT / "assets")
        nav = ["nav:", "  - Home: index.md", "  - Docs:", "    - Getting started:"]
        nav += [f"      - {t}: {f}" for f, t, *_ in SECTION_PAGES[:3]]
        nav += ["    - Guides:"] + [f"      - {t}: {f}" for f, t, _ in GUIDES]
        nav += ["    - Project:"] + [f"      - {t}: {f}" for f, t, *_ in SECTION_PAGES[PROJECT_PAGES]]
        nav += ["  - Command reference:"] + [f"    - {quote(t)}: {f}" for t, f in self.command_pages]
        nav += ["  - Evaluation: evaluation.md", "  - Changelog: changelog.md", "  - Português: pt-BR.md"]
        (ROOT / "site_nav.yml").write_text("\n".join(nav) + "\n", encoding="utf-8")


def quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> int:
    site = Site()
    site.build()
    site.write()
    print(f"site_src/: {len(site.pages)} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
