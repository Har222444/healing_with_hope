import os
import firebase_admin
from firebase_admin import credentials, firestore
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Setup paths
backend_dir = Path(__file__).parent.absolute()
cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", str(backend_dir / "firebase-credentials.json"))

# Initialize Firebase
if not firebase_admin._apps:
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase initialized in database.py")
    else:
        print(f"❌ Firebase credentials not found at {cred_path}")

db = firestore.client()