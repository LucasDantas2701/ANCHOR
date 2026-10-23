"""
Where a measurement was made: the commit (full and short), its tag, and whether the working copy
was the commit's, with nothing changed. Every result file of eval/ records it.

A development run with uncommitted changes is allowed, but its files get "+dirty" in their name and
the list of what had changed (the results of 21-22/10 were measured with fixes not yet committed,
and their files said only the old commit). A final run (--final) is refused unless the working copy
is clean and the commit has a tag: the release is tagged first, and its results say so.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUTPUTS = ("eval/results/",)              # where the measurements themselves are written


def _git(repo: Path, *args: str, keep_lines: bool = False) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout
    return out.rstrip("\n") if keep_lines else out.strip()     # "git status" lines start with a space


def provenance(repo: Path = REPO) -> dict:
    """{"commit", "commit_full", "tag", "clean", "changed"} for the working copy at repo."""
    try:
        full = _git(repo, "rev-parse", "HEAD")
    except Exception:
        return {"commit": "no-git", "commit_full": "", "tag": "", "clean": False, "changed": []}
    try:
        tag = _git(repo, "describe", "--tags", "--exact-match", "HEAD")
    except Exception:
        tag = ""
    changed = []
    for line in _git(repo, "status", "--porcelain", "--untracked-files=all", keep_lines=True).splitlines():
        path = line[3:].strip().strip('"')
        if path and not path.startswith(OUTPUTS):
            changed.append(path)
    return {"commit": full[:7], "commit_full": full, "tag": tag, "clean": not changed, "changed": changed[:30]}


def in_name(p: dict) -> str:
    """The commit as it goes in a result file's name: "+dirty" when the working copy had changes."""
    return p["commit"] + ("" if p["clean"] else "+dirty")


def final_problem(p: dict) -> str:
    """Why a final run may not run here ("" when it may)."""
    if p["commit"] == "no-git":
        return "a final run needs the repository (git) to record its commit."
    if not p["clean"]:
        return ("a final run needs a working copy with nothing changed; commit or undo these first: "
                + ", ".join(p["changed"][:10]) + (" ..." if len(p["changed"]) > 10 else ""))
    if not p["tag"]:
        return "a final run needs the release's tag on this commit (create it first, e.g. git tag v1.0.0)."
    return ""


def warn_if_dirty(p: dict) -> None:
    if not p["clean"]:
        print(f"[warning] measuring with uncommitted changes ({len(p['changed'])} file(s)): "
              f"the results are named {in_name(p)} and list them.")
