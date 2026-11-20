"""SQLAlchemy ORM entities. See docs/ARCHITECTURE.md §5 for the schema rationale."""
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class UpdatedMixin(TimestampMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(UpdatedMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped["UserProfile"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserProfile(UpdatedMixin, Base):
    __tablename__ = "user_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(120))
    notify_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notify_reminders: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    data_retention_days: Mapped[int | None] = mapped_column(Integer)

    user: Mapped[User] = relationship(back_populates="profile")


class Conversation(UpdatedMixin, Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="New conversation", nullable=False)

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ChatMessage.id"
    )


class ChatMessage(TimestampMixin, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role in ('user','assistant')", name="ck_chat_role"),
        Index("ix_chat_conv_created", "conversation_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[Any | None] = mapped_column(JSONType)
    verification: Mapped[Any | None] = mapped_column(JSONType)
    retrieval_strategy: Mapped[str | None] = mapped_column(String(32))

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class MedicalReport(UpdatedMixin, Base):
    __tablename__ = "medical_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extraction_method: Mapped[str | None] = mapped_column(String(16))
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="processed", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)

    lab_results: Mapped[list["ExtractedLabResult"]] = relationship(
        back_populates="report", cascade="all, delete-orphan", order_by="ExtractedLabResult.id"
    )


class ExtractedLabResult(TimestampMixin, Base):
    __tablename__ = "extracted_lab_results"
    __table_args__ = (CheckConstraint("flag in ('low','high','normal','unknown')", name="ck_lab_flag"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("medical_reports.id", ondelete="CASCADE"), index=True, nullable=False
    )
    parameter: Mapped[str] = mapped_column(String(120), nullable=False)
    printed_name: Mapped[str | None] = mapped_column(String(160))
    value_text: Mapped[str] = mapped_column(String(64), nullable=False)
    value_numeric: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(32))
    ref_low: Mapped[float | None] = mapped_column(Float)
    ref_high: Mapped[float | None] = mapped_column(Float)
    ref_text: Mapped[str | None] = mapped_column(String(64))
    flag: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    flag_source: Mapped[str] = mapped_column(String(24), default="none", nullable=False)

    report: Mapped[MedicalReport] = relationship(back_populates="lab_results")


class ModelVersion(TimestampMixin, Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_model_name_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(512), nullable=False)
    metrics: Mapped[Any | None] = mapped_column(JSONType)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Prediction(TimestampMixin, Base):
    __tablename__ = "predictions"
    __table_args__ = (Index("ix_pred_user_created", "user_id", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"), nullable=False)
    inputs: Mapped[Any] = mapped_column(JSONType, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_class: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_band: Mapped[str] = mapped_column(String(16), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)

    model_version: Mapped[ModelVersion] = relationship()


class Reminder(UpdatedMixin, Base):
    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint("frequency in ('daily','every_other_day','weekly','as_needed')", name="ck_reminder_frequency"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    medication_name: Mapped[str] = mapped_column(String(120), nullable=False)
    dosage_note: Mapped[str | None] = mapped_column(String(200))
    frequency: Mapped[str] = mapped_column(String(32), nullable=False)
    times: Mapped[Any] = mapped_column(JSONType, nullable=False)
    days_of_week: Mapped[Any | None] = mapped_column(JSONType)  # 0=Mon … 6=Sun, for weekly
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    events: Mapped[list["ReminderEvent"]] = relationship(back_populates="reminder", cascade="all, delete-orphan")


class ReminderEvent(TimestampMixin, Base):
    __tablename__ = "reminder_events"
    __table_args__ = (
        CheckConstraint("status in ('taken','skipped','missed')", name="ck_reminder_status"),
        UniqueConstraint("reminder_id", "scheduled_date", "scheduled_time", name="uq_reminder_dose"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    reminder_id: Mapped[int] = mapped_column(ForeignKey("reminders.id", ondelete="CASCADE"), index=True, nullable=False)
    # wall-clock dose time in the user's local time zone ("08:00" on 2026-11-17)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_time: Mapped[str] = mapped_column(String(5), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    reminder: Mapped[Reminder] = relationship(back_populates="events")


class ActivityLog(TimestampMixin, Base):
    __tablename__ = "activity_logs"
    __table_args__ = (Index("ix_activity_user_created", "user_id", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[Any | None] = mapped_column("metadata", JSONType)
