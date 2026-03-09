"""Per-email daily rate limiting using Firestore transactions."""

import os
from datetime import date

import firebase_admin
from firebase_admin import firestore

if not firebase_admin._apps:
    firebase_admin.initialize_app()

_db = firestore.client(database_id=os.environ.get("FIRESTORE_DB", "openaireview-db"))
_COL = "rate_limit"
MAX_REVIEWS_PER_DAY = 3


@firestore.transactional
def _check_and_increment_txn(transaction, ref):
    snapshot = ref.get(transaction=transaction)
    current = snapshot.get("count") if snapshot.exists else 0
    if current >= MAX_REVIEWS_PER_DAY:
        return False
    transaction.set(ref, {"count": current + 1}, merge=True)
    return True


def check_and_increment(email: str) -> bool:
    """Return True if request is allowed (under limit), False if blocked."""
    today = date.today().isoformat()
    doc_id = f"{email}_{today}"
    ref = _db.collection(_COL).document(doc_id)
    transaction = _db.transaction()
    return _check_and_increment_txn(transaction, ref)
