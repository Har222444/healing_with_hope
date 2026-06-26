"""
HEALING_WITH_HOPE — services/hope_injector.py
Combines LLaMA output + vagal score → technique recommendation.
"""

import logging, numpy as np
from typing import Optional
logger = logging.getLogger(__name__)

TECHNIQUES = {
    "panic_protocol": {
        "technique":      "bilateral_stimulation",
        "instruction":    "Tap left shoulder → right shoulder gently. ~30 sec.",
        "chatbot_action": "start_bilateral",
    },
    "calm_technique": {
        "technique":      "slow_breathing",
        "instruction":    "Inhale through nose, tiny sip, slow exhale. Repeat 3×.",
        "chatbot_action": "start_breathing",
    },
    "steady_support": {
        "technique":      "tiny_step",
        "instruction":    "Let's think of one small step you can take right now.",
        "chatbot_action": "show_tiny_step_prompt",
    },
}

_STATE_MAP = {
    "panic":    ("high",   "panic_protocol"),
    "suicidal": ("high",   "panic_protocol"),
    "stuck":    ("medium", "calm_technique"),
    "anxious":  ("medium", "calm_technique"),
    "sad":      ("low",    "steady_support"),
    "calm":     ("low",    "steady_support"),
}


class HopeInjector:
    def enrich(self, state: str, vagal_model,
               audio_features: Optional[np.ndarray] = None) -> dict:
        """
        If audio_features provided + vagal model loaded → real inference.
        Otherwise → state-based fallback.
        """
        if audio_features is not None and vagal_model.is_loaded:
            v = vagal_model.predict(audio_features)
        else:
            arousal, rec = _STATE_MAP.get(state, ("medium", "calm_technique"))
            v = {"vagal_score": None, "arousal_level": arousal, "recommendation": rec}

        rec = v.get("recommendation", "calm_technique")
        return {
            "vagal_score":    v.get("vagal_score"),
            "arousal_level":  v.get("arousal_level", "medium"),
            "recommendation": rec,
            "technique":      TECHNIQUES.get(rec, TECHNIQUES["calm_technique"]),
        }
