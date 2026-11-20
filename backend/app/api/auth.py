from fastapi import APIRouter, Request, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.profile.full_name if user.profile else None,
        created_at=user.created_at,
    )


def _token(user) -> TokenResponse:
    s = get_settings()
    return TokenResponse(access_token=create_access_token(user.id, user.hashed_password),
                         expires_in=s.jwt_access_token_expire_minutes * 60)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def register(request: Request, body: RegisterRequest, db: DbSession):
    user = auth_service.register_user(db, body.email, body.password, body.full_name)
    return _token(user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("20/minute")
def login(request: Request, body: LoginRequest, db: DbSession):
    user = auth_service.authenticate(db, body.email, body.password)
    return _token(user)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return _user_out(user)


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("5/minute")
def forgot_password(request: Request, body: ForgotPasswordRequest, db: DbSession):
    auth_service.request_password_reset(db, body.email)
    return MessageResponse(message="If an account exists for that email, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("10/minute")
def reset_password(request: Request, body: ResetPasswordRequest, db: DbSession):
    auth_service.reset_password(db, body.token, body.new_password)
    return MessageResponse(message="Password updated. You can now sign in.")


@router.post("/change-password", response_model=TokenResponse)
@limiter.limit("10/minute")
def change_password(request: Request, body: ChangePasswordRequest, db: DbSession, user: CurrentUser):
    """Changes the password, signs out every other session and returns a fresh token for this one."""
    auth_service.change_password(db, user, body.current_password, body.new_password)
    return _token(user)
