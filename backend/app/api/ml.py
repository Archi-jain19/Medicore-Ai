from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.errors import ServiceUnavailableError
from app.core.rate_limit import limiter
from app.ml.registry import get_registry
from app.models import Prediction
from app.schemas.ml import ExplanationOut, PatientInput, PredictionHistoryItem, PredictionOut
from app.services import ml_service
from app.services import plain_language as plain

router = APIRouter(prefix="/ml", tags=["machine learning"])


@router.post("/predict", response_model=PredictionOut)
@limiter.limit("60/minute")
def predict(request: Request, body: PatientInput, db: DbSession, user: CurrentUser):
    """Diabetes-risk estimate from the trained, calibrated model. Persists to the user's history."""
    return ml_service.predict(db, user, body)


@router.post("/explain", response_model=ExplanationOut)
@limiter.limit("60/minute")
def explain(request: Request, body: PatientInput, user: CurrentUser):
    """Full SHAP explanation for one input (not persisted)."""
    return ml_service.explain(body)


@router.get("/models")
def models(user: CurrentUser):
    return ml_service.model_summary()


@router.get("/model-performance")
def model_performance(user: CurrentUser):
    return ml_service.performance()


@router.get("/feature-importance")
def feature_importance(user: CurrentUser):
    g = get_registry().risk_model().shap_global
    if g is None:
        raise ServiceUnavailableError("This information is not available right now. Please try again later.", code="model_unavailable")
    return {**g, "features": [{**f, "plain_label": plain.plain_label(f["feature"])} for f in g["features"]]}


@router.get("/clusters")
def clusters(user: CurrentUser):
    return get_registry().clusters()


@router.get("/predictions", response_model=list[PredictionHistoryItem])
def prediction_history(db: DbSession, user: CurrentUser, limit: int = Query(50, ge=1, le=200)):
    rows = db.scalars(
        select(Prediction).where(Prediction.user_id == user.id).order_by(Prediction.id.desc()).limit(limit)
    )
    return list(rows)
