#!/usr/bin/env python3
"""
start_backend.py — Run this instead of uvicorn directly.
Place this file in your backend/ folder.
Run: python start_backend.py

Does pre-flight checks before starting so you know exactly what's wrong.
"""
import os
import sys
import subprocess
from pathlib import Path

# ── Make sure we're in the backend folder ─────────────────────────────────────
script_dir = Path(__file__).parent.absolute()
os.chdir(script_dir)
sys.path.insert(0, str(script_dir))

print("\n" + "=" * 60)
print("  💜  HEALING WITH HOPE — Pre-flight Check")
print("=" * 60)

errors = []

# ── 1. Check firebase credentials ─────────────────────────────────────────────
cred = script_dir / "firebase-credentials.json"
if cred.exists():
    print("  ✅  firebase-credentials.json found")
else:
    print("  ❌  firebase-credentials.json MISSING")
    errors.append("Put your Firebase credentials JSON in backend/firebase-credentials.json")

# ── 2. Check for space-named files (import killers) ───────────────────────────
services = script_dir / "api" / "services"
if services.exists():
    for f in services.iterdir():
        if " " in f.name and f.suffix == ".py":
            fixed = f.parent / f.name.replace(" ", "_")
            print(f"  🔧  Renaming: '{f.name}' → '{fixed.name}'")
            f.rename(fixed)
    print("  ✅  No space-named Python files")

# ── 3. Check .env ──────────────────────────────────────────────────────────────
env_file = script_dir / ".env"
if env_file.exists():
    print("  ✅  .env found")
else:
    print("  ⚠️   .env not found — creating minimal one")
    env_file.write_text(
        "LLAMA_MODEL_PATH=./trained_models/llama_hope\n"
        "VAGAL_MODEL_PATH=./trained_models/vagal_proxy_best.pth\n"
    )

# ── 4. Check critical Python files exist ──────────────────────────────────────
required = [
    "app.py",
    "api/__init__.py",
    "api/routes/chat.py",
    "api/services/chatbot_logic.py",
    "api/services/sage_listener.py",
    "api/services/sage_connector.py",
    "api/services/sage_memory.py",
    "api/dependencies.py",
]
for r in required:
    p = script_dir / r
    if p.exists():
        print(f"  ✅  {r}")
    else:
        print(f"  ❌  MISSING: {r}")
        errors.append(f"File not found: {r}")

print("=" * 60)

if errors:
    print("\n  🛑  Fix these issues before starting:\n")
    for e in errors:
        print(f"     • {e}")
    print()
    sys.exit(1)

print("\n  🚀  Starting server on http://localhost:8000\n")
print("  Test it: open http://localhost:8000 in your browser")
print("  Stop it: Ctrl+C\n")
print("=" * 60 + "\n")

# ── Start uvicorn ──────────────────────────────────────────────────────────────
subprocess.run([
    sys.executable, "-m", "uvicorn",
    "app:app",
    "--reload",
    "--port", "8000",
    "--host", "0.0.0.0",
])