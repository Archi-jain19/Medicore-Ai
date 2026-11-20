import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Frequency = Literal["daily", "every_other_day", "weekly", "as_needed"]
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ReminderBase(BaseModel):
    medication_name: str = Field(min_length=1, max_length=120)
    dosage_note: str | None = Field(default=None, max_length=200,
                                    description="Free text copied from the user's prescription; never generated")
    frequency: Frequency
    times: list[str] = Field(default_factory=list, max_length=8, description="Local wall-clock times, HH:MM")
    days_of_week: list[int] | None = Field(default=None, description="0=Mon … 6=Sun (weekly only)")
    start_date: date
    end_date: date | None = None
    is_active: bool = True

    @field_validator("medication_name", "dosage_note")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("times")
    @classmethod
    def _times(cls, v: list[str]) -> list[str]:
        for t in v:
            if not _TIME.match(t):
                raise ValueError(f"'{t}' is not a valid HH:MM time")
        if len(set(v)) != len(v):
            raise ValueError("Times must be unique")
        return sorted(v)

    @field_validator("days_of_week")
    @classmethod
    def _days(cls, v):
        if v is None:
            return v
        if not v or any(d < 0 or d > 6 for d in v) or len(set(v)) != len(v):
            raise ValueError("days_of_week must be unique values from 0 (Mon) to 6 (Sun)")
        return sorted(v)

    @model_validator(mode="after")
    def _consistency(self):
        if not self.medication_name:
            raise ValueError("Medication name is required")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must be on or after the start date")
        if self.frequency != "as_needed" and not self.times:
            raise ValueError("Add at least one time for scheduled reminders")
        if self.frequency == "weekly" and not self.days_of_week:
            raise ValueError("Choose at least one day for weekly reminders")
        if self.frequency != "weekly":
            self.days_of_week = None
        return self


class ReminderCreate(ReminderBase):
    pass


class ReminderUpdate(ReminderBase):
    pass


class ReminderOut(ReminderBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
    status: Literal["active", "paused", "ended", "scheduled"]


class DoseLog(BaseModel):
    scheduled_date: date
    scheduled_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    status: Literal["taken", "skipped"]


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reminder_id: int
    medication_name: str
    scheduled_date: date
    scheduled_time: str
    status: str
    logged_at: datetime


class DoseOut(BaseModel):
    reminder_id: int
    medication_name: str
    dosage_note: str | None
    scheduled_date: date
    scheduled_time: str
    status: Literal["taken", "skipped", "pending"]
    event_id: int | None
