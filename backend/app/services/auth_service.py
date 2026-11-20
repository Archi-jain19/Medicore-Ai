from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AuthError, ConflictError
from app.core.security import hash_password, verify_password
from app.models import User, UserProfile
from app.models.entities import utcnow
from app.services.activity import log_activity

# Pre-computed hash used to equalize timing when the email does not exist
_DUMMY_HASH = hash_password("timing-equalizer-0")


def register_user(db: Session, email: str, password: str, full_name: str | None) -> User:
    email = email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise ConflictError("There is already an account with this email. Try signing in instead.")
    user = User(email=email, hashed_password=hash_password(password))
    user.profile = UserProfile(full_name=full_name)
    db.add(user)
    db.flush()
    log_activity(db, user.id, "auth.register")
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise AuthError("Incorrect email or password")
    if not verify_password(password, user.hashed_password):
        raise AuthError("Incorrect email or password")
    if not user.is_active:
        raise AuthError("This account has been turned off. Please contact support.")
    user.last_login_at = utcnow()
    from app.services.privacy_service import apply_retention

    apply_retention(db, user)
    log_activity(db, user.id, "auth.login")
    db.commit()
    return user


def request_password_reset(db: Session, email: str) -> None:
    """Always succeeds from the caller's perspective (no account enumeration)."""
    from app.core.config import get_settings
    from app.core.security import create_reset_token
    from app.services.email_service import send_password_reset

    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if user is None or not user.is_active:
        return
    token = create_reset_token(user.id, user.hashed_password)
    send_password_reset(user.email, f"{get_settings().frontend_url}/reset-password?token={token}")
    log_activity(db, user.id, "auth.password_reset_requested")
    db.commit()


def reset_password(db: Session, token: str, new_password: str) -> None:
    import jwt

    from app.core.security import decode_reset_token, reset_token_matches

    try:
        payload = decode_reset_token(token)
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise AuthError("This reset link has expired. Please ask for a new one.") from None
    if user is None or not reset_token_matches(payload, user.hashed_password):
        raise AuthError("This reset link has already been used or has expired. Please ask for a new one.")
    user.hashed_password = hash_password(new_password)
    log_activity(db, user.id, "auth.password_reset")
    db.commit()


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.hashed_password):
        raise AuthError("Your current password is not correct", code="invalid_password", status_code=400)
    user.hashed_password = hash_password(new)
    log_activity(db, user.id, "auth.password_changed")
    db.commit()
