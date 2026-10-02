"""
The command reference (docs/COMMANDS.md) must document every option and subcommand that
the command-line tools show in --help. A new option without documentation fails here.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "docs" / "COMMANDS.md").read_text(encoding="utf-8")

TOOLS = [
    ["anchor.agent"],
    ["anchor.planner"],
    ["anchor.automations"],
    ["anchor.automations", "create"],
    ["anchor.automations", "run"],
    ["anchor.automations", "list"],
    ["anchor.automations", "show"],
    ["anchor.automations", "recoveries"],
    ["anchor.automations", "undo"],
    ["anchor.engine.memory", "file", "list"],
    ["anchor.engine.memory", "file", "forget"],
    ["anchor.engine.memory", "file", "clear"],
    ["eval.run"],
    ["eval.plan_run"],
]
IGNORED = {"-h", "--help", "-m", "-v"}


def help_text(tool):
    out = subprocess.run([sys.executable, "-m", *tool, "--help"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


@pytest.mark.parametrize("tool", TOOLS, ids=[" ".join(t) for t in TOOLS])
def test_every_option_is_documented(tool):
    options = set(re.findall(r"(?<![\w-])(--?[a-z][a-z-]*)", help_text(tool))) - IGNORED
    missing = sorted(o for o in options if f"`{o}`" not in DOC)
    assert missing == [], f"undocumented options of {' '.join(tool)}: {missing}"


def test_every_subcommand_is_documented():
    text = help_text(["anchor.automations"])
    commands = re.search(r"\{([a-z,]+)\}", text).group(1).split(",")
    missing = [c for c in commands if f"`{c}" not in DOC]
    assert missing == [], f"undocumented subcommands: {missing}"


OTHER_DOCS = [ROOT / "README.md", ROOT / "eval" / "README.md"]


def test_every_module_in_the_docs_exists():
    import importlib.util
    for text in [DOC] + [p.read_text(encoding="utf-8") for p in OTHER_DOCS]:
        for module in sorted(set(re.findall(r"python -m ([\w.]+)", text))):
            if module in ("venv", "pip"):
                continue
            assert importlib.util.find_spec(module) is not None, module


@pytest.mark.parametrize("path", OTHER_DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_options_used_in_the_other_docs_are_in_the_reference(path):
    """A README example with an option the reference does not know is out of date."""
    blocks = re.findall(r"```(?:sh|text)?\n(.*?)```", path.read_text(encoding="utf-8"), re.S)
    options = {o for b in blocks for line in b.splitlines() if "python -m" in line
               for o in re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", line)}
    missing = sorted(o for o in options if f"`{o}`" not in DOC)
    assert missing == [], f"options in {path.name} missing from the reference: {missing}"


def test_every_command_line_tool_is_documented():
    """Every module that can be run with python -m appears in the reference."""
    modules = set()
    for folder in ("anchor", "eval", "examples"):
        for path in (ROOT / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if path.name == "__main__.py":
                modules.add(".".join(path.relative_to(ROOT).parent.parts))
            elif re.search(r"__name__ == [\"']__main__[\"']", text):
                modules.add(".".join(path.relative_to(ROOT).with_suffix("").parts))
    missing = sorted(m for m in modules if f"python -m {m}" not in DOC)
    assert missing == [], f"undocumented tools: {missing}"


def test_every_memory_command_is_documented():
    text = help_text(["anchor.engine.memory"])
    commands = re.search(r"\{([a-z,]+)\}", text).group(1).split(",")
    missing = [c for c in commands if f"`{c}" not in DOC]
    assert missing == [], f"undocumented memory commands: {missing}"


def test_every_profile_field_is_documented():
    from dataclasses import fields

    from anchor.planner.config import LLMProfile
    missing = [f.name for f in fields(LLMProfile) if f"`{f.name}`" not in DOC]
    assert missing == [], f"undocumented profile fields: {missing}"


def test_every_environment_variable_is_documented():
    names = set()
    for folder in ("anchor", "eval", "examples", "tests"):
        for path in (ROOT / folder).rglob("*.py"):
            names |= set(re.findall(r"environ(?:\.get)?\(?\[?[\"']([A-Z_]+)[\"']", path.read_text(encoding="utf-8")))
    missing = sorted(n for n in names if f"`{n}`" not in DOC)
    assert missing == [], f"undocumented environment variables: {missing}"
