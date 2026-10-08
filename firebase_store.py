"""Optional Firestore-backed persistence for the Telegram bot.

The bot keeps its JSON files as a local cache and fallback. When Firebase
credentials are present, every JSON state file is also mirrored to Firestore,
so Railway restarts do not erase users, balances, settings, or order history.

Credentials must be supplied through Railway environment variables; never
commit a service-account JSON file to the project.
"""

from __future__ import annotations

import base64
import json
import os
import threading
from pathlib import Path
from typing import Any


_firebase_lock = threading.RLock()
_firebase_db = None
_firebase_ready = False
_firebase_attempted = False
_collection_name = os.environ.get("FIREBASE_COLLECTION", "bot_state").strip() or "bot_state"


def _credential_options():
    """Return Firebase Admin credentials/options without exposing secrets."""
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        return {"kind": "certificate", "value": json.loads(raw)}

    encoded = os.environ.get("FIREBASE_SERVICE_ACCOUNT_BASE64", "").strip()
    if encoded:
        decoded = base64.b64decode(encoded).decode("utf-8")
        return {"kind": "certificate", "value": json.loads(decoded)}

    credentials_path = os.environ.get(
        "FIREBASE_CREDENTIALS_PATH",
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""),
    ).strip()
    if credentials_path:
        return {"kind": "path", "value": credentials_path}

    # Application Default Credentials are useful locally and on GCP. Railway
    # deployments normally use FIREBASE_SERVICE_ACCOUNT_JSON instead.
    if os.environ.get("FIREBASE_PROJECT_ID", "").strip():
        return {"kind": "application_default", "value": None}
    return None


def _init_firebase():
    global _firebase_db, _firebase_ready, _firebase_attempted
    with _firebase_lock:
        if _firebase_attempted:
            return _firebase_db
        _firebase_attempted = True

        if os.environ.get("FIREBASE_DISABLE", "").strip().lower() in {
            "1", "true", "yes", "on"
        }:
            print("[FIREBASE] Disabled by FIREBASE_DISABLE", flush=True)
            return None

        options = _credential_options()
        if options is None:
            print(
                "[FIREBASE] Not configured; using local JSON persistence. "
                "Set FIREBASE_SERVICE_ACCOUNT_JSON on Railway to enable Firestore.",
                flush=True,
            )
            return None

        try:
            import firebase_admin
            from firebase_admin import credentials, firestore

            if options["kind"] == "certificate":
                cred = credentials.Certificate(options["value"])
                project_id = options["value"].get("project_id")
            elif options["kind"] == "path":
                cred = credentials.Certificate(options["value"])
                project_id = None
            else:
                cred = credentials.ApplicationDefault()
                project_id = os.environ.get("FIREBASE_PROJECT_ID", "").strip() or None

            app_options = {"projectId": project_id} if project_id else None
            app = firebase_admin.initialize_app(cred, app_options)
            _firebase_db = firestore.client(app)
            _firebase_ready = True
            print(
                f"[FIREBASE] Firestore persistence enabled "
                f"(collection: {_collection_name})",
                flush=True,
            )
        except Exception as exc:
            # Firebase is an optional durability layer. The bot must still
            # start when credentials are missing or temporarily unavailable.
            print(
                f"[FIREBASE] Could not initialize Firestore: {exc}. "
                "Continuing with local JSON persistence.",
                flush=True,
            )
            _firebase_db = None
        return _firebase_db


def _doc_id(path: str) -> str:
    name = Path(path).name
    if name.lower().endswith(".json"):
        name = name[:-5]
    return name.replace("/", "_").replace("\\", "_")[:1_500] or "state"


def _read_local(path: str, default: Any):
    local_path = Path(path)
    if not local_path.exists():
        return default, False
    try:
        with local_path.open("r", encoding="utf-8") as file:
            return json.load(file), True
    except Exception:
        return default, True


def _firestore_document(path: str):
    db = _init_firebase()
    if db is None:
        return None
    try:
        snapshot = db.collection(_collection_name).document(_doc_id(path)).get()
        if snapshot.exists:
            payload = snapshot.to_dict() or {}
            return payload.get("data")
    except Exception as exc:
        print(f"[FIREBASE] Read failed for {_doc_id(path)}: {exc}", flush=True)
    return None


def _write_firestore(path: str, data: Any):
    db = _init_firebase()
    if db is None:
        return
    try:
        from firebase_admin import firestore

        db.collection(_collection_name).document(_doc_id(path)).set(
            {
                "data": data,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "source_file": Path(path).name,
            }
        )
    except Exception as exc:
        print(f"[FIREBASE] Write failed for {_doc_id(path)}: {exc}", flush=True)


def load_json(path: str, default: Any):
    """Load Firestore state first, migrating an existing local file on first run."""
    local_data, local_exists = _read_local(path, default)
    remote_data = _firestore_document(path)
    if remote_data is not None:
        # Keep a cache so the bot can still boot during a later Firebase outage.
        try:
            local_path = Path(path)
            with local_path.open("w", encoding="utf-8") as file:
                json.dump(remote_data, file, indent=2, ensure_ascii=False)
        except Exception:
            pass
        return remote_data
    if _firebase_ready and local_exists:
        # Existing JSON files are imported into Firestore once, without
        # replacing a document that already contains user data.
        _write_firestore(path, local_data)
    return local_data


def save_json(path: str, data: Any):
    """Write local cache and Firestore, preserving the old JSON API."""
    local_path = Path(path)
    with _firebase_lock:
        with local_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        _write_firestore(path, data)
