"""Preprocessing: Pipeline + ColumnTransformer. Fit only on training folds (no leakage)."""
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.config import BINARY_FEATURES, CONTINUOUS_FEATURES, ORDINAL_FEATURES
from src.feature_engineering.features import (
    BMI_LABELS,
    ENGINEERED_BINARY,
    ENGINEERED_CATEGORICAL,
    ENGINEERED_NUMERIC,
    HealthFeatureBuilder,
    QuantileClipper,
)


def build_preprocessor() -> Pipeline:
    numeric = ORDINAL_FEATURES + CONTINUOUS_FEATURES + ENGINEERED_NUMERIC
    binary = BINARY_FEATURES + ENGINEERED_BINARY
    columns = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
            ("bin", SimpleImputer(strategy="most_frequent"), binary),
            (
                "cat",
                OneHotEncoder(categories=[BMI_LABELS], handle_unknown="ignore", sparse_output=False),
                ENGINEERED_CATEGORICAL,
            ),
        ],
        verbose_feature_names_out=False,
    )
    return Pipeline(
        [
            ("clip", QuantileClipper(columns=("BMI",))),
            ("features", HealthFeatureBuilder()),
            ("columns", columns),
        ]
    )


def build_model_pipeline(estimator) -> Pipeline:
    return Pipeline([("preprocess", build_preprocessor()), ("model", estimator)])
