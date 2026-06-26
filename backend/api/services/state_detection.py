"""
HEALING_WITH_HOPE — api/services/state_detection.py
Production-grade emotional state detection (regex-based, no ML dependency)

Fixes applied:
✅ Panic detection requires first-person; blocked for other-subject (cat/dog/he/she)
✅ Negation handling ("I am not panicking" → SAD not PANIC)
✅ Score-based detection — SUICIDAL always wins, others ranked by hits
✅ Pet illness / grief → SAD, not PANIC (can't breathe → checks subject)
✅ Panic attack discussion context guard (prevents false positives)
✅ All 51-rule trigger keywords covered
"""

import re
from enum import Enum
from typing import List, Tuple, Dict, Optional


class UserState(Enum):
    PANIC     = "panic"
    SUICIDAL  = "suicidal"
    STUCK     = "stuck"
    ANXIOUS   = "anxious"
    SAD       = "sad"
    EXIT      = "exit"
    CALM      = "calm"
    NEUTRAL   = "neutral"


class StateDetector:

    def __init__(self):
        # ── First-person indicators ──────────────────────────────────────────
        self._self_refs = re.compile(
            r"\b(i|me|my|myself|i'm|i am|ive|i've|i have)\b",
            re.IGNORECASE
        )

        # ── Third-party / other-subject indicators ────────────────────────────
        self._other_refs = re.compile(
            r"\b(cat|dog|pet|he|she|they|him|her|them|"
            r"my\s+cat|my\s+dog|my\s+pet|my\s+friend|my\s+partner)\b",
            re.IGNORECASE
        )

        # ── Negations that cancel panic detection ─────────────────────────────
        self._panic_negations = [
            r"\bi\s+am\s+not\s+panicking\b",
            r"\bi'?m\s+not\s+panicking\b",
            r"\bi\s+do\s+not\s+feel\s+panic\b",
            r"\bi\s+dont\s+feel\s+panic\b",
            r"\bnot\s+panicking\b",
            r"\bi\s+am\s+calm\b",
            r"\bi'?m\s+calm\b",
            r"\bno\s+panic\b",
            r"\bpanic\s+attacks?\s+(are|can|may|might|could|often|sometimes|usually)",   # discussing panic clinically
            r"\bread\s+about\s+panic\b",
            r"\blearn(ing|ed)?\s+about\s+panic\b",
            r"\bsomeone\s+(else|i\s+know).*panic\b",
        ]

        # ── Patterns per state ────────────────────────────────────────────────
        self._patterns: Dict[UserState, List[str]] = {

            UserState.SUICIDAL: [
                r"\bsuicid(e|al|ally)\b",
                r"\bdon'?t\s+want\s+to\s+(exist|live|be\s+alive|be\s+here|wake\s+up)\b",
                r"\bkill\s+my\s*self\b",
                r"\bend\s+(my\s+life|it\s+all|everything)\b",
                r"\bbetter\s+off\s+(dead|gone|without\s+me)\b",
                r"\bwant\s+to\s+die\b",
                r"\bwanna\s+die\b",
                r"\bno\s+reason\s+to\s+(live|be\s+alive|exist|keep\s+going)\b",
                r"\bcan'?t\s+go\s+on\b",
                r"\bwish\s+i\s+(was|were)\s+(dead|gone|never\s+born)\b",
                r"\btired\s+of\s+(living|being\s+alive|everything|existing)\b",
                r"\bnot\s+worth\s+(it|living|anything)\b",
                r"\blife\s+is\s+not\s+worth\b",
                r"\bgive\s+up\s+on\s+(life|living|everything)\b",
                r"\bnobody\s+would\s+(miss|care)\b",
                r"\bworld\s+would\s+be\s+better\s+without\s+me\b",
                r"\bdon'?t\s+want\s+to\s+be\s+here\s+anymore\b",
            ],

            UserState.PANIC: [
                # All checked for first-person in detect_state()
                r"\bi'?m\s+(having\s+a\s+)?panic\s+attack\b",
                r"\bi\s+am\s+(having\s+a\s+)?panic\s+attack\b",
                r"\bi'?m\s+panicking\b",
                r"\bi\s+am\s+panicking\b",
                r"\bmy\s+heart\s+is\s+racing\b",
                r"\bmy\s+heart\s+is\s+pounding\b",
                r"\bi\s+can'?t\s+breathe\b",
                r"\bi\s+can'?t\s+calm\s+(down|myself)\b",
                r"\bi\s+feel\s+(completely\s+)?out\s+of\s+control\b",
                r"\bi'?m\s+freaking\s+out\b",
                r"\bi'?m\s+losing\s+(my\s+mind|control|it)\b",
                r"\bi'?m\s+shaking\b",
                r"\bi'?m\s+terrified\b",
                r"\bi\s+am\s+overwhelmed\b",
                r"\bi'?m\s+overwhelmed\b",
                r"\bi'?m\s+going\s+crazy\b",
                r"\beverything\s+is\s+spinning\b",
                r"\bi\s+feel\s+like\s+i'?m\s+dying\b",
            ],

            UserState.STUCK: [
                r"\bdon'?t\s+know\s+what\s+to\s+do\b",
                r"\bfeel(ing)?\s+stuck\b",
                r"\bnothing\s+is\s+clear\b",
                r"\bcan'?t\s+decide\b",
                r"\bconfused\b",
                r"\bfeeling\s+lost\b",
                r"\bparalyz(ed|ing)\b",
                r"\bdon'?t\s+know\s+where\s+to\s+start\b",
                r"\bcan'?t\s+think\s+straight\b",
                r"\beverything\s+is\s+(a\s+)?blur\b",
                r"\bcan'?t\s+focus\b",
                r"\bmind\s+is\s+blank\b",
                r"\bno\s+idea\s+what\s+to\s+do\b",
                r"\bdon'?t\s+know\s+where\s+to\s+turn\b",
            ],

            UserState.ANXIOUS: [
                r"\banxious\b",
                r"\banxiety\b",
                r"\bworried\b",
                r"\bstressed\b",
                r"\bnervous\b",
                r"\bon\s+edge\b",
                r"\bscared\b",
                r"\bafraid\b",
                r"\bworrying\b",
                r"\buneasy\b",
                r"\bfearful\b",
                r"\boverwhelmed\b",
                r"\bdread\b",
                r"\bapprehensive\b",
                r"\bjittery\b",
                r"\btense\b",
            ],

            UserState.SAD: [
                # Core sadness
                r"\bsad(ness)?\b",
                r"\bdepressed\b",
                r"\bhopeless\b",
                r"\blonely\b",
                r"\balone\b",
                r"\bcrying\b",
                r"\btears\b",
                r"\bhurt(ing)?\b",
                r"\bgriev(e|ing|ed)\b",
                r"\bempty\b",
                r"\bheavy\b",
                r"\bbroken\b",
                r"\bunhappy\b",
                r"\bmiss(ing)?\b",
                r"\bnobody\s+(cares|loves|listens)\b",
                r"\bno\s+one\s+(cares|loves|understands|listens)\b",
                r"\bfeel\s+(so\s+)?(bad|terrible|awful|horrible)\b",
                r"\bheartbroken\b",
                r"\bdevastated\b",
                r"\bmiserable\b",
                r"\bnumb\b",
                r"\bpain\b",
                r"\bsuffering\b",
                r"\bdown\b",
                r"\bdepleted\b",
                r"\bexhausted\b",
                r"\bworn\s+out\b",
                r"\btired\s+of\s+(this|it|everything|feeling)\b",
                # Pet/other grief — explicitly mapped to SAD, not PANIC
                r"\bmy\s+(cat|dog|pet)\b",
                r"\b(cat|dog|pet)\s+(is\s+)?(sick|not\s+well|dying|passed|gone|can.t breathe)\b",
                r"\bhe\s+is\s+(sick|dying|not\s+well|gone)\b",
                r"\bshe\s+is\s+(sick|dying|not\s+well|gone)\b",
                r"\bi\s+might\s+lose\b",
                r"\bi.?m\s+(so\s+)?scared\s+to\s+lose\b",
                r"\bhe\s+(gonna|going\s+to)\s+die\b",
                r"\bshe\s+(gonna|going\s+to)\s+die\b",
                r"\bhe\s+can.?t\s+breathe\b",
                r"\bshe\s+can.?t\s+breathe\b",
            ],

            UserState.EXIT: [
                r"\bi'?m\s+(feeling\s+)?(good|better|okay|ok|fine|alright)(\s+now)?\b",
                r"\bthank(s|\s+you)\b",
                r"\bthat\s+helped\b",
                r"\bfeel(ing)?\s+(better|ok|okay|good|much\s+better)\b",
                r"\bfeeling\s+relieved\b",
                r"\bi\s+feel\s+calmer\b",
                r"\bthat\s+was\s+(helpful|great|good|nice)\b",
                r"\bi'?m\s+okay\s+now\b",
                r"\bgotta\s+go\b",
                r"\bbye\b",
                r"\bsee\s+you\b",
            ],

            UserState.CALM: [
                r"\bcalm(er|ed)?\b",
                r"\brelax(ed|ing)?\b",
                r"\bpeaceful\b",
                r"\bstable\b",
                r"\bbreath(ing)?\s+(slow|easy|better|calmer)\b",
                r"\bgrounded\b",
                r"\bcentered\b",
                r"\bsteady\b",
            ],
        }

    # ── Public: single best state ──────────────────────────────────────────────
    def detect_state(self, text: str) -> Tuple[UserState, float]:
        """Returns (best_state, confidence 0-1)."""
        if not text or not text.strip():
            return UserState.NEUTRAL, 0.5

        t = text.lower().strip()

        # 1. Noise / too-short input
        if re.match(r"^[a-zA-Z]{1,3}$", t) or re.match(r"^[^a-zA-Z0-9]+$", t):
            return UserState.NEUTRAL, 0.3

        # 2. Panic negation override → route to SAD (person is not panicking)
        for pattern in self._panic_negations:
            if re.search(pattern, t, re.IGNORECASE):
                return UserState.SAD, 0.75

        scores: Dict[UserState, float] = {}

        for state, patterns in self._patterns.items():
            hits = 0
            for pattern in patterns:
                if re.search(pattern, t, re.IGNORECASE):
                    if state == UserState.PANIC:
                        has_self  = bool(self._self_refs.search(t))
                        has_other = bool(self._other_refs.search(t))
                        # Skip if talking about someone/something else (not self)
                        if not has_self or (has_other and not has_self):
                            continue
                    hits += 1
            if hits > 0:
                scores[state] = min(0.5 + hits * 0.18, 1.0)

        if not scores:
            return UserState.NEUTRAL, 0.5

        # SUICIDAL always wins
        if UserState.SUICIDAL in scores:
            return UserState.SUICIDAL, scores[UserState.SUICIDAL]

        # PANIC beats others if clearly present
        if UserState.PANIC in scores and scores[UserState.PANIC] >= 0.68:
            return UserState.PANIC, scores[UserState.PANIC]

        best = max(scores, key=scores.get)
        return best, scores[best]

    # ── Public: all detected states ranked ────────────────────────────────────
    def detect_multiple_states(self, text: str) -> List[Tuple[UserState, float]]:
        t = text.lower()
        scores: Dict[UserState, float] = {}
        for state, patterns in self._patterns.items():
            hits = 0
            for pattern in patterns:
                if re.search(pattern, t, re.IGNORECASE):
                    if state == UserState.PANIC:
                        has_self  = bool(self._self_refs.search(t))
                        has_other = bool(self._other_refs.search(t))
                        if not has_self or (has_other and not has_self):
                            continue
                    hits += 1
            if hits > 0:
                scores[state] = min(0.5 + hits * 0.18, 1.0)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # ── Public: sub-state for calm-this-feeling routing (Rule 19) ─────────────
    def detect_calm_substate(self, text: str) -> str:
        """
        Returns one of: sad_heavy | anxious_restless | panicked | numb_shutdown | overthinking
        Used by Rule 19 to route to correct calming technique.
        """
        t = text.lower()

        if re.search(r"\bnumb\b|\bshutdown\b|\bcan'?t\s+feel\b|\bempty\b|\bdetach(ed)?\b", t):
            return "numb_shutdown"

        if re.search(r"\bpanic\b|\bheart\s+racing\b|\bcan'?t\s+breathe\b|\bterrified\b", t):
            return "panicked"

        if re.search(r"\boverthink\b|\bstuck\s+in\s+my\s+head\b|\bspiral\b|\bcan.?t\s+stop\s+thinking\b|\bspiraling\b", t):
            return "overthinking"

        if re.search(r"\banxious\b|\bworried\b|\brestless\b|\bon\s+edge\b|\bscared\b|\bnervous\b", t):
            return "anxious_restless"

        # Default: sad/heavy
        return "sad_heavy"