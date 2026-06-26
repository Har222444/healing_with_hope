"""
HEALING_WITH_HOPE — services/trauma_embed.py
Trauma-informed prompt context injected into LLaMA system prompt.
"""

import logging
from typing import Optional
logger = logging.getLogger(__name__)

_MODIFIERS = {
    "high": {
        "tone":        "extremely gentle, slow, grounding",
        "instruction": "Very short sentences. No questions. No advice. Just presence.",
        "prefix":      "You're safe right now.",
    },
    "medium": {
        "tone":        "warm, calm, non-directive",
        "instruction": "Validate first, then offer ONE option. No lists.",
        "prefix":      "I'm here with you.",
    },
    "low": {
        "tone":        "encouraging, hopeful, gentle",
        "instruction": "Can introduce a small forward step. Keep it optional.",
        "prefix":      "I'm glad you're feeling steadier.",
    },
    "unknown": {
        "tone":        "calm, warm, patient",
        "instruction": "Follow the user's pace. Validate before anything else.",
        "prefix":      "I'm here.",
    },
}

_EXTRA = {
    "suicidal": (
        " This person may be in crisis. Do NOT say 'everything will be okay'. "
        "Acknowledge their pain. Provide crisis contacts at the end."
    ),
    "panic": (
        " This person is in acute panic. No questions. No advice. "
        "Ground them with presence only."
    ),
}


class TraumaEmbed:
    def build_context(self, state: str, arousal_level: str = "medium",
                      vagal_score: Optional[float] = None) -> dict:
        mod   = _MODIFIERS.get(arousal_level, _MODIFIERS["unknown"])
        extra = _EXTRA.get(state, "")
        full  = (
            f"TRAUMA-INFORMED CONTEXT:\n"
            f"  State        : {state}\n"
            f"  Arousal      : {arousal_level}"
            + (f" (vagal={vagal_score:.2f})" if vagal_score else "")
            + f"\n  Tone         : {mod['tone']}\n"
            f"  Instruction  : {mod['instruction']}{extra}\n"
            f"  Opening      : \"{mod['prefix']}\"\n"
        )
        return {"tone": mod["tone"], "instruction": mod["instruction"] + extra,
                "prefix": mod["prefix"], "full_context": full}

    def enrich_prompt(self, base_prompt: str, state: str,
                      arousal_level: str = "medium",
                      vagal_score: Optional[float] = None) -> str:
        return self.build_context(state, arousal_level, vagal_score)["full_context"] \
               + "\n" + base_prompt
