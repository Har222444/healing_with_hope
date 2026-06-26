"""
HEALING WITH HOPE — api/routes/audio.py
"""

from fastapi import APIRouter, UploadFile, File, Form, Request, HTTPException
from datetime import datetime
import logging

# FIX: Import from the actual location
from services.audio_processor import AudioProcessor

logger = logging.getLogger(__name__)
router = APIRouter()

_processor = AudioProcessor()

@router.post("/process")
async def process_audio(
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Form(default="anonymous"),
):
    try:
        # Read file bytes directly
        raw_audio_bytes = await file.read()
        
        # Pass bytes to the processor
        features = _processor.extract_features_from_bytes(raw_audio_bytes)

        if features is None:
            return {"success": False, "error": "Feature extraction failed"}

        vagal_model = getattr(request.app.state, "vagal_model", None)
        if vagal_model is None or not getattr(vagal_model, "is_loaded", False):
            return {"success": False, "error": "Vagal model not loaded"}

        result = vagal_model.predict(features)

        return {
            "success": True,
            "vagal": result,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as exc:
        logger.error(f"❌ Audio route error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/status")
async def audio_status(request: Request):
    vagal_model = getattr(request.app.state, "vagal_model", None)
    return {
        "success": True,
        "vagal_loaded": getattr(vagal_model, "is_loaded", False),
    }