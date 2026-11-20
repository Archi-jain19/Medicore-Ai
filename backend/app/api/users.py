import json
from typing import Literal

from fastapi import APIRouter, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from app.api.deps import CurrentUser, DbSession
from app.core.errors import AuthError
from app.core.rate_limit import limiter
from app.core.security import verify_password
from app.models import UserProfile
from app.services import privacy_service
from app.services.activity import log_activity

router = APIRouter(prefix="/users/me", tags=["settings"])
RETENTION_CHOICES = (None, 30, 90, 180, 365)


class ProfileOut(BaseModel):
    email: str
    full_name: str | None
    notify_reminders: bool
    data_retention_days: int | None
    created_at: str


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    notify_reminders: bool
    data_retention_days: int | None = None

    @field_validator("data_retention_days")
    @classmethod
    def _retention(cls, v):
        if v not in RETENTION_CHOICES:
            raise ValueError("Choose 30, 90, 180 or 365 days, or keep data until you delete it")
        return v

    @field_validator("full_name")
    @classmethod
    def _name(cls, v):
        return (v.strip() or None) if v else None


class PurgeRequest(BaseModel):
    scope: Literal["conversations", "reports", "predictions", "reminders", "activity"]


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=72)
    confirm: Literal["DELETE"]


def _profile(user) -> UserProfile:
    if user.profile is None:
        user.profile = UserProfile()
    return user.profile


def _out(user) -> ProfileOut:
    p = _profile(user)
    return ProfileOut(email=user.email, full_name=p.full_name, notify_reminders=p.notify_reminders,
                      data_retention_days=p.data_retention_days, created_at=user.created_at.isoformat())


@router.get("/profile", response_model=ProfileOut)
def get_profile(user: CurrentUser):
    return _out(user)


@router.put("/profile", response_model=ProfileOut)
def update_profile(body: ProfileUpdate, db: DbSession, user: CurrentUser):
    p = _profile(user)
    p.full_name, p.notify_reminders, p.data_retention_days = body.full_name, body.notify_reminders, body.data_retention_days
    db.flush()
    removed = privacy_service.apply_retention(db, user)
    log_activity(db, user.id, "settings.update", meta={"retention_removed": removed} if removed else None)
    db.commit()
    return _out(user)


@router.get("/export")
@limiter.limit("5/minute")
def export_data(request: Request, db: DbSession, user: CurrentUser):
    data = privacy_service.export(db, user)
    return Response(json.dumps(data, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="medicore-data-export.json"'})


@router.post("/purge")
def purge(body: PurgeRequest, db: DbSession, user: CurrentUser):
    n = privacy_service.purge(db, user, body.scope)
    if body.scope != "activity":
        log_activity(db, user.id, "settings.purge", meta={"scope": body.scope, "deleted": n})
    db.commit()
    return {"scope": body.scope, "deleted": n}


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
def delete_account(request: Request, body: DeleteAccountRequest, db: DbSession, user: CurrentUser):
    if not verify_password(body.password, user.hashed_password):
        raise AuthError("That password is not correct", code="invalid_password", status_code=400)
    privacy_service.delete_account(db, user)
    db.commit()
