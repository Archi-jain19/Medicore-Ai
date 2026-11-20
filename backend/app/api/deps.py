from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.security import access_token_current, decode_access_token
from app.database.session import get_db
from app.models import User

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise AuthError("Please sign in to continue.")
    try:
        payload = decode_access_token(creds.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise AuthError("Your session has ended. Please sign in again.") from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthError("We could not find your account. Please sign in again.")
    if not access_token_current(payload, user.hashed_password):
        raise AuthError("Your session has ended because your password changed. Please sign in again.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
