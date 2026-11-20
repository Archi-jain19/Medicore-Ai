"""Loads versioned model artifacts produced by the offline pipeline (read-only at runtime)."""
from __future__ import annotations

import json
import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib

from app.core.config import PROJECT_ROOT, get_settings
from app.core.errors import ServiceUnavailableError

# The joblib pipeline references transformers defined in the project-level `src` package
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

log = logging.getLogger("medicore.ml")

FRIENDLY_UNAVAILABLE = "The health check is not available right now. Please try again later."
# Operator-facing instructions: written to the server log only, never shown to users
TRAIN_HINT = (
    "Model artifacts not found. Run from the project root: "
    "python -m src.ingestion.download && python -m src.preprocessing.validate && "
    "python -m src.training.train && python -m src.evaluation.explain_global && python -m src.segmentation.cluster"
)


@dataclass
class LoadedModel:
    name: str
    version: str
    algorithm: str
    algorithm_display: str
    directory: Path
    artifact: dict[str, Any]
    metrics: dict[str, Any]
    shap_global: dict[str, Any] | None
    explainer: Any


class ModelRegistry:
    def __init__(self, models_dir: Path):
        self.models_dir = models_dir
        self._model: LoadedModel | None = None
        self._clusters: dict | None = None
        self._lock = threading.Lock()

    def risk_model(self) -> LoadedModel:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._load_risk_model()
        return self._model

    def _load_risk_model(self) -> LoadedModel:
        reg_path = self.models_dir / "registry.json"
        if not reg_path.exists():
            log.error(TRAIN_HINT)
            raise ServiceUnavailableError(FRIENDLY_UNAVAILABLE, code="model_unavailable")
        entry = json.loads(reg_path.read_text())["diabetes_risk"]
        d = self.models_dir / entry["path"]
        try:
            artifact = joblib.load(d / "model.joblib")
        except FileNotFoundError:
            log.error(TRAIN_HINT)
            raise ServiceUnavailableError(FRIENDLY_UNAVAILABLE, code="model_unavailable") from None
        from src.inference.explainer import RiskExplainer

        shap_path = d / "shap_global.json"
        log.info("Loaded model %s v%s (%s)", artifact["name"], artifact["version"], artifact["algorithm"])
        return LoadedModel(
            name=artifact["name"],
            version=artifact["version"],
            algorithm=artifact["algorithm"],
            algorithm_display=artifact["algorithm_display"],
            directory=d,
            artifact=artifact,
            metrics=json.loads((d / "metrics.json").read_text()),
            shap_global=json.loads(shap_path.read_text()) if shap_path.exists() else None,
            explainer=RiskExplainer(artifact),
        )

    def clusters(self) -> dict:
        if self._clusters is None:
            p = self.models_dir / "segmentation" / "clusters.json"
            if not p.exists():
                log.error(TRAIN_HINT)
                raise ServiceUnavailableError(FRIENDLY_UNAVAILABLE, code="model_unavailable")
            self._clusters = json.loads(p.read_text())
        return self._clusters


_registry: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry(get_settings().models_dir)
    return _registry
