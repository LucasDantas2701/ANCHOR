"""
Builds the documentation site's pages from the repository's own files, so the site never says
something the repository does not: the README is cut into its sections (one page each), and the
command reference, the Portuguese README and the changelog are added as they are.

    python .github/scripts/build_site.py      # writes site_src/; then: mkdocs build

Run by .github/workflows/pages.yml on every push to main (the released version).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site_src"
REPO = "https://github.com/LucasDantas2701/ANCHOR/blob/main/"

# Each page: its file and the README's "## " sections that make it (in order).
PAGES = {
    "index.md": ["About The Project"],
    "getting-started.md": ["Getting Started"],
    "usage.md": ["Usage"],
    "evaluation.md": ["Evaluation"],
    "responsible-use.md": ["Responsible Use", "Known Limitations"],
    "roadmap.md": ["Roadmap"],
    "contributing.md": ["Feedback", "Development", "License", "Contact", "Acknowledgments"],
}
TITLES = {"index.md": None, "getting-started.md": "Getting started", "usage.md": "Using ANCHOR",
          "evaluation.md": "Evaluation", "responsible-use.md": "Responsible use and limitations",
          "roadmap.md": "Roadmap", "contributing.md": "Contributing, license and contact"}
FILES = {"docs/COMMANDS.md": "commands.md", "README.pt-BR.md": "pt-BR.md", "CHANGELOG.md": "changelog.md"}


def slug(heading: str) -> str:
    """The anchor MkDocs (and GitHub) gives a heading."""
    s = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return re.sub(r"[\s]+", "-", s).strip("-")


def sections(readme: str) -> dict[str, str]:
    parts = re.split(r"(?m)^## ", readme)
    return {p.split("\n", 1)[0].strip(): "## " + p for p in parts[1:]}


def clean(text: str) -> str:
    text = re.sub(r'<p align="right">\(<a href="#readme-top">back to top</a>\)</p>\s*', "", text)
    return text


def rewrite(text: str, page_of: dict[str, str], here: str) -> str:
    """Links: to a heading on another page, to a page made from a repository file, to the repository."""
    def fix(target: str) -> str:
        if target.startswith("#"):
            page = page_of.get(target[1:])
            return target if page in (None, here) else f"{page}{target}"
        if re.match(r"^[a-z]+://|^mailto:", target):
            return target
        path = target.split("#")[0]
        if path.startswith("docs/images/"):
            return target.replace("docs/images/", "images/")
        if path in FILES:
            return FILES[path] + (target[len(path):] if len(target) > len(path) else "")
        if path == "README.md":
            return "index.md"
        return REPO + target
    text = re.sub(r"\]\(([^)\s]+)\)", lambda m: f"]({fix(m.group(1))})", text)
    text = re.sub(r'(href|src)="([^"]+)"', lambda m: f'{m.group(1)}="{fix(m.group(2))}"', text)
    return text


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    parts = sections(readme)
    missing = [s for names in PAGES.values() for s in names if s not in parts]
    if missing:
        raise SystemExit(f"README sections not found: {missing}")
    # Which page every heading's anchor lives on.
    page_of: dict[str, str] = {}
    for page, names in PAGES.items():
        for name in names:
            for h in re.findall(r"(?m)^#{2,4} (.+)$", parts[name]):
                page_of.setdefault(slug(h), page)
    page_of["readme-top"] = "index.md"
    for page, names in PAGES.items():
        body = "\n\n".join(clean(parts[n]).rstrip() for n in names)
        if page == "index.md":
            tagline = re.search(r"(The ANCHOR web automation agent:[\s\S]*?you stay in control\.)", readme)
            head = ("---\ntitle: ANCHOR web automation agent, self-healing and local (Ollama, Playwright)\n---\n\n"
                    "# ANCHOR\n\n**Adaptive Natural-language Control with Human Oversight and Recovery**\n\n")
            if tagline:
                head += " ".join(tagline.group(1).split()) + "\n\n"
            body = head + body
        elif len(names) == 1:
            # One section: it is the page's title, and its subheadings move up one level.
            body = re.sub(r"(?m)^#(#{1,5}) ", r"\1 ", body)
        else:
            body = f"# {TITLES[page]}\n\n" + body
        (OUT / page).write_text(rewrite(body, page_of, page) + "\n", encoding="utf-8")
    for src, dst in FILES.items():
        text = (ROOT / src).read_text(encoding="utf-8")
        (OUT / dst).write_text(rewrite(text, page_of, dst), encoding="utf-8")
    shutil.copytree(ROOT / "docs" / "images", OUT / "images")
    shutil.copytree(ROOT / "docs" / "site" / "assets", OUT / "assets")
    print(f"site_src/: {len(PAGES) + len(FILES)} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
