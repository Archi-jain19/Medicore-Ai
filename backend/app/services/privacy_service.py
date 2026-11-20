"""Data-retention, export and deletion controls for a user's own records."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import ActivityLog, Conversation, MedicalReport, Prediction, Reminder, ReminderEvent, User
from app.models.entities import utcnow

PURGE_SCOPES = {
    "conversations": Conversation,
    "reports": MedicalReport,
    "predictions": Prediction,
    "reminders": Reminder,
    "activity": ActivityLog,
}
RETENTION_SCOPES = ("conversations", "reports", "predictions", "activity")


def purge(db: Session, user: User, scope: str) -> int:
    """Delete all of the user's records in one scope. Uses ORM deletes so cascades (messages, lab values,
    dose events) are applied in every database backend."""
    model = PURGE_SCOPES[scope]
    rows = db.scalars(select(model).where(model.user_id == user.id)).all()
    for r in rows:
        db.delete(r)
    db.flush()
    return len(rows)


def apply_retention(db: Session, user: User) -> dict:
    """Delete history older than the user's retention setting (no-op when unset). Reminders are kept because
    they are ongoing schedules, not history."""
    days = user.profile.data_retention_days if user.profile else None
    if not days:
        return {}
    cutoff = utcnow() - timedelta(days=days)
    removed = {}
    for scope in RETENTION_SCOPES:
        model = PURGE_SCOPES[scope]
        col = model.updated_at if hasattr(model, "updated_at") else model.created_at
        rows = db.scalars(select(model).where(model.user_id == user.id, col < cutoff)).all()
        for r in rows:
            db.delete(r)
        removed[scope] = len(rows)
    old_events = db.scalars(select(ReminderEvent).join(Reminder).where(
        Reminder.user_id == user.id, ReminderEvent.logged_at < cutoff)).all()
    for e in old_events:
        db.delete(e)
    removed["reminder_events"] = len(old_events)
    db.flush()
    return removed


def export(db: Session, user: User) -> dict:
    def iso(d):
        return d.isoformat() if d else None

    convs = db.scalars(select(Conversation).where(Conversation.user_id == user.id)).all()
    reports = db.scalars(select(MedicalReport).where(MedicalReport.user_id == user.id)).all()
    preds = db.scalars(select(Prediction).where(Prediction.user_id == user.id)).all()
    rems = db.scalars(select(Reminder).where(Reminder.user_id == user.id)).all()
    acts = db.scalars(select(ActivityLog).where(ActivityLog.user_id == user.id)).all()
    p = user.profile
    return {
        "exported_at": iso(utcnow()),
        "note": "All personal data MediCore AI holds for this account. Uploaded files are never stored.",
        "account": {"email": user.email, "created_at": iso(user.created_at), "last_login_at": iso(user.last_login_at),
                    "full_name": p.full_name if p else None, "notify_reminders": p.notify_reminders if p else None,
                    "data_retention_days": p.data_retention_days if p else None},
        "conversations": [{"id": c.id, "title": c.title, "created_at": iso(c.created_at), "messages": [
            {"role": m.role, "content": m.content, "created_at": iso(m.created_at),
             "sources": [{"title": s.get("title"), "url": s.get("url")} for s in (m.sources or [])]}
            for m in c.messages]} for c in convs],
        "medical_reports": [{"id": r.id, "file": r.original_filename, "created_at": iso(r.created_at),
                             "summary": r.summary, "results": [
            {"parameter": x.parameter, "value": x.value_text, "unit": x.unit, "reference_range": x.ref_text,
             "flag": x.flag} for x in r.lab_results]} for r in reports],
        "predictions": [{"id": x.id, "created_at": iso(x.created_at), "inputs": x.inputs,
                         "probability": x.probability, "risk_band": x.risk_band} for x in preds],
        "reminders": [{"id": r.id, "medication_name": r.medication_name, "dosage_note": r.dosage_note,
                       "frequency": r.frequency, "times": r.times, "days_of_week": r.days_of_week,
                       "start_date": iso(r.start_date), "end_date": iso(r.end_date), "is_active": r.is_active,
                       "events": [{"date": iso(e.scheduled_date), "time": e.scheduled_time, "status": e.status}
                                  for e in r.events]} for r in rems],
        "activity": [{"action": a.action, "created_at": iso(a.created_at)} for a in acts],
    }


def delete_account(db: Session, user: User) -> None:
    db.execute(delete(ActivityLog).where(ActivityLog.user_id == user.id))
    db.delete(user)          # ORM cascades + DB ON DELETE CASCADE remove everything else
    db.flush()
