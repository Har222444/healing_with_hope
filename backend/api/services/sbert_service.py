"""
HEALING_WITH_HOPE — api/services/sbert_service.py
Optimized with embedding cache for fast repeated encodes.
"""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

SBERT_OK    = False
_model      = None
_MODEL_NAME = "all-MiniLM-L6-v2"
_cache: Dict[str, any] = {}   # embedding cache — avoids re-encoding same strings


try:
    from sentence_transformers import SentenceTransformer, util
    _model   = SentenceTransformer(_MODEL_NAME)
    SBERT_OK = True
    logger.info(f"✅ SBERT loaded: {_MODEL_NAME}")
except ImportError:
    logger.warning("sentence-transformers not installed — run: pip install sentence-transformers")
except Exception as e:
    logger.warning(f"SBERT load failed: {e}")


def _encode_cached(text: str):
    """Encode with in-memory cache — avoids re-encoding identical strings."""
    if text not in _cache:
        if len(_cache) > 500:   # prevent unbounded growth
            _cache.clear()
        _cache[text] = _model.encode(text, convert_to_tensor=True)
    return _cache[text]


class SBERTService:

    def status(self) -> Dict:
        """Called by chatbot_logic.llama_status() — MUST exist."""
        return {
            "ready": self.is_ready,
            "model": _MODEL_NAME if SBERT_OK else None,
        }

    @property
    def is_ready(self) -> bool:
        return SBERT_OK and _model is not None

    @property
    def ready(self) -> bool:
        return self.is_ready

    def encode(self, texts):
        if not self.is_ready:
            raise RuntimeError("SBERT not available")
        if isinstance(texts, str):
            return _encode_cached(texts)
        return _model.encode(texts, convert_to_tensor=True)

    def similarity(self, text_a: str, text_b: str) -> float:
        if not self.is_ready:
            return 0.0
        from sentence_transformers import util
        return float(util.cos_sim(_encode_cached(text_a), _encode_cached(text_b))[0][0])

    def most_similar(self, query: str, candidates: List[str]) -> str:
        if not self.is_ready or not candidates:
            return candidates[0] if candidates else ""
        from sentence_transformers import util
        query_emb = _encode_cached(query)
        cand_embs = _model.encode(candidates, convert_to_tensor=True)
        scores    = util.cos_sim(query_emb, cand_embs)[0]
        return candidates[int(scores.argmax())]

    def goal_proximity(self, message: str, goal: str) -> float:
        return self.similarity(message, goal)

    def rank_tasks(self, situation: str, tasks: List[str]) -> List[str]:
        if not self.is_ready or not tasks or not situation:
            return tasks
        from sentence_transformers import util
        sit_emb   = _encode_cached(situation)
        task_embs = _model.encode(tasks, convert_to_tensor=True)
        scores    = util.cos_sim(sit_emb, task_embs)[0]
        ranked    = sorted(zip(tasks, scores.tolist()), key=lambda x: x[1], reverse=True)
        return [t for t, _ in ranked]


# ── Warmup — pre-encode so first real request is instant ──────────────────────
if SBERT_OK and _model is not None:
    try:
        _encode_cached("warmup")
        logger.info("✅ SBERT warmup complete.")
    except Exception as e:
        logger.warning(f"SBERT warmup skipped: {e}")

sbert_service = SBERTService()