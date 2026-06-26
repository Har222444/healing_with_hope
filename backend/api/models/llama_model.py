"""
HEALING_WITH_HOPE - api/models/llama_model.py
Uses Ollama API — zero RAM usage. Optimized for fast responses.

NOTE: This model is used ONLY for Hope's chat responses.
     Task generation uses the Together API (task_generator.py) — never this model.
"""

import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:1b"

# ── Hope chat persona rules ────────────────────────────────────────────────────
_BASE_RULES = (
    "You are Hope, a warm and grounded friend - never a therapist or robot. "
    "You speak simply, gently, and briefly.\n\n"
    "Hard rules:\n"
    "- Keep responses concise (around 2-3 sentences max). Always finish your final sentence completely.\n"
    "- Empathy comes first. Reflect the user feeling before anything else.\n"
    "- Never give advice lists or lecture.\n"
    "- Never use clinical words: cognitive, neural, cortex, oxytocin, dopamine.\n"
    "- Always end with one open question.\n"
    "- PANIC state: ground only, breath or tapping, no advice.\n"
    "- SUICIDAL state: only provide contacts - "
    "Sumithrayo 011 269 6666 | CCCline 1333 | National 1926.\n"
    "- Never repeat the user words verbatim. Paraphrase with warmth.\n"
    "- Never say I understand how you feel - show it instead.\n"
)

_STATE_OVERLAYS = {
    "sad":      "User is sad. Validate briefly. Ask what feels hardest.",
    "anxious":  "User is anxious. Acknowledge tension briefly. Ask what weighs most.",
    "stuck":    "User feels stuck. Normalize it. Ask one orienting question.",
    "panic":    "User in panic. Be very calm. Offer ONE grounding action only.",
    "neutral":  "User is calm. Respond warmly. Ask what is on their mind.",
    "calm":     "User is settled. Reflect gently. Ask what feels meaningful.",
    "suicidal": "User expressed self-harm. Quiet care. Provide crisis contacts immediately.",
}


class HopeLlamaModel:

    def __init__(self, model_path: str = "./trained_models/llama_hope"):
        self.model_path  = model_path
        self.is_loaded   = False
        self._ollama_ok  = False

    def load(self, background: bool = False) -> bool:
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=5)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                if any("llama3.2" in m for m in models):
                    self.is_loaded  = True
                    self._ollama_ok = True
                    logger.info("✅ Ollama llama3.2:1b ready")
                    return True
                else:
                    logger.error("llama3.2:1b not found. Run: ollama pull llama3.2:1b")
            else:
                logger.error("Ollama not responding. Run: ollama serve")
        except Exception as e:
            logger.error(f"Ollama connection failed: {e}")
        self.is_loaded = False
        return False

    @property
    def is_ready(self) -> bool:
        return self.is_loaded

    def _build_system_prompt(
        self,
        state: str = "neutral",
        context_summary: Optional[str] = None,
        memory_hint: Optional[str] = None,
        extra_instruction: Optional[str] = None,
    ) -> str:
        parts = [_BASE_RULES]
        overlay = _STATE_OVERLAYS.get(state.lower(), _STATE_OVERLAYS["neutral"])
        parts.append(f"State: {state.upper()}. {overlay}")

        # Keep context SHORT — long context = slow Ollama
        if context_summary:
            parts.append(f"Recent: {context_summary[:150]}")
        if memory_hint:
            parts.append(f"Note: {memory_hint[:80]}")
        if extra_instruction:
            parts.append(extra_instruction[:600])

        return "\n".join(parts)

    def generate(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        max_new_tokens: int = 200,
        temperature: float = 0.72,
        top_p: float = 0.90,
        repetition_penalty: float = 1.18,
    ) -> Optional[str]:
        """
        Generate a Hope chat response.
        This method is for conversational replies ONLY — not task generation.
        Task generation is handled exclusively by task_generator.py.
        """
        if not self.is_loaded:
            return None

        sys = system_prompt or _BASE_RULES

        try:
            payload = {
                "model":  OLLAMA_MODEL,
                "prompt": user_message[:300],
                "system": sys,
                "stream": False,
                "options": {
                    "temperature":    temperature,
                    "top_p":          top_p,
                    "num_predict":    max_new_tokens,
                    "repeat_penalty": repetition_penalty,
                    "num_ctx":        512,
                    "stop":           ["User:", "Assistant:"],
                },
            }
            r = requests.post(OLLAMA_URL, json=payload, timeout=25)
            if r.status_code == 200:
                text = r.json().get("response", "").strip()
                return text if text and len(text) >= 8 else None
            else:
                logger.error(f"Ollama API error: {r.status_code}")
                return None
        except requests.exceptions.Timeout:
            logger.error("Ollama timed out after 25s")
            return None
        except Exception as e:
            logger.error(f"Ollama generate error: {e}")
            return None

    def generate_with_context(
        self,
        user_message: str,
        state: str = "neutral",
        context_summary: Optional[str] = None,
        memory_hint: Optional[str] = None,
        extra_instruction: Optional[str] = None,
        **kwargs,
    ) -> Optional[str]:
        system_prompt = self._build_system_prompt(
            state=state,
            context_summary=context_summary,
            memory_hint=memory_hint,
            extra_instruction=extra_instruction,
        )
        return self.generate(user_message, system_prompt=system_prompt, **kwargs)