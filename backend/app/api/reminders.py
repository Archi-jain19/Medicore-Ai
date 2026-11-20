"""Medication reminders. MediCore only reminds. It never suggests, checks or changes medicines or doses.

Times are local wall-clock times entered by the user; the client supplies its local date when asking
for a day's schedule, so no server time-zone assumptions are made.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.errors import AppError, NotFoundError
from app.models import Reminder, ReminderEvent
from app.models.entities import utcnow
from app.schemas.reminders import DoseLog, DoseOut, EventOut, ReminderCreate, ReminderOut, ReminderUpdate
from app.services.activity import log_activity

router = APIRouter(prefix="/reminders", tags=["reminders"])
MAX_REMINDERS = 50


def _owned(db, user, rid: int) -> Reminder:
    r = db.scalar(select(Reminder).where(Reminder.id == rid, Reminder.user_id == user.id))
    if r is None:
        raise NotFoundError("We could not find that reminder.")
    return r


def occurs_on(r: Reminder, day: date) -> bool:
    if not r.is_active or day < r.start_date or (r.end_date and day > r.end_date):
        return False
    if r.frequency == "daily":
        return True
    if r.frequency == "every_other_day":
        return (day - r.start_date).days % 2 == 0
    if r.frequency == "weekly":
        return day.weekday() in (r.days_of_week or [])
    return False  # as_needed: no scheduled doses


def _status(r: Reminder, today: date) -> str:
    if not r.is_active:
        return "paused"
    if r.end_date and r.end_date < today:
        return "ended"
    if r.start_date > today:
        return "scheduled"
    return "active"


def _out(r: Reminder, today: date | None = None) -> ReminderOut:
    return ReminderOut(
        id=r.id, medication_name=r.medication_name, dosage_note=r.dosage_note, frequency=r.frequency,
        times=r.times or [], days_of_week=r.days_of_week, start_date=r.start_date, end_date=r.end_date,
        is_active=r.is_active, created_at=r.created_at, updated_at=r.updated_at,
        status=_status(r, today or date.today()),
    )


def _apply(r: Reminder, body: ReminderCreate):
    r.medication_name, r.dosage_note, r.frequency = body.medication_name, body.dosage_note, body.frequency
    r.times, r.days_of_week = body.times, body.days_of_week
    r.start_date, r.end_date, r.is_active = body.start_date, body.end_date, body.is_active


@router.get("", response_model=list[ReminderOut])
def list_reminders(db: DbSession, user: CurrentUser, today: date | None = None):
    rows = db.scalars(select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.medication_name))
    return [_out(r, today) for r in rows]


@router.post("", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
def create_reminder(body: ReminderCreate, db: DbSession, user: CurrentUser):
    count = len(db.scalars(select(Reminder.id).where(Reminder.user_id == user.id)).all())
    if count >= MAX_REMINDERS:
        raise AppError(f"You can keep up to {MAX_REMINDERS} reminders.", code="too_many_reminders")
    r = Reminder(user_id=user.id)
    _apply(r, body)
    db.add(r)
    db.flush()
    log_activity(db, user.id, "reminder.create", "reminder", r.id)
    db.commit()
    db.refresh(r)
    return _out(r)


@router.put("/{reminder_id}", response_model=ReminderOut)
def update_reminder(reminder_id: int, body: ReminderUpdate, db: DbSession, user: CurrentUser):
    r = _owned(db, user, reminder_id)
    _apply(r, body)
    log_activity(db, user.id, "reminder.update", "reminder", r.id)
    db.commit()
    db.refresh(r)
    return _out(r)


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reminder(reminder_id: int, db: DbSession, user: CurrentUser):
    r = _owned(db, user, reminder_id)
    db.delete(r)
    log_activity(db, user.id, "reminder.delete", "reminder", reminder_id)
    db.commit()


@router.get("/schedule", response_model=list[DoseOut])
def schedule(db: DbSession, user: CurrentUser, day: date = Query(..., description="The user's local date")):
    """Doses due on `day`, with any logged status. Past 'pending' doses are shown as missed by the client."""
    reminders = db.scalars(select(Reminder).where(Reminder.user_id == user.id)).all()
    due = [r for r in reminders if occurs_on(r, day)]
    events = {}
    if due:
        rows = db.scalars(select(ReminderEvent).where(ReminderEvent.reminder_id.in_([r.id for r in due]),
                                                      ReminderEvent.scheduled_date == day))
        events = {(e.reminder_id, e.scheduled_time): e for e in rows}
    doses = []
    for r in due:
        for t in r.times or []:
            e = events.get((r.id, t))
            doses.append(DoseOut(reminder_id=r.id, medication_name=r.medication_name, dosage_note=r.dosage_note,
                                 scheduled_date=day, scheduled_time=t, status=e.status if e else "pending",
                                 event_id=e.id if e else None))
    return sorted(doses, key=lambda d: (d.scheduled_time, d.medication_name))


@router.post("/{reminder_id}/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def log_dose(reminder_id: int, body: DoseLog, db: DbSession, user: CurrentUser):
    """Record a dose as taken or skipped. Re-logging the same dose updates it.
    Scheduled reminders: the date/time must be one of the reminder's doses.
    As-needed reminders: the time is when the dose was taken (local wall-clock)."""
    r = _owned(db, user, reminder_id)
    d, t = body.scheduled_date, body.scheduled_time
    if r.frequency == "as_needed":
        if d < r.start_date or (r.end_date and d > r.end_date):
            raise AppError("That date is outside this reminder's start and end dates.", code="not_scheduled")
    elif not occurs_on(r, d) or t not in (r.times or []):
        raise AppError("That dose is not part of this reminder's schedule.", code="not_scheduled")
    if d > date.today() + timedelta(days=1):  # +1 day tolerance for time zones ahead of the server
        raise AppError("You cannot mark a dose as taken in the future.", code="future_dose")
    e = db.scalar(select(ReminderEvent).where(ReminderEvent.reminder_id == r.id, ReminderEvent.scheduled_date == d,
                                              ReminderEvent.scheduled_time == t))
    if e is None:
        e = ReminderEvent(reminder_id=r.id, scheduled_date=d, scheduled_time=t, status=body.status)
        db.add(e)
    else:
        e.status, e.logged_at = body.status, utcnow()
    log_activity(db, user.id, f"reminder.{body.status}", "reminder", r.id)
    db.commit()
    db.refresh(e)
    return EventOut(id=e.id, reminder_id=r.id, medication_name=r.medication_name, scheduled_date=e.scheduled_date,
                    scheduled_time=e.scheduled_time, status=e.status, logged_at=e.logged_at)


@router.get("/history", response_model=list[EventOut])
def history(db: DbSession, user: CurrentUser, days: int = Query(30, ge=1, le=365)):
    since = date.today() - timedelta(days=days)
    rows = db.execute(
        select(ReminderEvent, Reminder.medication_name)
        .join(Reminder, Reminder.id == ReminderEvent.reminder_id)
        .where(Reminder.user_id == user.id, ReminderEvent.scheduled_date >= since)
        .order_by(ReminderEvent.scheduled_date.desc(), ReminderEvent.scheduled_time.desc())
    ).all()
    return [EventOut(id=e.id, reminder_id=e.reminder_id, medication_name=name, scheduled_date=e.scheduled_date,
                     scheduled_time=e.scheduled_time, status=e.status, logged_at=e.logged_at) for e, name in rows]
