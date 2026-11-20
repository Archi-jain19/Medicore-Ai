"""Prediction / explanation service. Every number returned comes from the trained artifact."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.registry import LoadedModel, get_registry
from app.models import ModelVersion, Prediction, User
from app.schemas.ml import PatientInput
from app.services import plain_language as plain
from app.services.activity import log_activity

LIMITATIONS = plain.LIMITATIONS


def _frame(inp: PatientInput, model: LoadedModel) -> pd.DataFrame:
    row = inp.model_dump()
    return pd.DataFrame([[row[f] for f in model.artifact["features"]]], columns=model.artifact["features"])


def risk_band(p: float, threshold: float, prevalence: float) -> str:
    """Display convention: below the model's operating threshold -> 'lower'; at/above threshold ->
    'elevated'; at/above 3x the training-population prevalence -> 'high'. Not a clinical category."""
    if p < threshold:
        return "lower"
    return "high" if p >= 3 * prevalence else "elevated"


def ensure_model_version(db: Session, model: LoadedModel) -> ModelVersion:
    mv = db.scalar(select(ModelVersion).where(ModelVersion.name == model.name, ModelVersion.version == model.version))
    if mv is None:
        sel = model.metrics["models"][model.algorithm]
        mv = ModelVersion(
            name=model.name, version=model.version, algorithm=model.algorithm,
            artifact_path=str(model.directory), is_active=True,
            metrics={"test": sel["test"], "validation": sel["validation"]},
        )
        db.add(mv)
        db.flush()
    return mv


def _score(inp: PatientInput):
    model = get_registry().risk_model()
    X = _frame(inp, model)
    p = float(model.artifact["calibrated_pipeline"].predict_proba(X)[0, 1])
    exp = model.explainer.explain_one(X)
    plain.annotate(exp["contributions"])
    return model, X, p, exp


def predict(db: Session, user: User, inp: PatientInput) -> dict:
    model, _, p, exp = _score(inp)
    thr = float(model.artifact["threshold"])
    prev = float(model.artifact["prevalence"])
    cls = int(p >= thr)
    band = risk_band(p, thr, prev)
    mv = ensure_model_version(db, model)
    rec = Prediction(user_id=user.id, model_version_id=mv.id, inputs=inp.model_dump(), probability=p,
                     predicted_class=cls, risk_band=band, threshold=thr)
    db.add(rec)
    db.flush()
    log_activity(db, user.id, "ml.predict", "prediction", rec.id, {"risk_band": band})
    db.commit()
    return {
        "id": rec.id,
        "predicted_class": cls,
        "predicted_label": "Worth a blood sugar test" if cls else "No test suggested by this check",
        "headline": plain.band_headline(band),
        "chance_text": plain.in_100(p),
        "next_step": plain.NEXT_STEP[band],
        "probability": round(p, 4),
        "threshold": round(thr, 4),
        "risk_band": band,
        "population_base_rate": round(prev, 4),
        "model_name": model.name,
        "model_version": model.version,
        "algorithm": model.algorithm_display,
        "top_contributions": exp["contributions"][:6],
        "explanation": plain.explanation_text(p, prev, exp["contributions"]),
        "limitations": LIMITATIONS,
        "created_at": rec.created_at,
    }


def explain(inp: PatientInput) -> dict:
    model, _, p, exp = _score(inp)
    prev = float(model.artifact["prevalence"])
    return {
        "probability": round(p, 4),
        "base_value": exp["base_value"],
        "output_space": exp["output_space"],
        "contributions": exp["contributions"],
        "explanation": plain.explanation_text(p, prev, exp["contributions"]),
        "note": (
            f"Technical note: SHAP values are in the model's {exp['output_space']} space and are computed on the "
            "uncalibrated model; the displayed probability is calibrated. Calibration is monotonic, so the direction "
            "of each contribution is preserved. Contributions are associations, not causes."
        ),
    }


def model_summary() -> dict:
    model = get_registry().risk_model()
    m = model.metrics
    return {
        "active": {"name": model.name, "version": model.version, "algorithm": model.algorithm,
                   "algorithm_display": model.algorithm_display, "threshold": model.artifact["threshold"],
                   "trained_at": m["trained_at"]},
        "dataset": m["dataset"],
        "splits": m["splits"],
        "selection_criterion": m["selection_criterion"],
        "threshold_policy": m["threshold_policy"],
        "candidates": [{"key": k, "display_name": v["display_name"], "best_params": v["best_params"]}
                       for k, v in m["models"].items()],
    }


def performance() -> dict:
    m = get_registry().risk_model().metrics
    out = {k: m[k] for k in ("selected_model", "selection_criterion", "threshold_policy", "tuning", "models",
                             "selected", "splits")}
    t = m["models"][m["selected_model"]]["test"]["at_threshold"]
    out["plain_summary"] = plain.accuracy_summary(t["recall"], t["specificity"])
    return out
