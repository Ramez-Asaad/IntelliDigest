"""SQLite user store (email + password hash; optional Google link)."""

import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone

from auth.config import AUTH_DB_PATH
from auth.passwords import hash_password, verify_password


def _migrate_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in cur.fetchall()]
    if "google_sub" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN google_sub TEXT")
        conn.commit()
    if "password_login_allowed" not in cols:
        conn.execute(
            "ALTER TABLE users ADD COLUMN password_login_allowed INTEGER NOT NULL DEFAULT 1"
        )
        conn.commit()
    if "phone_e164" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN phone_e164 TEXT")
        conn.commit()
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub
        ON users(google_sub) WHERE google_sub IS NOT NULL AND google_sub != ''
        """
    )
    conn.commit()


def _conn():
    os.makedirs(os.path.dirname(AUTH_DB_PATH), exist_ok=True)
    c = sqlite3.connect(AUTH_DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    c.commit()
    _migrate_schema(c)
    return c


def get_user_for_password_reset(email: str) -> dict | None:
    """Lookup for forgot-password email flow."""
    email = email.strip().lower()
    conn = _conn()
    try:
        cur = conn.execute(
            """
            SELECT id, email, password_login_allowed, google_sub
            FROM users WHERE email = ?
            """,
            (email,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def validate_password_for_registration(email: str, password: str) -> None:
    """
    Raises ValueError if password is too weak for a new account.
    Call after normalizing email to lowercase.
    """
    email = email.strip().lower()
    if not password.strip():
        raise ValueError("Password cannot be only spaces.")
    pl = password.lower()
    if pl == email:
        raise ValueError("Password must not be the same as your email.")
    local = email.split("@", 1)[0]
    if pl == local:
        raise ValueError(
            "Password must not match the part of your email before the @ symbol."
        )
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")


def set_password_by_user_id(user_id: str, new_password: str) -> None:
    """
    Set password and allow email login (e.g. after reset). Google-only accounts become
    able to use email/password as well.
    """
    conn = _conn()
    try:
        cur = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("User not found.")
        email = (row["email"] or "").strip().lower()
        validate_password_for_registration(email, new_password)
        ph = hash_password(new_password)
        conn.execute(
            """
            UPDATE users SET password_hash = ?, password_login_allowed = 1 WHERE id = ?
            """,
            (ph, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def register_user(email: str, password: str) -> dict:
    """Create user; raises ValueError if email exists or password too short."""
    email = email.strip().lower()
    if len(email) < 3 or "@" not in email:
        raise ValueError("Invalid email.")
    validate_password_for_registration(email, password)
    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT google_sub FROM users WHERE email = ?", (email,)
        )
        row = cur.fetchone()
        if row and row[0]:
            raise ValueError(
                "This email is linked to Google. Use Continue with Google to sign in."
            )
    finally:
        conn.close()

    uid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    ph = hash_password(password)
    conn = _conn()
    try:
        conn.execute(
            """
            INSERT INTO users (id, email, password_hash, created_at, password_login_allowed)
            VALUES (?, ?, ?, ?, 1)
            """,
            (uid, email, ph, now),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        if "email" in str(e).lower() or "unique" in str(e).lower():
            raise ValueError("Email already registered.") from e
        raise
    finally:
        conn.close()
    return {"id": uid, "email": email, "created_at": now}


def authenticate_email_password(email: str, password: str) -> dict:
    """
    Email/password login. Returns user dict on success.
    Raises ValueError with a message suitable for HTTP detail on failure.
    """
    email = email.strip().lower()
    conn = _conn()
    try:
        cur = conn.execute(
            """
            SELECT id, email, created_at, password_hash, password_login_allowed
            FROM users WHERE email = ?
            """,
            (email,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Invalid email or password.")
        d = dict(row)
        pla = d.get("password_login_allowed")
        if pla is None:
            pla = 1
        if int(pla) == 0:
            raise ValueError(
                "This account uses Google sign-in. Use Continue with Google."
            )
        if not verify_password(password, d["password_hash"]):
            raise ValueError("Invalid email or password.")
        return {"id": d["id"], "email": d["email"], "created_at": d["created_at"]}
    finally:
        conn.close()


def get_user_by_id(user_id: str) -> dict | None:
    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT id, email, created_at FROM users WHERE id = ?", (user_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_or_create_google_user(email: str, google_sub: str) -> dict:
    """
    Find or create a user from Google profile. Links google_sub to an existing
    email row when the email already exists (password account).
    """
    email = email.strip().lower()
    if len(email) < 3 or "@" not in email:
        raise ValueError("Invalid email from Google.")
    if not google_sub or not str(google_sub).strip():
        raise ValueError("Missing Google account id.")

    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT id, email, created_at, google_sub FROM users WHERE google_sub = ?",
            (google_sub,),
        )
        row = cur.fetchone()
        if row:
            return {"id": row["id"], "email": row["email"], "created_at": row["created_at"]}

        cur = conn.execute("SELECT id, email, created_at FROM users WHERE email = ?", (email,))
        row = cur.fetchone()
        if row:
            conn.execute(
                "UPDATE users SET google_sub = ? WHERE id = ?",
                (google_sub, row["id"]),
            )
            conn.commit()
            return {"id": row["id"], "email": row["email"], "created_at": row["created_at"]}

        uid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        ph = hash_password(secrets.token_urlsafe(48))
        conn.execute(
            """
            INSERT INTO users (id, email, password_hash, created_at, google_sub, password_login_allowed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (uid, email, ph, now, google_sub),
        )
        conn.commit()
        return {"id": uid, "email": email, "created_at": now}
    finally:
        conn.close()
