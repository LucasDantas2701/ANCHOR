"""
How a saved automation is stored: one folder per automation.

    automations/<name>/
        automation.json   request, link, model and browser profiles, prompt language
        plan.json         the approved plan (goals and steps), once learned
        memory.json       the choice memory of this automation
        recoveries.json   how the automation recovered when the site changed (reviewable, undoable)
        notes.json        the user's notes after runs that did not work, sent to the planner
        confirmations.json  the user's decisions on sensitive actions (allowed or denied)
        runs/             one record per run, with its metrics

The folder is usage data and stays out of Git, like memory/.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from anchor.planner import Goal, Step

FORMAT_VERSION = 1
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class AutomationError(ValueError):
    """An automation that does not exist, already exists, or has an invalid name."""


@dataclass
class Automation:
    name: str
    request: str
    url: str
    profile: str
    browser_profile: Optional[str] = None
    prompt_language: Optional[str] = None     # None: the model profile's
    parameters: list[str] = field(default_factory=list)   # placeholders of the request: {nome}, {cpf}
    created: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    version: int = FORMAT_VERSION


@dataclass
class ApprovedPlan:
    steps: list[Step]
    goals: list[Goal]
    approved: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    source_run: str = ""
    language: str = "pt"       # the language the model read when the plan was learned


class AutomationStore:
    """The automations folder (default: automations/ in the current directory)."""

    def __init__(self, root: str | Path = "automations"):
        self.root = Path(root)

    # ------------------------------------------------------------ paths
    def folder(self, name: str) -> Path:
        return self.root / name

    def memory_path(self, name: str) -> Path:
        return self.folder(name) / "memory.json"

    # ------------------------------------------------------------ automations
    def create(self, automation: Automation) -> Automation:
        if not NAME_RE.match(automation.name):
            raise AutomationError(f"invalid name {automation.name!r}: use lowercase letters, digits, - and _")
        folder = self.folder(automation.name)
        if (folder / "automation.json").exists():
            raise AutomationError(f"automation {automation.name!r} already exists")
        from .params import find_parameters
        automation.parameters = find_parameters(automation.request)
        (folder / "runs").mkdir(parents=True, exist_ok=True)
        self._write(folder / "automation.json", asdict(automation))
        return automation

    def load(self, name: str) -> Automation:
        path = self.folder(name) / "automation.json"
        if not path.exists():
            raise AutomationError(f"automation {name!r} does not exist")
        data = json.loads(path.read_text(encoding="utf-8"))
        return Automation(**{k: v for k, v in data.items() if k in Automation.__dataclass_fields__})

    def names(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.parent.name for p in self.root.glob("*/automation.json"))

    # ------------------------------------------------------------ approved plan
    def load_plan(self, name: str) -> Optional[ApprovedPlan]:
        path = self.folder(name) / "plan.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ApprovedPlan(
            steps=[Step(**s) for s in data["steps"]],
            goals=[Goal(**g) for g in data.get("goals", [])],
            approved=data.get("approved", ""),
            source_run=data.get("source_run", ""),
            language=data.get("language", "pt"),
        )

    def save_plan(self, name: str, plan: ApprovedPlan) -> None:
        self._write(self.folder(name) / "plan.json", {
            "version": FORMAT_VERSION, "approved": plan.approved, "source_run": plan.source_run,
            "language": plan.language,
            "goals": [asdict(g) for g in plan.goals], "steps": [asdict(s) for s in plan.steps],
        })

    def forget_plan(self, name: str) -> bool:
        path = self.folder(name) / "plan.json"
        if path.exists():
            path.unlink()
            return True
        return False

    # ------------------------------------------------------------ recoveries
    def recoveries(self, name: str) -> list[dict]:
        path = self.folder(name) / "recoveries.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def add_recovery(self, name: str, record: dict) -> dict:
        items = self.recoveries(name)
        record = {"number": len(items) + 1, "date": datetime.now().isoformat(timespec="seconds"),
                  "undone": False, **record}
        items.append(record)
        self._write_list(self.folder(name) / "recoveries.json", items)
        return record

    def mark_undone(self, name: str, numbers: set[int]) -> None:
        items = self.recoveries(name)
        for item in items:
            if item["number"] in numbers:
                item["undone"] = True
        self._write_list(self.folder(name) / "recoveries.json", items)

    # ------------------------------------------------------------ user notes
    NOTES_SENT = 5      # how many of the most recent notes go to the planner

    def notes(self, name: str) -> list[dict]:
        path = self.folder(name) / "notes.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def add_note(self, name: str, text: str, run: str = "") -> dict:
        items = self.notes(name)
        note = {"number": max((n["number"] for n in items), default=0) + 1,
                "date": datetime.now().isoformat(timespec="seconds"), "run": run, "text": text.strip()}
        items.append(note)
        self._write_list(self.folder(name) / "notes.json", items)
        return note

    def remove_note(self, name: str, number: int) -> bool:
        items = self.notes(name)
        kept = [n for n in items if n["number"] != number]
        self._write_list(self.folder(name) / "notes.json", kept)
        return len(kept) < len(items)

    def recent_notes(self, name: str) -> list[str]:
        return [n["text"] for n in self.notes(name)[-self.NOTES_SENT:]]

    # ------------------------------------------------------------ sensitive actions
    def confirmations(self, name: str) -> list[dict]:
        path = self.folder(name) / "confirmations.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def add_confirmation(self, name: str, decision: dict) -> dict:
        items = self.confirmations(name)
        record = {"number": max((i["number"] for i in items), default=0) + 1,
                  "date": datetime.now().isoformat(timespec="seconds"), **decision}
        items.append(record)
        self._write_list(self.folder(name) / "confirmations.json", items)
        return record

    def forget_confirmation(self, name: str, number: int) -> bool:
        items = self.confirmations(name)
        kept = [i for i in items if i["number"] != number]
        self._write_list(self.folder(name) / "confirmations.json", kept)
        return len(kept) < len(items)

    # ------------------------------------------------------------ runs
    def save_run(self, name: str, record: dict) -> str:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self._write(self.folder(name) / "runs" / f"{run_id}.json", {"id": run_id, **record})
        return run_id

    def runs(self, name: str) -> list[dict]:
        folder = self.folder(name) / "runs"
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]

    @staticmethod
    def _write_list(path: Path, data: list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _write(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
