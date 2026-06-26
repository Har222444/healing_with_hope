"""
HEALING_WITH_HOPE — api/routes/user.py

Fixes applied:
✅ Shares the SAME HopeChatbot instance as chat.py via dependency injection
   (previously each route file created its own instance — contexts were isolated)
✅ POST /api/user/tiny-steps            — add a tiny step (Rule 45)
✅ POST /api/user/hope-goal             — add a hope goal (Rule 46)
✅ POST /api/user/confirm-hope-goal     — confirm after chatbot prompts save
✅ GET  /api/user/data/{user_id}        — retrieve user data
✅ DELETE /api/user/clear/{user_id}     — clear session
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.services.chatbot_logic import HopeChatbot
from api.dependencies import get_chatbot

router  = APIRouter()
logger  = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────
class TinyStepRequest(BaseModel):
    user_id: str
    step: str


class HopeGoalRequest(BaseModel):
    user_id: str
    goal: str
    timeframe: str = "3_months"    # "3_months" | "1_year" | "2_years"


class ConfirmHopeGoalRequest(BaseModel):
    user_id: str
    confirmed: bool                 # True = Yes add it, False = No thanks


# ── POST /api/user/tiny-steps ─────────────────────────────────────────────────
@router.post("/tiny-steps")
async def add_tiny_step(data: TinyStepRequest, bot: HopeChatbot = Depends(get_chatbot)):
    """
    Rule 45 / 48: Add a tiny step. Only called when user explicitly confirms 'Yes, add it'.
    Step is inserted at top of list.
    """
    try:
        step = data.step.strip()
        if not step:
            raise HTTPException(status_code=400, detail="Step text cannot be empty.")
        bot.add_tiny_step(data.user_id, step)
        return {
            "success":   True,
            "message":   "Tiny step added to top of list.",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error adding tiny step for {data.user_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ── POST /api/user/hope-goal ──────────────────────────────────────────────────
@router.post("/hope-goal")
async def add_hope_goal(data: HopeGoalRequest, bot: HopeChatbot = Depends(get_chatbot)):
    """
    Rule 46: Add a hope/goal under the selected timeframe section.
    Only one timeframe per addition.
    """
    try:
        goal = data.goal.strip()
        if not goal:
            raise HTTPException(status_code=400, detail="Goal text cannot be empty.")
        valid_timeframes = ("3_months", "1_year", "2_years")
        if data.timeframe not in valid_timeframes:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timeframe. Must be one of: {valid_timeframes}"
            )
        success = bot.add_hope_goal(data.user_id, goal, data.timeframe)
        if not success:
            raise HTTPException(status_code=400, detail="Could not add goal.")
        return {
            "success":   True,
            "message":   f"Hope goal added under {data.timeframe}.",
            "timeframe": data.timeframe,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error adding hope goal for {data.user_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ── POST /api/user/confirm-hope-goal ─────────────────────────────────────────
@router.post("/confirm-hope-goal")
async def confirm_hope_goal(
    data: ConfirmHopeGoalRequest,
    bot: HopeChatbot = Depends(get_chatbot)
):
    """
    Rule 48: User confirms (or declines) after chatbot prompts 'Shall I add this to your Hope page?'
    The pending goal was already staged in ctx._pending_hope_goal.
    """
    try:
        ctx = bot.contexts.get(data.user_id)
        if not ctx:
            raise HTTPException(status_code=404, detail="No active session found.")

        pending_goal = getattr(ctx, "_pending_hope_goal", None)
        timeframe    = ctx.hope_timeframe

        if data.confirmed and pending_goal and timeframe:
            bot.add_hope_goal(data.user_id, pending_goal, timeframe)
            ctx._pending_hope_goal = None
            timeframe_label = {"3_months": "3 months", "1_year": "1 year", "2_years": "2 years"}.get(timeframe, timeframe)
            return {
                "success":   True,
                "added":     True,
                "message":   f"Goal added to {timeframe_label} Hope page.",
                "timestamp": datetime.utcnow().isoformat(),
            }
        else:
            ctx._pending_hope_goal = None
            return {
                "success":   True,
                "added":     False,
                "message":   "Goal not saved — that's totally fine.",
                "timestamp": datetime.utcnow().isoformat(),
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error confirming hope goal for {data.user_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ── GET /api/user/data/{user_id} ──────────────────────────────────────────────
@router.get("/data/{user_id}")
async def get_user_data(user_id: str, bot: HopeChatbot = Depends(get_chatbot)):
    """Returns all stored data for a user (tiny steps + hope goals)."""
    try:
        data = bot.get_user_data(user_id)
        return {
            "success":   True,
            "data":      data,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.error(f"Error getting data for {user_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ── DELETE /api/user/clear/{user_id} ─────────────────────────────────────────
@router.delete("/clear/{user_id}")
async def clear_user(user_id: str, bot: HopeChatbot = Depends(get_chatbot)):
    """Clears the session context for a user."""
    try:
        bot.reset_user(user_id)
        return {"success": True, "message": "User session cleared."}
    except Exception as exc:
        logger.error(f"Error clearing user {user_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))