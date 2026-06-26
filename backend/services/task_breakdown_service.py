"""HEALING_WITH_HOPE — services/task_breakdown_service.py"""

import logging
from typing import List
logger = logging.getLogger(__name__)

_TEMPLATES = {
    "work":      ["Open the document / app", "Write just one sentence",
                  "Set a 5-min timer and start", "Save what you have"],
    "chores":    ["Pick up just one item", "Put that item away",
                  "Rinse one dish", "Take one bag to the bin"],
    "self_care": ["Drink a glass of water", "Wash your face",
                  "Change into comfortable clothes", "Sit quietly for 2 min"],
    "social":    ["Open the message", "Type one sentence reply",
                  "Send without rereading", "Close the app"],
    "default":   ["Sit where you are for 30 sec", "Take three slow breaths",
                  "Name one tiny thing you can do in 2 min",
                  "Do just that one thing"],
}


class TaskBreakdownService:
    def breakdown(self, desc: str) -> List[str]:
        d = desc.lower()
        if any(w in d for w in ("work","report","email","meeting","deadline")):
            cat = "work"
        elif any(w in d for w in ("clean","dishes","laundry","tidy","chore")):
            cat = "chores"
        elif any(w in d for w in ("shower","eat","sleep","rest","self")):
            cat = "self_care"
        elif any(w in d for w in ("message","call","reply","friend","family")):
            cat = "social"
        else:
            cat = "default"
        return _TEMPLATES[cat]

    def to_list(self, desc: str) -> List[dict]:
        return [{"id": i + 1, "step": s, "done": False}
                for i, s in enumerate(self.breakdown(desc))]
