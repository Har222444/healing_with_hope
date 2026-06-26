"""
HEALING_WITH_HOPE — api/services/firebase_service.py

Handles core read/write transactions directly into root Firestore collections.
Provides a shared global structural database pointer (_db) for isolated service jobs.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

FIREBASE_OK = False
_db         = None

try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        _CRED_PATHS = [
            Path(__file__).parent.parent.parent / "firebase-credentials.json",  # backend/
            Path(__file__).parent.parent       / "firebase-credentials.json",  # api/
        ]
        cred_path = next((p for p in _CRED_PATHS if p.exists()), None)
        if not cred_path:
            raise FileNotFoundError(
                "firebase-credentials.json not found. Searched:\n" +
                "\n".join(str(p) for p in _CRED_PATHS)
            )
        firebase_admin.initialize_app(credentials.Certificate(str(cred_path)))
        logger.info(f"✅ Firebase initialised from {cred_path}")

    _db         = firestore.client()
    FIREBASE_OK = True

except ImportError:
    logger.warning("firebase-admin not installed — run: pip install firebase-admin")
except Exception as e:
    logger.error(f"Firebase init error: {e}")


class FirebaseService:

    def write_chatbot_output(
        self,
        user_id: str,
        ctx,
        new_tasks: list,
        new_goal: Optional[str],
        goal_timeframe: Optional[str],
    ) -> None:
        if not FIREBASE_OK or _db is None:
            logger.warning("Firestore not available — skipping write.")
            return
        try:
            if new_tasks:
                self._write_tiny_steps(user_id, new_tasks)
            if new_goal and goal_timeframe:
                self._write_hope_goal(user_id, new_goal, goal_timeframe)
        except Exception as e:
            logger.error(f"write_chatbot_output failed: {e}")

    def _write_tiny_steps(self, user_id: str, new_tasks: list) -> None:
        """
        Fallback direct task writer. Uses the uniform 'date' key to ensure
        unhindered integration with your async background task_generator pipeline.
        """
        from firebase_admin import firestore as fs
        col = _db.collection("tiny_steps")
        for task in new_tasks:
            col.add({
                "userId":           user_id,
                "task":             task,
                "completed":        False,
                "source":           "chatbot",
                "domain":           "GENERAL",
                "category":         "New",
                "time":             "Anytime",
                "history":          [False] * 31,
                "sage_highlighted": True,
                "sage_suggested":   False,
                "date":             fs.SERVER_TIMESTAMP, # 🔄 MATCHED: Changed from created_at to date
            })
        logger.info(f"[Firestore] {len(new_tasks)} tiny_step(s) written to root collection for user {user_id}")

    def _write_hope_goal(self, user_id: str, goal: str, timeframe: str) -> None:
        from firebase_admin import firestore as fs
        doc = (
            _db.collection("users")
               .document(user_id)
               .collection("hope_tasks")
               .document(timeframe)
        )
        doc.set(
            {"goals": fs.ArrayUnion([goal]), "updated_at": datetime.utcnow()},
            merge=True,
        )
        logger.info(f"[Firestore] Hope goal '{goal}' ({timeframe}) written for {user_id}")

    def _write_user_stats(self, user_id: str, ctx) -> None:
        if not FIREBASE_OK or _db is None:
            return
        try:
            # Safe parsing extraction of the state enum to structural primitive string types
            raw_state = getattr(ctx, "state", "neutral")
            state_str = raw_state.value if hasattr(raw_state, "value") else str(raw_state)

            _db.collection("users").document(user_id).set(
                {
                    "chat_count":     getattr(ctx, "chat_count", 0),
                    "last_active":    datetime.utcnow(),
                    "emotion_state":  state_str, # ✅ Enum serialized safely
                },
                merge=True,
            )
        except Exception as e:
            logger.error(f"_write_user_stats failed: {e}")


firebase_service = FirebaseService()