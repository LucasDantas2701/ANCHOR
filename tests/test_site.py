"""The documentation site is cut from the README and the command reference: every section, subsection,
guide paragraph and the "Why ANCHOR" list the site needs must exist (the site is published from main by
.github/workflows/pages.yml), and links between pages are rewritten."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def builder():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / ".github" / "scripts" / "build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_page_of_the_site_finds_what_it_is_made_of():
    site = builder().Site()
    site.build()                                  # raises if a section, subsection or guide paragraph is missing
    assert "docs/guides/logins.md" in site.pages and "commands/agent.md" in site.pages
    assert "template: home.html" in site.pages["pt-BR.md"] and "lang: pt" in site.pages["pt-BR.md"]   # the Portuguese landing page
    assert len(site.why()) >= 4                   # the landing page's cards


def test_links_to_other_pages_and_to_the_repository_are_rewritten():
    module = builder()
    site = module.Site()
    site.build()
    site.link_map()
    out = site.rewrite("See [the commands](docs/COMMANDS.md), [eval](eval/README.md) and ![x](docs/images/a.gif).",
                       "docs/guides/logins.md")
    assert "](../../commands/index.md)" in out and "](../../images/a.gif)" in out
    assert "](https://github.com/LucasDantas2701/ANCHOR/blob/main/eval/README.md)" in out
