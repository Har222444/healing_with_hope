"""
HEALING_WITH_HOPE — api/routes/chat.py

CHANGES:
  ✅ Automatically intercepts, strips, and cleans leaked JSON/RULES text from user chat bubble.
  ✅ Extracts raw JSON array using regex even if LLaMA appends garbage text or trailing rule blocks.
  ✅ Robust key matching supports BOTH 'tasks' and 'tiny_steps' out-of-the-box.
  ✅ Safely forces updating context variables so the page layout updates instantly.
  ✅ Retains background asynchronous threads for fire-and-forget Firestore updates.
"""

import re
import json
import logging
import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.services.chatbot_logic import HopeChatbot
from api.services.firebase_service import firebase_service
from api.dependencies import get_chatbot

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    user_id: str
    message: str
    state: Optional[str] = None
    technique_index: Optional[int] = None


class SilenceRequest(BaseModel):
    duration_seconds: int


# ── POST /api/chat/send ───────────────────────────────────────────────────────

@router.post("/send")
async def chat_send(req: ChatRequest, bot: HopeChatbot = Depends(get_chatbot)):
    """Main entry point for the Hope chatbot."""
    try:
        user_message = req.message.strip()
        if not user_message:
            return {"success": False, "error": "Message cannot be empty."}

        # ── Snapshot ctx BEFORE processing so we can diff new tasks/goals ────
        ctx_before = bot.contexts.get(req.user_id)
        tasks_before: list = list(ctx_before.tiny_steps) if ctx_before else []
        goals_before: dict = {
            tf: list(goals)
            for tf, goals in (ctx_before.hope_goals.items() if ctx_before else {})
        }

        # ── Core chatbot call ─────────────────────────────────────────────────
        response_data = bot.process_message(uid=req.user_id, message=user_message)
        
        raw_text = response_data.get("text", "")

        # ── Snapshot ctx AFTER processing ────────────────────────────────────
        ctx_after = bot.contexts.get(req.user_id)

        # ── Advanced Regex Extraction & Sanitization for Tiny Steps ───────────
        if ctx_after:
            try:
                # Find any valid JSON block structure { ... } hidden in the response text
                json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                if json_match:
                    clean_json_str = json_match.group(0)
                    parsed_data = json.loads(clean_json_str)
                    
                    # Handle both template variations seamlessly
                    extracted_tasks = parsed_data.get("tiny_steps") or parsed_data.get("tasks") or []
                    if extracted_tasks and isinstance(extracted_tasks, list):
                        # Force commit tasks into context so state changes take effect
                        ctx_after.tiny_steps = extracted_tasks
                        logger.info(f"Successfully sync'd context tiny_steps for {req.user_id}: {ctx_after.tiny_steps}")
            except Exception as json_err:
                logger.warning(f"Failed parsing leaked raw task blocks into context: {json_err}")

        # ── Clean up user-facing text bubble ──────────────────────────────────
        # Drop JSON bracket leaks and rule prompt instructions from displaying on the UI
        if "{" in raw_text or "RULES:" in raw_text:
            clean_display_text = raw_text.split("{")[0].split("RULES:")[0].strip()
            # If everything gets truncated, give a warm fallback message
            raw_text = clean_display_text if clean_display_text else "I've added these tiny steps to your dashboard layout. Let's take them one slow pace at a time."

        # ── Diff: find tasks added THIS turn ─────────────────────────────────
        tasks_after: list = list(ctx_after.tiny_steps) if ctx_after else []
        new_tasks = [t for t in tasks_after if t not in tasks_before]

        # ── Diff: find hope goals added THIS turn ────────────────────────────
        new_goal: Optional[str] = None
        new_goal_timeframe: Optional[str] = None
        if ctx_after:
            for tf, goals in ctx_after.hope_goals.items():
                before_set = set(goals_before.get(tf, []))
                for g in goals:
                    if g not in before_set:
                        new_goal = g
                        new_goal_timeframe = tf
                        break
                if new_goal:
                    break

        # ── Fire-and-forget Firestore write (never blocks response) ──────────
        if ctx_after and (new_tasks or new_goal):
            def _write():
                try:
                    firebase_service.write_chatbot_output(
                        user_id=req.user_id,
                        ctx=ctx_after,
                        new_tasks=new_tasks,
                        new_goal=new_goal,
                        goal_timeframe=new_goal_timeframe,
                    )
                except Exception as e:
                    logger.error(f"Background Firestore write failed: {e}")

            threading.Thread(target=_write, daemon=True).start()

        # Also write user_stats on every turn (lightweight merge=True update)
        if ctx_after:
            def _stats():
                try:
                    firebase_service._write_user_stats(req.user_id, ctx_after)
                except Exception as e:
                    logger.error(f"Background stats write failed: {e}")

            threading.Thread(target=_stats, daemon=True).start()

        # ── Build response ────────────────────────────────────────────────────
        options   = response_data.get("options", [])
        metadata  = response_data.get("metadata", {})

        menu_options = [opt["label"] for opt in options if "label" in opt]
        option_ids   = [opt["id"]    for opt in options if "id"    in opt]
        show_menu    = len(menu_options) > 0

        detected_state = metadata.get("state", "neutral").upper()
        is_crisis      = detected_state in ("SUICIDAL", "CRISIS", "PANIC")
        hope_capture   = metadata.get("state") == "hope_input"

        chat_count = ctx_after.chat_count if ctx_after else 0

        return {
            "success":            True,
            "response":           raw_text, # Clean sanitized messaging text
            "state":              detected_state,
            "detected_emotion":   metadata.get("state", "neutral"),
            "show_menu":          show_menu,
            "menu_options":       menu_options,
            "option_ids":         option_ids,
            "crisis_detected":    is_crisis,
            "hope_capture_mode":  hope_capture,
            "conversation_count": chat_count,
            "tasks_saved":        len(new_tasks),
            "goal_saved":         bool(new_goal),
            "timestamp":          datetime.utcnow().isoformat(),
        }

    except Exception as exc:
        logger.error(f"Chat error for user {req.user_id}: {exc}", exc_info=True)
        return {
            "success":            False,
            "response":           "I'm having a little trouble right now. Please try again 💜",
            "state":              "NORMAL",
            "detected_emotion":   "neutral",
            "show_menu":          False,
            "menu_options":       [],
            "option_ids":         [],
            "crisis_detected":    False,
            "hope_capture_mode":  False,
            "conversation_count": 0,
            "tasks_saved":        0,
            "goal_saved":         False,
        }


