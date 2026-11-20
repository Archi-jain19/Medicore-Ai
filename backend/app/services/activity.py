from sqlalchemy.orm import Session

from app.models import ActivityLog


def log_activity(
    db: Session, user_id: int, action: str, entity_type: str | None = None, entity_id: int | None = None, meta=None
) -> None:
    """Adds an activity row to the current transaction (caller commits)."""
    db.add(ActivityLog(user_id=user_id, action=action, entity_type=entity_type, entity_id=entity_id, meta=meta))
