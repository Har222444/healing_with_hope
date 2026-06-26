"""
HEALING WITH HOPE — app.py

STARTUP ORDER:
  1. sys.path set so `api.*` resolves correctly
  2. firebase_service imported directly (it self-inits on import)
  3. LLaMA model loaded via Ollama
  4. Vagal model loaded
  4.5 Stage1 MentalBERT situation classifier loaded   ← NEW
  5. HopeChatbot singleton created
  6. Routers registered
"""

import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager

# ── PATH SETUP — must be first ────────────────────────────────────────────────
backend_root = Path(__file__).parent.absolute()
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── LIFESPAN ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "=" * 60)
    print("   HEALING WITH HOPE - Starting Up")
    print("=" * 60)

    # ── STEP 1: Firebase ──────────────────────────────────────────────────────
    try:
        from api.services.firebase_service import firebase_service, FIREBASE_OK
        app.state.firebase = firebase_service if FIREBASE_OK else None
        if FIREBASE_OK:
            print("  [OK] Firebase / Firestore ready")
        else:
            print("  [WARN] Firebase unavailable — check firebase-credentials.json")
    except Exception as e:
        print(f"  [FAIL] Firebase import failed: {e}")
        app.state.firebase = None

    # ── STEP 2: LLaMA via Ollama ──────────────────────────────────────────────
    try:
        from api.models.llama_model import HopeLlamaModel
        llama_path  = os.getenv("LLAMA_MODEL_PATH", "./trained_models/llama_hope")
        llama_model = HopeLlamaModel(model_path=llama_path)
        loaded      = llama_model.load(background=False)
        app.state.llama_model = llama_model if loaded else None
        if loaded:
            print("  [OK] LLaMA (llama3.2:3b via Ollama) ready")
        else:
            print("  [WARN] LLaMA not available — run: ollama pull llama3.2:3b")
    except Exception as e:
        print(f"  [WARN] LLaMA load failed: {e}")
        app.state.llama_model = None

    # ── STEP 3: Vagal model ───────────────────────────────────────────────────
    try:
        from api.models.vagal_model import VagalProxyModel
        vagal_path  = os.getenv("VAGAL_MODEL_PATH", "./trained_models/vagal_proxy_best.pth")
        vagal_model = VagalProxyModel(model_path=vagal_path)
        vagal_model.load()
        app.state.vagal_model = vagal_model
        print("  [OK] Vagal model ready")
    except Exception as e:
        print(f"  [WARN] Vagal model not loaded: {e}")
        app.state.vagal_model = None

    # ── STEP 3.5: LLaMA Classification Model ─────────────────────────────────
    try:
        from api.models.llama_classification_model import get_llama_classification_model
        llama_classification = get_llama_classification_model()
        app.state.llama_classification = llama_classification
        if llama_classification.is_loaded:
            print("  [OK] LLaMA Classification (Fine-tuned Hope Chatbot) ready")
        else:
            print("  [WARN] LLaMA Classification model not loaded")
    except Exception as e:
        print(f"  [WARN] LLaMA Classification load failed: {e}")
        app.state.llama_classification = None

    # ── STEP 4: Stage1 MentalBERT Situation Classifier ────────────────────────
    try:
        from api.services.situation_classifier import get_situation_classifier

        stage1_dir = os.getenv(
            "STAGE1_MODEL_DIR",
            str(backend_root / "trained_models" / "stage1_backend"),
        )

        # ── DEBUG: path & contents ─────────────────────────────────────────
        stage1_path = Path(stage1_dir)
        print(f"  [DEBUG] Stage1 dir       : {stage1_dir}")
        print(f"  [DEBUG] Dir exists       : {stage1_path.exists()}")

        if stage1_path.exists():
            contents = list(stage1_path.iterdir())
            print(f"  [DEBUG] Dir contents     : {[f.name for f in contents]}")

            required = ["model_weights.pt", "label_encoders.pkl", "config.json"]
            for req in required:
                found = (stage1_path / req).exists()
                print(f"  [DEBUG]   {req:<25}: {'FOUND' if found else 'MISSING ❌'}")

            tokenizer_dir = stage1_path / "tokenizer"
            print(f"  [DEBUG]   {'tokenizer/':<25}: {'FOUND' if tokenizer_dir.exists() else 'MISSING ❌'}")
        else:
            print(f"  [DEBUG] ❌ Folder does not exist at path above!")
            print(f"  [DEBUG]    Create it and unzip stage1_backend.zip from Colab into:")
            print(f"  [DEBUG]    {stage1_dir}")
        # ── END DEBUG ──────────────────────────────────────────────────────

        situation_clf = get_situation_classifier()

        try:
            loaded = situation_clf.load(stage1_dir)
        except Exception as load_err:
            print(f"  [DEBUG] situation_clf.load() raised exception: {load_err}")
            import traceback; traceback.print_exc()
            loaded = False

        app.state.situation_classifier = situation_clf if loaded else None

        if loaded:
            status = situation_clf.status()
            print("  [OK] Stage1 MentalBERT Situation Classifier ready")
            print(f"       Model : {status['base_model']}")
            print(f"       Device: {status['device']}")
            print(f"       Run   : {status['final_run']}")
        else:
            print("  [WARN] Stage1 classifier not loaded — see DEBUG lines above")

    except Exception as e:
        print(f"  [WARN] Stage1 classifier load failed: {e}")
        import traceback; traceback.print_exc()
        app.state.situation_classifier = None

    # ── STEP 5: HopeChatbot singleton ─────────────────────────────────────────
    try:
        from api.dependencies import get_chatbot
        chatbot = get_chatbot()

        chatbot._situation_classifier = getattr(app.state, "situation_classifier", None)
        chatbot._firebase_service     = getattr(app.state, "firebase", None)

        app.state.chatbot = chatbot
        llama_status = chatbot.llama_status()
        sbert_ready  = llama_status.get("sbert", {}).get("ready", False)
        llama_ready  = llama_status.get("llama", {}).get("loaded", False)
        print("  [OK] HopeChatbot singleton ready")
        print(f"       LLaMA loaded       : {llama_ready}")
        print(f"       SBERT ready        : {sbert_ready}")
        print(f"       Stage1 injected    : {chatbot._situation_classifier is not None}")
        print(f"       Firebase injected  : {chatbot._firebase_service is not None}")
    except Exception as e:
        print(f"  [FAIL] HopeChatbot init failed: {e}")
        import traceback; traceback.print_exc()
        app.state.chatbot = None

    print("=" * 60)
    print("   Ready at http://localhost:8000")
    print("=" * 60 + "\n")

    yield

    print("\nHealing with Hope - Shutting down gracefully")


