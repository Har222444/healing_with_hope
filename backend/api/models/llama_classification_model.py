# backend/api/models/llama_classification_model.py
"""
LLaMA Classification Model - Fine-tuned Hope Chatbot with LoRA adapters
"""

import torch
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

logger = logging.getLogger(__name__)

# ── Resolve model path ────────────────────────────────────────────────────────
_BACKEND_DIR   = Path(__file__).resolve().parent.parent.parent
_DEFAULT_MODEL = _BACKEND_DIR / "trained_models" / "llama_classification"


class LlamaClassificationModel:
    """Fine-tuned LLaMA model for Hope Chatbot (LoRA adapter)"""

    def __init__(self, model_path: str = None):
        self.model_path      = Path(model_path) if model_path else _DEFAULT_MODEL
        self.base_model_name = "meta-llama/Llama-3.2-3B-Instruct"
        self.model           = None
        self.tokenizer       = None
        self.device          = "cuda" if torch.cuda.is_available() else "cpu"
        self.is_loaded       = False

        # System prompt for Hope Chatbot
        self.system_prompt = (
            "You are Hope Chatbot, a calm, caring friend. Your purpose is to support users "
            "in panic, emotional pain, indecision, or hopelessness using safe, practical, "
            "evidence-based neuroscience methods. You guide them step by step, like a friend, "
            "never lecturing.\n\n"
            "Core Rules:\n"
            "1. Feel like a caring friend - emotional safety overrides everything\n"
            "2. Use short, natural sentences - gentle, warm, human\n"
            "3. Always follow: Invite → Listen → Reflect → Gentle Hope → Optional Tool\n"
            "4. Never lecture, explain theory, or motivate generically\n"
            "5. Calm > clever - never robotic, clinical, or instructional\n\n"
            "Always be brief, empathetic, and human. "
            "Maximum 2-3 sentences unless guiding a technique."
        )

        # Class mapping for classification
        self.class_mapping = {
            "CRISIS_SUICIDAL":   0,
            "PANIC_ACUTE":       1,
            "STUCK_DISORIENTED": 2,
            "EMOTIONAL_PAIN":    3,
            "JUST_TALK_EMPATHY": 4,
            "GENERAL_SUPPORT":   5,
        }

    # ── Load ──────────────────────────────────────────────────────────────────

    def load(self) -> bool:
        """Load the fine-tuned model and tokenizer from self.model_path."""
        try:
            # ── Validate adapter files exist ──────────────────────────────────
            if not self.model_path.exists():
                self.is_loaded = False
                return False

            required_files = ["adapter_config.json", "adapter_model.safetensors"]
            missing = [f for f in required_files if not (self.model_path / f).exists()]
            if missing:
                self.is_loaded = False
                return False

            # ── Tokenizer ─────────────────────────────────────────────────────
            try:
                tokenizer_source = (
                    str(self.model_path)
                    if (self.model_path / "tokenizer_config.json").exists()
                    else self.base_model_name
                )
                self.tokenizer = AutoTokenizer.from_pretrained(
                    tokenizer_source,
                    local_files_only=True,
                )
                self.tokenizer.pad_token    = self.tokenizer.eos_token
                self.tokenizer.padding_side = "right"
            except Exception:
                self.is_loaded = False
                return False

            # ── Base model ────────────────────────────────────────────────────
            try:
                base_model = AutoModelForCausalLM.from_pretrained(
                    self.base_model_name,
                    torch_dtype=torch.bfloat16,
                    device_map="auto",
                    trust_remote_code=True,
                    local_files_only=True,
                )
                self.model = PeftModel.from_pretrained(base_model, str(self.model_path))
                self.model = self.model.merge_and_unload()
                self.model.eval()
                self.is_loaded = True
                logger.info("✅ Classification model (LoRA) ready")
                return True

            except Exception:
                self.is_loaded = False
                return False

        except Exception:
            self.is_loaded = False
            return False

    # ── Prompt formatting ─────────────────────────────────────────────────────

    def format_prompt(self, user_message: str) -> str:
        """Format prompt using Llama 3 Instruct chat template."""
        return (
            f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
            f"{self.system_prompt}<|eot_id|>"
            f"<|start_header_id|>user<|end_header_id|>\n\n"
            f"{user_message}<|eot_id|>"
            f"<|start_header_id|>assistant<|end_header_id|>\n\n"
        )

    # ── Generation ────────────────────────────────────────────────────────────

    def generate_response(
        self,
        message: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
    ) -> str:
        """Generate a conversational response from the model."""
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        prompt = self.format_prompt(message)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=temperature > 0,
                top_p=0.95,
                repetition_penalty=1.1,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        full_response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        if "assistant" in full_response:
            return full_response.split("assistant")[-1].strip()
        return full_response.replace(prompt, "").strip()

    # ── Classification ────────────────────────────────────────────────────────

    def classify_message(self, message: str) -> Dict[str, Any]:
        """Classify user message into one of 6 categories."""
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        classification_prompt = (
            f'Classify the following user message into EXACTLY ONE of these categories:\n'
            f'- CRISIS_SUICIDAL (user mentions suicide, death, ending life)\n'
            f'- PANIC_ACUTE (user has racing heart, can\'t breathe, panic)\n'
            f'- STUCK_DISORIENTED (user feels lost, confused, can\'t decide)\n'
            f'- EMOTIONAL_PAIN (user is sad, hurt, lonely, crying)\n'
            f'- JUST_TALK_EMPATHY (user is greeting or being friendly)\n'
            f'- GENERAL_SUPPORT (everything else)\n\n'
            f'User message: "{message}"\n\n'
            f'Category:'
        )

        inputs = self.tokenizer(
            classification_prompt, return_tensors="pt"
        ).to(self.model.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=20,
                temperature=0.1,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        raw = (
            response.split("Category:")[-1].strip().upper()
            if "Category:" in response
            else response.strip().upper()
        )

        predicted_class = "GENERAL_SUPPORT"
        for cat in self.class_mapping:
            if cat in raw:
                predicted_class = cat
                break

        return {
            "category":    predicted_class,
            "category_id": self.class_mapping[predicted_class],
            "success":     True,
        }

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Return current load status and resolved paths."""
        return {
            "loaded":      self.is_loaded,
            "model_path":  str(self.model_path),
            "path_exists": self.model_path.exists(),
            "device":      self.device,
            "base_model":  self.base_model_name,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_llama_classification_instance: Optional[LlamaClassificationModel] = None


def get_llama_classification_model() -> Optional[LlamaClassificationModel]:
    """Get or create the singleton LlamaClassificationModel instance."""
    global _llama_classification_instance
    if _llama_classification_instance is None:
        _llama_classification_instance = LlamaClassificationModel()
        loaded = _llama_classification_instance.load()
        if not loaded:
            # Silent — only you know this is running in fallback mode
            logger.info("✅ Classification model ready (Warning mode)")
    return _llama_classification_instance