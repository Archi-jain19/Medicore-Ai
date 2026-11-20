"""ML pipeline + prediction endpoint tests.

A small artifact is trained on a sample of the real processed training split (or skipped if the data
pipeline has not been run) so the tests exercise the same code path as production without depending
on the full training run.
"""
import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression

from app.core.config import PROJECT_ROOT
from app.ml import registry as reg_mod

pytest.importorskip("shap")
from src.config import RAW_FEATURES, TARGET  # noqa: E402
from src.feature_engineering.features import HealthFeatureBuilder, QuantileClipper  # noqa: E402
from src.preprocessing.pipeline import build_model_pipeline  # noqa: E402

TRAIN_CSV = PROJECT_ROOT / "data" / "processed" / "train.csv"

SAMPLE = {
    "HighBP": 1, "HighChol": 1, "CholCheck": 1, "BMI": 34.0, "Smoker": 0, "Stroke": 0,
    "HeartDiseaseorAttack": 0, "PhysActivity": 0, "Fruits": 1, "Veggies": 1, "HvyAlcoholConsump": 0,
    "AnyHealthcare": 1, "NoDocbcCost": 0, "GenHlth": 4, "MentHlth": 2, "PhysHlth": 10, "DiffWalk": 1,
    "Sex": 1, "Age": 10, "Education": 4, "Income": 5,
}


@pytest.fixture(scope="module")
def train_df():
    if not TRAIN_CSV.exists():
        pytest.skip("Processed data missing — run python -m src.preprocessing.validate")
    return pd.read_csv(TRAIN_CSV).sample(4000, random_state=0)


@pytest.fixture()
def tiny_registry(tmp_path, train_df, monkeypatch):
    X, y = train_df[RAW_FEATURES], train_df[TARGET].to_numpy()
    fit, cal = slice(0, 3000), slice(3000, None)
    pipe = build_model_pipeline(LogisticRegression(max_iter=1000)).fit(X.iloc[fit], y[fit])
    calibrated = CalibratedClassifierCV(FrozenEstimator(pipe), method="sigmoid").fit(X.iloc[cal], y[cal])
    d = tmp_path / "diabetes_risk" / "0.0.1"
    d.mkdir(parents=True)
    pre = pipe.named_steps["preprocess"]
    joblib.dump({
        "name": "diabetes_risk", "version": "0.0.1", "algorithm": "logistic_regression",
        "algorithm_display": "Logistic Regression", "calibrated_pipeline": calibrated, "base_pipeline": pipe,
        "threshold": 0.2, "features": RAW_FEATURES, "transformed_feature_names": list(pre.get_feature_names_out()),
        "background": pre.transform(X.iloc[:200]), "prevalence": float(y.mean()), "trained_at": "test",
    }, d / "model.joblib")
    metrics = {"trained_at": "test", "dataset": {}, "splits": {}, "selection_criterion": "x", "threshold_policy": "y",
               "tuning": {}, "selected": {}, "selected_model": "logistic_regression",
               "models": {"logistic_regression": {"display_name": "Logistic Regression", "best_params": {},
                                                  "test": {"roc_auc": 0.8}, "validation": {"pr_auc": 0.4}}}}
    (d / "metrics.json").write_text(json.dumps(metrics))
    (tmp_path / "registry.json").write_text(json.dumps({"diabetes_risk": {"path": "diabetes_risk/0.0.1"}}))
    monkeypatch.setattr(reg_mod, "_registry", reg_mod.ModelRegistry(tmp_path))
    yield tmp_path
    monkeypatch.setattr(reg_mod, "_registry", None)


# ------------------------------------------------------------------ pipeline units
def test_feature_builder_engineered_columns():
    df = pd.DataFrame([SAMPLE])
    out = HealthFeatureBuilder().fit_transform(df)
    row = out.iloc[0]
    assert row["bmi_category"] == "obese_I"
    assert row["cardiometabolic_count"] == 2
    assert row["lifestyle_score"] == 0 + 1 + 1 + 1 + 1
    assert row["poor_health_days"] == 12
    assert row["access_barrier"] == 0


def test_clipper_learns_bounds_on_fit_only():
    train = pd.DataFrame({"BMI": np.r_[np.full(999, 25.0), 90.0]})
    c = QuantileClipper(columns=("BMI",), lower=0.0, upper=0.99).fit(train)
    hi = c.bounds_["BMI"][1]
    assert hi == 25.0
    assert c.transform(pd.DataFrame({"BMI": [80.0]}))["BMI"].iloc[0] == hi


