"""
Saved automations: describe the task once, run it whenever you want.

The first run learns: the agent plans with the LLM, the user breaks ties, and
the plan that worked is saved as approved. The next runs replay the approved
plan without calling the LLM, with the same choice memory, heuristic, effect
checks and goals as the agent.
"""

from .model import Automation, AutomationError, AutomationStore
from .replay import ReplayPlanner, SavedPlanBroken
from .runner import run_automation

__all__ = ["Automation", "AutomationError", "AutomationStore", "ReplayPlanner", "SavedPlanBroken",
           "run_automation"]