# ── APP ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Healing with Hope API",
    version="2.0.0",
    description="Mental wellness chatbot API - LLaMA + SBERT + Firebase + MentalBERT",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── ROUTERS ───────────────────────────────────────────────────────────────────
try:
    from api.routes.chat import router as chat_router
    app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
    print("  [OK] /api/chat router registered")
except Exception as e:
    print(f"  [FAIL] Chat router failed: {e}")

try:
    from api.routes.user import router as user_router
    app.include_router(user_router, prefix="/api/user", tags=["user"])
    print("  [OK] /api/user router registered")
except Exception as e:
    print(f"  [FAIL] User router failed: {e}")

try:
    from api.routes.audio import router as audio_router
    app.include_router(audio_router, prefix="/api/audio", tags=["audio"])
    print("  [OK] /api/audio router registered")
except Exception as e:
    print(f"  [FAIL] Audio router failed: {e}")


# ── HEALTH ────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"message": "Healing with Hope API is running", "version": "2.0.0"}


@app.get("/health")
async def health():
    chatbot  = getattr(app.state, "chatbot",               None)
    firebase = getattr(app.state, "firebase",              None)
    vagal    = getattr(app.state, "vagal_model",           None)
    stage1   = getattr(app.state, "situation_classifier",  None)

    llama_ok = sbert_ok = False
    if chatbot:
        status   = chatbot.llama_status()
        llama_ok = status.get("llama", {}).get("loaded", False)
        sbert_ok = status.get("sbert", {}).get("ready",  False)

    return {
        "status":             "healthy" if llama_ok else "degraded",
        "llama_loaded":       llama_ok,
        "sbert_ready":        sbert_ok,
        "firebase_ready":     firebase is not None,
        "vagal_loaded":       getattr(vagal, "is_loaded", False),
        "chatbot_ready":      chatbot is not None,
        "stage1_classifier":  stage1.status() if stage1 else {"loaded": False},
    }


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=["trained_models/*", "*.pth", "*.bin", "*.pt"],
    )