"""
HEALING_WITH_HOPE — api/services/situation_classifier.py

Stage 1 Situation Recognition — MentalBERT multi-head classifier.
Loaded ONCE at app startup (Step 3.5 in app.py).

Outputs per message:
  task_trigger  : "YES" | "NO"
  life_domain   : "STUDY" | "CAREER" | "EMOTIONAL" | "SOCIAL" |
                  "PHYSICAL" | "PURPOSE" | "OVERLOAD" | "UNDIRECTED"
  energy_level  : "LOW" | "MEDIUM" | "HIGH"
  confidence    : softmax probabilities dict per head
"""

import os
import json
import pickle
import logging
from typing import Optional, Dict

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)

# ── Model definition — must EXACTLY match the training notebook ───────────────

class MultiHeadSituationClassifier(nn.Module):
    def __init__(self, model_name: str, n_domain: int, n_energy: int,
                 dropout: float = 0.1, use_layer_norm: bool = True):
        super().__init__()
        from transformers import AutoModel
        self.encoder        = AutoModel.from_pretrained(model_name)
        h                   = self.encoder.config.hidden_size
        self.dropout        = nn.Dropout(dropout)
        self.use_layer_norm = use_layer_norm
        if use_layer_norm:
            self.layer_norm = nn.LayerNorm(h)

        self.trigger_head = nn.Linear(h, 2)
        self.domain_head  = nn.Linear(h, n_domain)

        energy_hidden          = h // 4
        self.energy_projection = nn.Sequential(
            nn.Linear(h, energy_hidden),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.energy_head = nn.Linear(energy_hidden, n_energy)

    def forward(self, input_ids, attention_mask):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        cls = out.last_hidden_state[:, 0, :]
        if self.use_layer_norm:
            cls = self.layer_norm(cls)
        cls = self.dropout(cls)
        return (
            self.trigger_head(cls),
            self.domain_head(cls),
            self.energy_head(self.energy_projection(cls)),
        )


# ── Singleton service ─────────────────────────────────────────────────────────

class SituationClassifierService:
    """
    Loads the MentalBERT Stage1 model once. Thread-safe for read (inference).
    Call classify(text) from chatbot_logic — it never raises, returns None on error.
    """

    def __init__(self):
        self.is_loaded    = False
        self._model       = None
        self._tokenizer   = None
        self._le_trigger  = None
        self._le_domain   = None
        self._le_energy   = None
        self._cfg         = {}
        self._device      = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def load(self, model_dir: str) -> bool:
        """
        model_dir — absolute path to stage1_backend/ folder
                     e.g. ./trained_models/stage1_backend
        """
        try:
            cfg_path     = os.path.join(model_dir, "config.json")
            weights_path = os.path.join(model_dir, "model_weights.pt")
            tok_dir      = os.path.join(model_dir, "tokenizer")
            enc_path     = os.path.join(model_dir, "label_encoders.pkl")

            # Validate mandatory paths before initializing memory objects
            for p in [cfg_path, weights_path, tok_dir, enc_path]:
                if not os.path.exists(p):
                    logger.error(f"SituationClassifier: missing file/dir: {p}")
                    return False

            with open(cfg_path, "r", encoding="utf-8") as f:
                self._cfg = json.load(f)

            from transformers import AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(tok_dir)
            logger.info("SituationClassifier: tokenizer loaded successfully")

            self._model = MultiHeadSituationClassifier(
                model_name     = self._cfg["base_model"],
                n_domain       = self._cfg["n_domain_classes"],
                n_energy       = self._cfg["n_energy_classes"],
                use_layer_norm = self._cfg.get("use_layer_norm", True),
            )
            
            self._model.load_state_dict(
                torch.load(weights_path, map_location=self._device)
            )
            self._model.to(self._device)
            self._model.eval()
            logger.info(f"SituationClassifier: weights parsed successfully onto hardware: {self._device}")

            with open(enc_path, "rb") as f:
                enc = pickle.load(f)
            self._le_trigger = enc["le_trigger"]
            self._le_domain  = enc["le_domain"]
            self._le_energy  = enc["le_energy"]

            self.is_loaded = True
            logger.info("✅ SituationClassifier initialization pipeline complete. Service ready.")
            return True

        except Exception as e:
            logger.error(f"SituationClassifier load fatal initialization failure: {e}", exc_info=True)
            return False

    def classify(self, text: str) -> Optional[Dict]:
        """
        Runs input token text sequences through all three active classifier output heads.
        Returns:
          {
            "task_trigger": "YES"|"NO",
            "life_domain":  "EMOTIONAL"|...,
            "energy_level": "HIGH"|"MEDIUM"|"LOW",
            "confidence": { ... }
          }
        Returns None silently on any exception error.
        """
        if not self.is_loaded or self._tokenizer is None or self._model is None:
            logger.warning("SituationClassifier invoked before load sequence completed successfully.")
            return None
        try:
            enc = self._tokenizer(
                text,
                max_length  = self._cfg.get("max_len", 64),
                padding     = "max_length",
                truncation  = True,
                return_tensors = "pt",
            )
            input_ids      = enc["input_ids"].to(self._device)
            attention_mask = enc["attention_mask"].to(self._device)

            with torch.no_grad():
                t_logits, d_logits, e_logits = self._model(input_ids, attention_mask)

            t_probs = torch.softmax(t_logits, dim=1).cpu().numpy()[0]
            d_probs = torch.softmax(d_logits, dim=1).cpu().numpy()[0]
            e_probs = torch.softmax(e_logits, dim=1).cpu().numpy()[0]

            trigger_pred = self._le_trigger.inverse_transform([t_logits.argmax(1).item()])[0]
            domain_pred  = self._le_domain.inverse_transform([d_logits.argmax(1).item()])[0]
            energy_pred  = self._le_energy.inverse_transform([e_logits.argmax(1).item()])[0]

            return {
                "task_trigger": str(trigger_pred),
                "life_domain":  str(domain_pred),
                "energy_level": str(energy_pred),
                "confidence": {
                    "task_trigger": {
                        str(c): round(float(p), 4)
                        for c, p in zip(self._le_trigger.classes_, t_probs)
                    },
                    "life_domain": {
                        str(c): round(float(p), 4)
                        for c, p in zip(self._le_domain.classes_, d_probs)
                    },
                    "energy_level": {
                        str(c): round(float(p), 4)
                        for c, p in zip(self._le_energy.classes_, e_probs)
                    },
                },
            }
        except Exception as e:
            logger.error(f"SituationClassifier.classify computation error: {e}")
            return None

    def status(self) -> Dict:
        return {
            "loaded":     self.is_loaded,
            "device":     str(self._device),
            "base_model": self._cfg.get("base_model", "unknown"),
            "final_run":  self._cfg.get("final_run", "unknown"),
        }


# ── Module-level singleton instantiation ──────────────────────────────────────

_situation_classifier: Optional[SituationClassifierService] = None


def get_situation_classifier() -> SituationClassifierService:
    global _situation_classifier
    if _situation_classifier is None:
        _situation_classifier = SituationClassifierService()
    return _situation_classifier