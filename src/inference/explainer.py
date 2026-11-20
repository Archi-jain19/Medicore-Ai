"""SHAP-based explanations for the saved risk pipeline (used offline and by the API).

SHAP values describe how the *model* uses each feature relative to a baseline. They are
associations learned from survey data, not causal effects.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap

TREE_MODELS = {"random_forest", "decision_tree", "gradient_boosting", "xgboost"}
LINEAR_MODELS = {"logistic_regression", "svm_linear"}

FEATURE_LABELS = {
    "HighBP": "High blood pressure", "HighChol": "High cholesterol", "CholCheck": "Cholesterol check (5 yrs)",
    "BMI": "Body mass index", "Smoker": "Smoked ≥100 cigarettes", "Stroke": "Ever had a stroke",
    "HeartDiseaseorAttack": "Coronary heart disease / MI", "PhysActivity": "Physical activity (30 days)",
    "Fruits": "Fruit daily", "Veggies": "Vegetables daily", "HvyAlcoholConsump": "Heavy alcohol use",
    "AnyHealthcare": "Has healthcare coverage", "NoDocbcCost": "Skipped doctor due to cost",
    "GenHlth": "Self-rated general health (1=excellent…5=poor)", "MentHlth": "Poor mental-health days (30)",
    "PhysHlth": "Poor physical-health days (30)", "DiffWalk": "Difficulty walking", "Sex": "Sex (1=male)",
    "Age": "Age group (1=18–24 … 13=80+)", "Education": "Education level (1–6)", "Income": "Income band (1–8)",
    "bmi_category": "BMI category (engineered)", "cardiometabolic_count": "Cardiometabolic conditions (engineered)",
    "lifestyle_score": "Healthy-lifestyle score (engineered)", "poor_health_days": "Poor-health days (engineered)",
    "access_barrier": "Healthcare access barrier (engineered)",
}
OHE_PREFIX = "bmi_category_"


class RiskExplainer:
    def __init__(self, artifact: dict):
        base = artifact["base_pipeline"]
        self.algorithm = artifact["algorithm"]
        self.pre = base.named_steps["preprocess"]
        self.model = base.named_steps["model"]
        self.names = list(artifact["transformed_feature_names"])
        bg = np.asarray(artifact["background"], dtype=float)
        if self.algorithm in TREE_MODELS:
            self._explainer = shap.TreeExplainer(self.model)
            self.output_space = "probability" if self.algorithm in {"random_forest", "decision_tree"} else "log-odds"
        elif self.algorithm in LINEAR_MODELS:
            self._explainer = shap.LinearExplainer(self.model, bg)
            self.output_space = "log-odds" if self.algorithm == "logistic_regression" else "decision score"
        else:
            f = (lambda Z: self.model.predict_proba(Z)[:, 1])
            self._explainer = shap.PermutationExplainer(f, shap.maskers.Independent(bg, max_samples=100))
            self.output_space = "probability"

    # ---------------------------------------------------------------- core
    def _raw_shap(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        Z = np.asarray(self.pre.transform(X), dtype=float)
        ex = self._explainer(Z)
        vals = np.asarray(ex.values)
        base = np.asarray(ex.base_values)
        if vals.ndim == 3:  # (n, features, classes) -> positive class
            vals, base = vals[..., 1], base[..., 1] if base.ndim == 2 else base
        return vals, np.broadcast_to(base, (vals.shape[0],)).astype(float)

    def _group(self, vals: np.ndarray) -> tuple[list[str], np.ndarray]:
        """Sum one-hot BMI-category columns back into a single feature."""
        groups: dict[str, list[int]] = {}
        for i, n in enumerate(self.names):
            groups.setdefault("bmi_category" if n.startswith(OHE_PREFIX) else n, []).append(i)
        keys = list(groups)
        return keys, np.stack([vals[:, idx].sum(axis=1) for idx in groups.values()], axis=1)

    def _display_values(self, X: pd.DataFrame) -> pd.DataFrame:
        """Unscaled values after clipping + feature engineering (what the user can relate to)."""
        return self.pre[:-1].transform(X)

    # ---------------------------------------------------------------- API
    def explain_one(self, X: pd.DataFrame, top_k: int | None = None) -> dict:
        vals, base = self._raw_shap(X)
        keys, grouped = self._group(vals)
        shown = self._display_values(X).iloc[0]
        contribs = [
            {
                "feature": k,
                "label": FEATURE_LABELS.get(k, k),
                "value": _py(shown[k]) if k in shown.index else None,
                "shap_value": round(float(v), 5),
                "direction": "increases" if v > 0 else "decreases" if v < 0 else "neutral",
            }
            for k, v in zip(keys, grouped[0])
        ]
        contribs.sort(key=lambda c: abs(c["shap_value"]), reverse=True)
        return {
            "base_value": round(float(base[0]), 5),
            "output_space": self.output_space,
            "contributions": contribs[:top_k] if top_k else contribs,
        }

    def global_summary(self, X: pd.DataFrame, points_per_feature: int = 250, seed: int = 0) -> dict:
        vals, base = self._raw_shap(X)
        keys, grouped = self._group(vals)
        shown = self._display_values(X)
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(X), size=min(points_per_feature, len(X)), replace=False)
        features = []
        for j, k in enumerate(keys):
            col = shown[k] if k in shown.columns else None
            if col is not None and k == "bmi_category":
                col = shown["BMI"]  # colour BMI-category points by underlying BMI
            if col is not None:
                ranks = pd.Series(np.asarray(col, dtype=float)).rank(pct=True).to_numpy()
            features.append({
                "feature": k,
                "label": FEATURE_LABELS.get(k, k),
                "mean_abs_shap": round(float(np.abs(grouped[:, j]).mean()), 5),
                "mean_shap": round(float(grouped[:, j].mean()), 5),
                "points": [
                    {"shap": round(float(grouped[i, j]), 4),
                     "value_pct": round(float(ranks[i]), 3) if col is not None else None}
                    for i in idx
                ],
            })
        features.sort(key=lambda f: f["mean_abs_shap"], reverse=True)
        return {"n_samples": len(X), "base_value": round(float(base.mean()), 5),
                "output_space": self.output_space, "features": features}


def _py(v):
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float):
        return round(v, 3)
    return v
