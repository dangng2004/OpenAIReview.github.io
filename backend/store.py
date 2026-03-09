"""Firestore-backed persistence for review results."""

from datetime import datetime, timezone

import os

import firebase_admin
from firebase_admin import firestore

if not firebase_admin._apps:
    firebase_admin.initialize_app()

_db = firestore.client(database_id=os.environ.get("FIRESTORE_DB", "openaireview-db"))
_COL = "reviews"


def insert_pending(token: str, email: str) -> None:
    _db.collection(_COL).document(token).set({
        "status": "pending",
        "email": email,
        "data": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def set_done(token: str, data: dict) -> None:
    _db.collection(_COL).document(token).update({
        "status": "done",
        "data": data,
    })


def set_error(token: str, error: str) -> None:
    _db.collection(_COL).document(token).update({
        "status": "error",
        "error": error,
    })


def get_review(token: str) -> dict | None:
    """Return {status, data, error, email} or None if not found."""
    doc = _db.collection(_COL).document(token).get()
    if not doc.exists:
        return None
    d = doc.to_dict()
    return {
        "status": d.get("status"),
        "data": d.get("data"),
        "error": d.get("error"),
        "email": d.get("email"),
    }