# ── POST /api/chat/silence/{user_id} ─────────────────────────────────────────

@router.post("/silence/{user_id}")
async def chat_silence(
    user_id: str,
    req: SilenceRequest,
    bot: HopeChatbot = Depends(get_chatbot),
):
    try:
        response_data = bot.handle_silence(uid=user_id, duration_seconds=req.duration_seconds)
        text     = response_data.get("text", "")
        options  = response_data.get("options", [])
        metadata = response_data.get("metadata", {})

        return {
            "success":      True,
            "response":     text,
            "state":        metadata.get("state", "silence").upper(),
            "show_menu":    len(options) > 0,
            "menu_options": [opt["label"] for opt in options if "label" in opt],
            "option_ids":   [opt["id"]    for opt in options if "id"    in opt],
            "timestamp":    datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.error(f"Silence handler error for {user_id}: {exc}", exc_info=True)
        return {"success": False, "error": str(exc)}


# ── GET /api/chat/history/{user_id} ──────────────────────────────────────────

@router.get("/history/{user_id}")
async def get_chat_history(user_id: str, bot: HopeChatbot = Depends(get_chatbot)):
    try:
        history = bot.get_history(user_id)
        return {
            "success":   True,
            "history":   history,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.error(f"History error for {user_id}: {exc}")
        return {"success": False, "error": "Could not retrieve history."}


# ── Alias POST /api/chat/ ─────────────────────────────────────────────────────

@router.post("/")
async def chat_endpoint(req: ChatRequest, bot: HopeChatbot = Depends(get_chatbot)):
    return await chat_send(req, bot)