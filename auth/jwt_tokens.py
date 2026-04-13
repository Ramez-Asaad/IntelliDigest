from datetime import datetime, timedelta, timezone

import jwt

from auth.config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET


def create_access_token(*, user_id: str, email: str) -> str:
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not set in the environment.")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": now,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not set in the environment.")
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
