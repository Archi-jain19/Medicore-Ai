from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: DbSession, user: CurrentUser):
    """User-scoped counts, own prediction history and recent activity."""
    return dashboard_service.summary(db, user)


@router.get("/analytics")
def analytics(user: CurrentUser):
    """Population-level analytics from the public training dataset (clearly labelled as such)."""
    return dashboard_service.population_analytics()
