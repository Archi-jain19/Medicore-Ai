"""Password hashing (bcrypt) and JWT helpers."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

_BCRYPT_ROUNDS = 12
_MAX_BCRYPT_BYTES = 72  # bcrypt ignores input beyond 72 bytes; we reject longer passwords upstream


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")
    if len(pw) > _MAX_BCRYPT_BYTES:
        raise ValueError("Password too long")
    return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str | int, hashed_password: str | None = None,
                        expires_minutes: int | None = None) -> str:
    """`pwv` binds the session to the current password: changing/resetting it revokes all older tokens."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expires_minutes or s.jwt_access_token_expire_minutes)
    payload = {"sub": str(subject), "iat": now, "exp": exp, "type": "access"}
    if hashed_password:
        payload["pwv"] = _pw_fingerprint(hashed_password)
    return jwt.encode(payload, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def access_token_current(payload: dict, hashed_password: str) -> bool:
    return payload.get("pwv") == _pw_fingerprint(hashed_password)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError on invalid/expired tokens."""
    s = get_settings()
    payload = jwt.decode(token, s.jwt_secret_key, algorithms=[s.jwt_algorithm])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Wrong token type")
    return payload


def _pw_fingerprint(hashed_password: str) -> str:
    """Binds a reset token to the current password hash so it becomes invalid once used."""
    import hashlib

    return hashlib.sha256(hashed_password.encode()).hexdigest()[:16]


def create_reset_token(user_id: int, hashed_password: str, minutes: int = 15) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=minutes), "type": "reset",
               "pwf": _pw_fingerprint(hashed_password)}
    return jwt.encode(payload, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def decode_reset_token(token: str) -> dict:
    s = get_settings()
    payload = jwt.decode(token, s.jwt_secret_key, algorithms=[s.jwt_algorithm])
    if payload.get("type") != "reset":
        raise jwt.InvalidTokenError("Wrong token type")
    return payload


def reset_token_matches(payload: dict, hashed_password: str) -> bool:
    return payload.get("pwf") == _pw_fingerprint(hashed_password)
