from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from auth.jwt_tokens import decode_token
from auth.users import get_user_by_id

security = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    id: str
    email: str


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> CurrentUser:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    uid = payload.get("sub")
    if not uid or not isinstance(uid, str):
        raise HTTPException(status_code=401, detail="Invalid token payload")
    row = get_user_by_id(uid)
    if not row:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return CurrentUser(id=row["id"], email=row["email"])
