"""Dashboard aggregates. User-scoped numbers come from the user's own rows; population analytics
come from the EDA report of the public training dataset and are labelled as such."""
import json
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.ml.registry import get_registry
from app.models import ActivityLog, Conversation, MedicalReport, Prediction, Reminder, User

ACTION_LABELS = {
    "auth.register": "Created account",
    "auth.login": "Signed in",
    "auth.password_changed": "Changed password",
    "auth.password_reset": "Reset password",
    "auth.password_reset_requested": "Requested password reset",
    "ml.predict": "Ran a risk estimate",
    "chat.message": "Asked the AI assistant",
    "chat.delete": "Deleted a conversation",
    "report.upload": "Analysed a medical report",
    "report.delete": "Deleted a medical report",
    "reminder.create": "Added a medication reminder",
    "reminder.update": "Updated a reminder",
    "reminder.delete": "Deleted a reminder",
    "reminder.taken": "Logged a dose as taken",
    "reminder.skipped": "Logged a dose as skipped",
    "settings.update": "Updated settings",
    "settings.purge": "Deleted stored data",
}


def _count(db: Session, model, user_id: int) -> int:
    return db.scalar(select(func.count()).select_from(model).where(model.user_id == user_id)) or 0


def summary(db: Session, user: User) -> dict:
    preds = list(db.scalars(
        select(Prediction).where(Prediction.user_id == user.id).order_by(Prediction.created_at.asc())
    ))
    bands = Counter(p.risk_band for p in preds)
    activity = db.scalars(
        select(ActivityLog).where(ActivityLog.user_id == user.id).order_by(ActivityLog.id.desc()).limit(10)
    )
    return {
        "user": {"email": user.email, "full_name": user.profile.full_name if user.profile else None},
        "counts": {
            "reports": _count(db, MedicalReport, user.id),
            "conversations": _count(db, Conversation, user.id),
            "predictions": len(preds),
            "active_reminders": db.scalar(select(func.count()).select_from(Reminder).where(
                Reminder.user_id == user.id, Reminder.is_active.is_(True))) or 0,
        },
        "my_risk_distribution": [{"band": b, "count": bands.get(b, 0)} for b in ("lower", "elevated", "high")],
        "my_prediction_trend": [
            {"id": p.id, "created_at": p.created_at.isoformat(), "probability": round(p.probability, 4),
             "risk_band": p.risk_band}
            for p in preds[-30:]
        ],
        "recent_activity": [
            {"id": a.id, "action": a.action, "label": ACTION_LABELS.get(a.action, a.action),
             "created_at": a.created_at.isoformat()}
            for a in activity
        ],
    }


def population_analytics() -> dict:
    """Descriptive statistics of the public CDC BRFSS 2015-derived training split (not user data)."""
    path = get_settings().data_dir / "processed" / "eda_report.json"
    if not path.exists():
        raise AppError("This information is not available right now. Please try again later.", code="analytics_unavailable",
                       status_code=503)
    eda = json.loads(path.read_text())
    assoc = eda["association_with_target"]
    reg = get_registry()
    model = reg.risk_model()
    sel = model.metrics["models"][model.algorithm]["test"]
    try:
        clusters = reg.clusters()
        segments = [{"name": s["name"], "share": s["share"], "observed_diabetes_rate": s["observed_diabetes_rate"]}
                    for s in clusters["segments"]]
    except AppError:
        segments = []
    return {
        "source": "Training split of the UCI CDC Diabetes Health Indicators dataset (BRFSS 2015). "
                  "Population-level, de-identified survey data — not your personal data.",
        "n_respondents": eda["shape"][0],
        "prevalence": eda["class_distribution"].get("1"),
        "prevalence_by_age": [{"level": int(k), "rate": v} for k, v in assoc["Age"]["prevalence_by_level"].items()],
        "prevalence_by_genhlth": [{"level": int(k), "rate": v}
                                  for k, v in assoc["GenHlth"]["prevalence_by_level"].items()],
        "prevalence_by_bmi_category": [{"category": k, "rate": v}
                                       for k, v in eda["prevalence_by_bmi_category"].items()],
        "top_associations": sorted(
            [{"feature": k, "spearman": v} for k, v in eda["spearman_with_target"].items()],
            key=lambda d: -abs(d["spearman"]))[:8],
        "segments": segments,
        "model": {
            "algorithm": model.algorithm_display, "version": model.version,
            "test_roc_auc": sel["roc_auc"], "test_pr_auc": sel["pr_auc"],
            "test_recall": sel["at_threshold"]["recall"], "test_precision": sel["at_threshold"]["precision"],
            "threshold": sel["at_threshold"]["threshold"],
        },
    }