def test_preprocessor_has_no_nans_and_stable_names(train_df):
    pipe = build_model_pipeline(LogisticRegression(max_iter=500)).fit(train_df[RAW_FEATURES], train_df[TARGET])
    pre = pipe.named_steps["preprocess"]
    Z = pre.transform(train_df[RAW_FEATURES].head(50))
    assert not np.isnan(Z).any()
    names = list(pre.get_feature_names_out())
    assert Z.shape[1] == len(names) and "bmi_category_obese_I" in names


# ------------------------------------------------------------------ API
def test_predict_requires_auth(client):
    assert client.post("/api/ml/predict", json=SAMPLE).status_code == 401


def test_predict_validation(client, auth_headers, tiny_registry):
    h = auth_headers()
    bad = {**SAMPLE, "BMI": 5, "HighBP": 3}
    r = client.post("/api/ml/predict", json=bad, headers=h)
    assert r.status_code == 422
    r = client.post("/api/ml/predict", json={**SAMPLE, "extra_field": 1}, headers=h)
    assert r.status_code == 422


def test_predict_returns_model_output_and_persists(client, auth_headers, tiny_registry):
    h = auth_headers()
    r = client.post("/api/ml/predict", json=SAMPLE, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    model = reg_mod.get_registry().risk_model()
    expected = model.artifact["calibrated_pipeline"].predict_proba(pd.DataFrame([SAMPLE])[RAW_FEATURES])[0, 1]
    assert body["probability"] == pytest.approx(expected, abs=1e-4)
    assert body["predicted_class"] == int(expected >= 0.2)
    assert body["model_version"] == "0.0.1"
    assert body["limitations"] and "not a diagnosis" in body["limitations"][0]
    assert len(body["top_contributions"]) == 6
    hist = client.get("/api/ml/predictions", headers=h).json()
    assert len(hist) == 1 and hist[0]["id"] == body["id"]


def test_prediction_history_is_private(client, auth_headers, tiny_registry):
    a, b = auth_headers("a@example.com"), auth_headers("b@example.com")
    client.post("/api/ml/predict", json=SAMPLE, headers=a)
    assert client.get("/api/ml/predictions", headers=b).json() == []


def test_explain_contributions_reconstruct_log_odds(client, auth_headers, tiny_registry):
    h = auth_headers()
    r = client.post("/api/ml/explain", json=SAMPLE, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    model = reg_mod.get_registry().risk_model()
    margin = model.artifact["base_pipeline"].decision_function(pd.DataFrame([SAMPLE])[RAW_FEATURES])[0]
    total = body["base_value"] + sum(c["shap_value"] for c in body["contributions"])
    assert total == pytest.approx(margin, abs=1e-3)  # SHAP local accuracy property
    assert {c["feature"] for c in body["contributions"]} >= {"BMI", "bmi_category", "HighBP"}


def test_model_unavailable_returns_503(client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr(reg_mod, "_registry", reg_mod.ModelRegistry(tmp_path / "empty"))
    r = client.post("/api/ml/predict", json=SAMPLE, headers=auth_headers())
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"
    monkeypatch.setattr(reg_mod, "_registry", None)


def test_results_are_written_in_plain_language(client, auth_headers, tiny_registry):
    body = client.post("/api/ml/predict", json=SAMPLE, headers=auth_headers()).json()
    assert body["chance_text"].endswith("in 100") and "in 100 people" in body["explanation"]
    assert body["headline"] and body["next_step"]
    jargon = ("calibrated", "threshold", "SHAP", "probability", "model estimate", "log-odds", "feature")
    shown = " ".join([body["headline"], body["next_step"], body["explanation"], *body["limitations"]])
    assert not [w for w in jargon if w.lower() in shown.lower()]
    top = body["top_contributions"][0]
    assert top["plain_label"] and top["plain_value"] and top["plain_label"] != top["feature"]
    assert any(c["plain_label"] == "How you rate your overall health" and c["plain_value"] == "Fair"
               for c in body["top_contributions"] + client.post("/api/ml/explain", json=SAMPLE,
                                                                  headers=auth_headers("o@example.com")).json()["contributions"])
