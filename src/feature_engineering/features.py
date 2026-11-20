"""Leakage-safe, sklearn-compatible feature engineering.

Every learned quantity (e.g. clipping bounds) is estimated in ``fit`` on training folds only, so the
same objects can sit inside a Pipeline that is cross-validated and later serialised with joblib.

Engineered features and rationale (documented in docs/ML_METHODOLOGY.md):

* ``bmi_category`` — WHO adult BMI bands. Risk associated with BMI is non-linear; bands let linear
  models capture thresholds and make explanations easier to read.
* ``cardiometabolic_count`` — HighBP + HighChol + HeartDiseaseorAttack + Stroke. Cardiometabolic
  conditions co-occur; a count summarises burden in one ordinal value.
* ``lifestyle_score`` — PhysActivity + Fruits + Veggies + (1-Smoker) + (1-HvyAlcoholConsump), 0..5.
  Higher = more self-reported protective behaviours.
* ``poor_health_days`` — MentHlth + PhysHlth (0..60) as a single recent-wellbeing indicator.
* ``access_barrier`` — 1 if no healthcare coverage OR cost prevented a doctor visit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

BMI_BINS = [-np.inf, 18.5, 25, 30, 35, 40, np.inf]
BMI_LABELS = ["underweight", "normal", "overweight", "obese_I", "obese_II", "obese_III"]

ENGINEERED_NUMERIC = ["cardiometabolic_count", "lifestyle_score", "poor_health_days"]
ENGINEERED_BINARY = ["access_barrier"]
ENGINEERED_CATEGORICAL = ["bmi_category"]


class QuantileClipper(BaseEstimator, TransformerMixin):
    """Winsorise selected columns to quantiles learned on the training data."""

    def __init__(self, columns=("BMI",), lower: float = 0.001, upper: float = 0.999):
        self.columns = columns
        self.lower = lower
        self.upper = upper

    def fit(self, X: pd.DataFrame, y=None):
        X = pd.DataFrame(X)
        self.bounds_ = {c: (float(X[c].quantile(self.lower)), float(X[c].quantile(self.upper))) for c in self.columns}
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = pd.DataFrame(X).copy()
        for c, (lo, hi) in self.bounds_.items():
            X[c] = X[c].clip(lo, hi)
        return X

    def get_feature_names_out(self, input_features=None):
        return self.feature_names_in_


class HealthFeatureBuilder(BaseEstimator, TransformerMixin):
    """Adds domain-motivated features. Stateless (no learned parameters)."""

    def fit(self, X, y=None):
        self.feature_names_in_ = np.asarray(pd.DataFrame(X).columns, dtype=object)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = pd.DataFrame(X).copy()
        X["bmi_category"] = pd.cut(X["BMI"], bins=BMI_BINS, labels=BMI_LABELS, right=False).astype(str)
        X["cardiometabolic_count"] = X[["HighBP", "HighChol", "HeartDiseaseorAttack", "Stroke"]].sum(axis=1)
        X["lifestyle_score"] = (
            X["PhysActivity"] + X["Fruits"] + X["Veggies"] + (1 - X["Smoker"]) + (1 - X["HvyAlcoholConsump"])
        )
        X["poor_health_days"] = X["MentHlth"] + X["PhysHlth"]
        X["access_barrier"] = ((X["AnyHealthcare"] == 0) | (X["NoDocbcCost"] == 1)).astype(int)
        return X

    def get_feature_names_out(self, input_features=None):
        base = list(self.feature_names_in_)
        return np.asarray(base + ENGINEERED_CATEGORICAL + ENGINEERED_NUMERIC + ENGINEERED_BINARY, dtype=object)
