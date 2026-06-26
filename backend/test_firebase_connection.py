"""
Test Firebase Connection - Standalone
Run: python test_firebase_connection.py
"""

import os
import sys
from pathlib import Path

# Add backend to path
backend_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(backend_root))

print("=" * 60)
print("🧪 Testing Firebase Connection")
print("=" * 60)

# Check if credentials file exists
cred_path = backend_root / "firebase-credentials.json"
print(f"\n1. Checking credentials file...")
print(f"   Path: {cred_path}")

if cred_path.exists():
    print(f"   ✅ File exists ({cred_path.stat().st_size} bytes)")
else:
    print(f"   ❌ File NOT found!")
    print(f"\n   Download from:")
    print(f"   https://console.firebase.google.com/")
    print(f"   Project Settings > Service Accounts > Generate new private key")
    sys.exit(1)

# Try to import firebase_service
print(f"\n2. Importing firebase_service...")
try:
    from backend.api.services.firebase_service import firebase_service
    print(f"   ✅ Import successful")
except Exception as e:
    print(f"   ❌ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test Firestore operations
print(f"\n3. Testing Firestore operations...")
try:
    # Test write
    test_ref = firebase_service.db.collection('test').document('test_doc')
    test_ref.set({'message': 'Hello from test!', 'timestamp': 'now'})
    print(f"   ✅ Write successful")
    
    # Test read
    doc = test_ref.get()
    if doc.exists:
        print(f"   ✅ Read successful: {doc.to_dict()}")
    
    # Test delete
    test_ref.delete()
    print(f"   ✅ Delete successful")
    
except Exception as e:
    print(f"   ❌ Firestore test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("🎉 All Firebase tests passed!")
print("=" * 60)