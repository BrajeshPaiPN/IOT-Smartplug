"""
Smart Solar Plug — Firebase RTDB Listener
Runs as a background thread. Subscribes to /telemetry on Firebase RTDB.
On new data: persists to SQLite, runs ML inference, stores alerts, broadcasts via WebSocket.
"""

import os
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Set

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, db as rtdb

# Script's own directory (backend/) and project root
_SCRIPT_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _SCRIPT_DIR.parent

# Resolve FIREBASE_CRED_PATH: if it's a relative path in .env, make it absolute
# relative to the SCRIPT directory so it works regardless of CWD at startup.
_raw_cred = os.getenv(
    "FIREBASE_CRED_PATH",
    str(_PROJECT_ROOT / "firebase admin key" / "smart-power-meter-873a6-firebase-adminsdk-fbsvc-92c81af5bd.json")
)
CRED_PATH = str((_SCRIPT_DIR / _raw_cred).resolve()) if not Path(_raw_cred).is_absolute() else _raw_cred

DATABASE_URL = os.getenv(
    "FIREBASE_DATABASE_URL",
    "https://smart-power-meter-873a6-default-rtdb.firebaseio.com/"
)

_firebase_app = None
_listener_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()

from telemetry_processor import process_telemetry


def _init_firebase():
    """Initialize Firebase Admin SDK (idempotent)."""
    global _firebase_app
    if _firebase_app is not None:
        return True
    try:
        if not Path(CRED_PATH).exists():
            print(f"[Firebase] Credential file not found: {CRED_PATH}")
            return False
        cred = credentials.Certificate(CRED_PATH)
        _firebase_app = firebase_admin.initialize_app(cred, {
            "databaseURL": DATABASE_URL
        })
        print(f"[Firebase] Initialized — {DATABASE_URL}")
        return True
    except Exception as e:
        print(f"[Firebase] Init error: {e}")
        return False





def start_listener(db_session_factory, ml_predict_cleaning, ml_predict_degradation):
    """Start the Firebase RTDB listener in a background thread."""
    global _listener_thread

    if not _init_firebase():
        print("[Firebase] Listener not started — Firebase init failed.")
        return

    def _listen():
        print("[Firebase] Starting RTDB listener on /telemetry ...")
        ref = rtdb.reference("/telemetry")
        last_data = {}

        while not _stop_event.is_set():
            try:
                data = ref.get()
                if data and data != last_data:
                    last_data = data
                    process_telemetry(data, db_session_factory, ml_predict_cleaning, ml_predict_degradation)
            except Exception as e:
                print(f"[Firebase] Listener error: {e}")
            time.sleep(5)  # Poll every 5 seconds

        print("[Firebase] Listener stopped.")

    _stop_event.clear()
    _listener_thread = threading.Thread(target=_listen, daemon=True, name="firebase-listener")
    _listener_thread.start()
    print("[Firebase] Background listener thread started.")


def stop_listener():
    """Stop the Firebase listener thread."""
    _stop_event.set()
    if _listener_thread:
        _listener_thread.join(timeout=10)
    print("[Firebase] Listener thread stopped.")
