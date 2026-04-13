"""Time-limited password reset tokens (hashed at rest)."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from auth.config import AUTH_DB_PATH
from auth.users import get_user_by_id, set_password_by_user_id


def _conn():
    import os

    os.makedirs(os.path.dirname(AUTH_DB_PATH), exist_ok=True)
    c = sqlite3.connect(AUTH_DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS password_resets (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used_at TEXT
        )
        """
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id)"
    )
    c.commit()
    return c


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _expire_minutes() -> int:
    import os

    raw = (os.getenv("PASSWORD_RESET_EXPIRE_MINUTES") or "").strip()
    if raw:
        try:
            return max(5, min(int(raw), 7 * 24 * 60))
        except ValueError:
            pass
    return 60


def issue_reset_token(user_id: str) -> str:
    """Create a reset token; returns the raw secret (show once in email)."""
    raw = secrets.token_urlsafe(32)
    th = _hash_token(raw)
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=_expire_minutes())
    rid = str(uuid.uuid4())
    conn = _conn()
    try:
        conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))
        conn.execute(
            """
            INSERT INTO password_resets (id, user_id, token_hash, expires_at, used_at)
            VALUES (?, ?, ?, ?, NULL)
            """,
            (rid, user_id, th, exp.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return raw


def consume_reset_token(raw_token: str, new_password: str) -> dict:
    """Set new password if token is valid. Returns user dict. Raises ValueError on failure."""
    raw_token = (raw_token or "").strip()
    if not raw_token:
        raise ValueError("Invalid or expired reset link.")
    th = _hash_token(raw_token)
    conn = _conn()
    try:
        cur = conn.execute(
            """
            SELECT id, user_id, expires_at, used_at FROM password_resets
            WHERE token_hash = ?
            """,
            (th,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Invalid or expired reset link.")
        if row["used_at"]:
            raise ValueError("This reset link was already used.")
        exp = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > exp:
            raise ValueError("This reset link has expired. Request a new one.")

        uid = row["user_id"]
        reset_id = row["id"]
        try:
            set_password_by_user_id(uid, new_password)
        except ValueError:
            raise
        conn.execute(
            "UPDATE password_resets SET used_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), reset_id),
        )
        conn.commit()
    finally:
        conn.close()
    u = get_user_by_id(uid)
    if not u:
        raise ValueError("Invalid or expired reset link.")
    return u
