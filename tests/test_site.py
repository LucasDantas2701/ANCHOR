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


def test_links_inside_raw_html_are_written_from_the_site_root():
    """MkDocs does not adjust raw HTML: an <img> on a page two levels down must not break."""
    module = builder()
    site = module.Site()
    site.build()
    site.link_map()
    out = site.rewrite('<img src="docs/images/a.gif"> <a href="docs/COMMANDS.md">x</a>', "docs/introduction.md")
    assert 'src="/ANCHOR/images/a.gif"' in out and 'href="/ANCHOR/commands/"' in out


def test_no_page_has_an_unresolved_reference_link_or_an_unfixed_image_path(tmp_path):
    """Badges ([![Python][python-shield]][python-url]) need their definitions on the page, and the dark version
    of a figure (srcset) its path from the site's root: both showed broken on the 0.5 site."""
    import re
    site = builder().Site()
    site.build()
    site.link_map()
    assert len(site.pages) > 30
    for file, text in site.pages.items():
        out = site.rewrite(text, file, commands_doc=file.startswith("commands/"))
        defined = set(re.findall(r"(?m)^\[([^\]]+)\]:\s*\S+", out))
        unresolved = set(re.findall(r"\]\[([^\]]+)\]", out)) - defined
        assert not unresolved, f"{file}: reference links with no definition: {sorted(unresolved)}"
        assert not re.search(r'(src|srcset|href)="docs/images/', out), f"{file}: an image path not from the site's root"


def test_the_workflow_puts_the_website_at_the_root_over_the_documentation():
    """The site's root is the website (landing/): the workflow builds it after MkDocs and copies it over."""
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert workflow.index("mkdocs build") < workflow.index("npm run build") < workflow.index("cp -r dist/. ../site/")
    assert "working-directory: landing" in workflow
    angular = (ROOT / "landing" / "angular.json").read_text(encoding="utf-8")
    assert '"baseHref": "/ANCHOR/"' in angular


def test_the_documentation_links_skip_the_website():
    """The interface's Documentation button and the README's go to the documentation, not to the website."""
    from anchor.ui.server import DOCS_URL
    assert DOCS_URL.endswith("/ANCHOR/docs/introduction/")
    assert "docs/introduction/" in (ROOT / "web" / "src" / "app" / "app.ts").read_text(encoding="utf-8")
