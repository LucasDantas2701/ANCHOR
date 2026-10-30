"""The documentation site is cut from the README's sections: every section a page needs must exist,
and every link between pages must work (the site is published from main by .github/workflows/pages.yml)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def builder():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / ".github" / "scripts" / "build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_page_of_the_site_has_its_readme_sections():
    site = builder()
    parts = site.sections((ROOT / "README.md").read_text(encoding="utf-8"))
    missing = [s for names in site.PAGES.values() for s in names if s not in parts]
    assert not missing, f"README sections the site needs were renamed or removed: {missing}"
    assert all((ROOT / src).is_file() for src in site.FILES)


def test_links_to_other_pages_and_to_the_repository_are_rewritten():
    site = builder()
    text = "See [usage](#usage), [the commands](docs/COMMANDS.md#agent), [eval](eval/README.md) and ![x](docs/images/a.gif)."
    out = site.rewrite(text, {"usage": "usage.md"}, "index.md")
    assert "](usage.md#usage)" in out and "](commands.md#agent)" in out
    assert "](https://github.com/LucasDantas2701/ANCHOR/blob/main/eval/README.md)" in out and "](images/a.gif)" in out
