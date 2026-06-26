"""
HEALING WITH HOPE — api/dependencies.py

Provides a single shared HopeChatbot instance across all FastAPI routes.

Usage in any route file:
    from api.dependencies import get_chatbot
    from fastapi import Depends

    @router.post("/send")
    async def chat_send(req: ChatRequest, bot: HopeChatbot = Depends(get_chatbot)):
        ...

Why a module-level singleton (not FastAPI app.state)?
  - FastAPI Depends() needs a callable, not app.state
  - Module-level singleton is created once on first call to get_chatbot()
  - All subsequent calls return the same object — same ctx dict, same SBERT, same LLaMA
  - Thread-safe for reads; HopeChatbot internal state is per-uid so no cross-user collision
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level singleton — set on first get_chatbot() call
_chatbot_instance = None


def get_chatbot():
    """
    Returns the shared HopeChatbot singleton.
    Creates it on first call (which triggers LLaMA + SBERT load).
    All FastAPI routes that use Depends(get_chatbot) get the same object.
    """
    global _chatbot_instance
    if _chatbot_instance is None:
        try:
            from api.services.chatbot_logic import HopeChatbot
            _chatbot_instance = HopeChatbot()
            logger.info("✅ HopeChatbot singleton created")
        except Exception as e:
            logger.error(f"❌ Failed to create HopeChatbot: {e}")
            raise
    return _chatbot_instance