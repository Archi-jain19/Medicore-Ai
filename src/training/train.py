"""Train, tune, compare, calibrate and persist diabetes-risk classifiers.

Protocol (see docs/ML_METHODOLOGY.md):
  * train split  -> hyper-parameter search (Stratified K-fold CV on a stratified tuning subsample)
                    and final refit. All preprocessing lives inside the Pipeline, so each CV fold
                    fits imputers/scalers/clippers on its own training portion only.
  * val split    -> model selection (PR-AUC), isotonic probability calibration, threshold choice.
  * test split   -> touched once, for final reporting of every model.

Usage: python -m src.training.train [--quick]
"""
import argparse
import json
import logging
import platform
import time
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from scipy.stats import loguniform, randint, uniform
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV, StratifiedKFold, train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier

from src.config import DATA_PROCESSED, DATASET, MODELS_DIR, RANDOM_STATE, RAW_FEATURES, TARGET
from src.evaluation import metrics as M
from src.preprocessing.pipeline import build_model_pipeline

log = logging.getLogger("train")

MODEL_NAME = "diabetes_risk"
MODEL_VERSION = "1.0.0"
DISPLAY = {
    "logistic_regression": "Logistic Regression",
    "decision_tree": "Decision Tree",
    "random_forest": "Random Forest",
    "svm_linear": "Support Vector Machine (linear, calibrated)",
    "knn": "K-Nearest Neighbors",
    "gradient_boosting": "Gradient Boosting (HistGradientBoosting)",
    "xgboost": "XGBoost",
}


def model_specs(spw: float, quick: bool):
    it = 4 if quick else 12
    return {
        "logistic_regression": dict(
            est=LogisticRegression(max_iter=3000, class_weight="balanced"),
            search="grid", space={"model__C": [0.01, 0.1, 1.0, 10.0]},
        ),
        "decision_tree": dict(
            est=DecisionTreeClassifier(class_weight="balanced", random_state=RANDOM_STATE),
            search="grid", space={"model__max_depth": [4, 6, 8, 10, 14], "model__min_samples_leaf": [20, 100, 400]},
        ),
        "random_forest": dict(
            est=RandomForestClassifier(n_estimators=200, class_weight="balanced_subsample",
                                       n_jobs=-1, random_state=RANDOM_STATE),
            search="random", n_iter=it, search_jobs=1,
            space={"model__max_depth": [8, 12, 16], "model__min_samples_leaf": [5, 20, 50, 100],
                   "model__max_features": ["sqrt", 0.3, 0.5]},
        ),
        "svm_linear": dict(
            est=LinearSVC(class_weight="balanced", dual="auto", max_iter=5000, random_state=RANDOM_STATE),
            search="grid", space={"model__C": [0.001, 0.01, 0.1, 1.0]},
        ),
        "knn": dict(
            est=KNeighborsClassifier(n_jobs=-1),
            search="grid", search_jobs=1, final_fit_rows=40_000,
            space={"model__n_neighbors": [25, 75, 151], "model__weights": ["uniform", "distance"]},
        ),
        "gradient_boosting": dict(
            est=HistGradientBoostingClassifier(class_weight="balanced", early_stopping=True,
                                               random_state=RANDOM_STATE),
            search="random", n_iter=it,
            space={"model__learning_rate": loguniform(0.02, 0.3), "model__max_leaf_nodes": randint(15, 63),
                   "model__min_samples_leaf": randint(20, 200), "model__l2_regularization": loguniform(1e-3, 10)},
        ),
        "xgboost": dict(
            est=XGBClassifier(n_estimators=400, tree_method="hist", eval_metric="aucpr", scale_pos_weight=spw,
                              n_jobs=-1, random_state=RANDOM_STATE),
            search="random", n_iter=it, search_jobs=1,
            space={"model__max_depth": randint(3, 8), "model__learning_rate": loguniform(0.02, 0.2),
                   "model__subsample": uniform(0.6, 0.4), "model__colsample_bytree": uniform(0.5, 0.5),
                   "model__min_child_weight": randint(1, 20), "model__reg_lambda": loguniform(0.1, 10)},
        ),
    }


def scores(model, X) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    return model.decision_function(X)


def stratified_subsample(X, y, n, seed=RANDOM_STATE):
    if n >= len(X):
        return X, y
    Xs, _, ys, _ = train_test_split(X, y, train_size=n, stratify=y, random_state=seed)
    return Xs, ys


def load_splits():
    out = {}
    for name in ("train", "val", "test"):
        df = pd.read_csv(DATA_PROCESSED / f"{name}.csv")
        out[name] = (df[RAW_FEATURES], df[TARGET].to_numpy())
    return out


def run(quick: bool = False):
    splits = load_splits()
    X_tr, y_tr = splits["train"]
    X_val, y_val = splits["val"]
    X_te, y_te = splits["test"]
    spw = float((y_tr == 0).sum() / (y_tr == 1).sum())
    tune_n = 15_000 if quick else 50_000
    X_tune, y_tune = stratified_subsample(X_tr, y_tr, tune_n)
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=RANDOM_STATE)

    results, fitted = {}, {}
    for key, spec in model_specs(spw, quick).items():
        t0 = time.time()
        pipe = build_model_pipeline(spec["est"])
        common = dict(scoring="average_precision", cv=cv, n_jobs=spec.get("search_jobs", -1), refit=False)
        if spec["search"] == "grid":
            search = GridSearchCV(pipe, spec["space"], **common)
        else:
            search = RandomizedSearchCV(pipe, spec["space"], n_iter=spec["n_iter"], random_state=RANDOM_STATE,
                                        **common)
        log.info("[%s] tuning on %d rows (%s search)", key, len(X_tune), spec["search"])
        search.fit(X_tune, y_tune)
        best_params = search.best_params_
        # Refit on the full training split (KNN capped for inference cost)
        X_fit, y_fit = stratified_subsample(X_tr, y_tr, spec.get("final_fit_rows", len(X_tr)))
        pipe.set_params(**best_params)
        pipe.fit(X_fit, y_fit)
        tune_secs = time.time() - t0

        val_raw = scores(pipe, X_val)
        calibrated = CalibratedClassifierCV(FrozenEstimator(pipe), method="isotonic").fit(X_val, y_val)
        p_val = calibrated.predict_proba(X_val)[:, 1]
        thr = M.select_threshold_f2(y_val, p_val)
        t1 = time.time()
        p_te = calibrated.predict_proba(X_te)[:, 1]
        infer_ms = (time.time() - t1) / len(X_te) * 1000

        results[key] = {
            "display_name": DISPLAY[key],
            "best_params": {k.replace("model__", ""): (v.item() if hasattr(v, "item") else v)
                            for k, v in best_params.items()},
            "cv_pr_auc_mean": round(float(search.best_score_), 4),
            "cv_pr_auc_std": round(float(search.cv_results_["std_test_score"][search.best_index_]), 4),
            "train_rows": len(X_fit),
            "train_seconds": round(tune_secs, 1),
            "inference_ms_per_row": round(infer_ms, 4),
            "validation": {**M._round(M.ranking_metrics(y_val, val_raw)), "selected_threshold": round(thr, 4)},
            "test": M.full_report(y_te, p_te, thr),
        }
        fitted[key] = (pipe, calibrated, thr, p_te, p_val)
        log.info("[%s] val PR-AUC=%.4f  test ROC-AUC=%.4f PR-AUC=%.4f recall@thr=%.3f (%.0fs)", key,
                 results[key]["validation"]["pr_auc"], results[key]["test"]["roc_auc"],
                 results[key]["test"]["pr_auc"], results[key]["test"]["at_threshold"]["recall"], tune_secs)

    # Model selection on VALIDATION PR-AUC only (test is never used to choose)
    best_key = max(results, key=lambda k: results[k]["validation"]["pr_auc"])
    pipe, calibrated, thr, p_te, p_val = fitted[best_key]
    log.info("Selected model: %s", best_key)

    # Sensitivity check: test rows whose exact feature vector never appears in train
    train_keys = set(map(tuple, X_tr.to_numpy()))
    unseen = np.array([tuple(r) not in train_keys for r in X_te.to_numpy()])
    sensitivity = {
        "test_rows_with_feature_vector_unseen_in_train": int(unseen.sum()),
        **{f"unseen_{k}": v for k, v in M._round(M.ranking_metrics(y_te[unseen], p_te[unseen])).items()},
    }

    out_dir = MODELS_DIR / MODEL_NAME / MODEL_VERSION
    out_dir.mkdir(parents=True, exist_ok=True)
    background = pipe.named_steps["preprocess"].transform(stratified_subsample(X_tr, y_tr, 500)[0])
    artifact = {
        "name": MODEL_NAME,
        "version": MODEL_VERSION,
        "algorithm": best_key,
        "algorithm_display": DISPLAY[best_key],
        "calibrated_pipeline": calibrated,
        "base_pipeline": pipe,
        "threshold": thr,
        "features": RAW_FEATURES,
        "transformed_feature_names": list(pipe.named_steps["preprocess"].get_feature_names_out()),
        "background": background,
        "prevalence": float(y_tr.mean()),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    joblib.dump(artifact, out_dir / "model.joblib", compress=3)

    report = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "selected_model": best_key,
        "selection_criterion": "highest validation PR-AUC (uncalibrated scores)",
        "threshold_policy": "maximise F2 on validation (calibrated probabilities)",
        "dataset": {k: DATASET[k] for k in ("name", "doi", "url", "license", "origin")},
        "splits": {n: {"rows": int(len(s[1])), "positive_rate": round(float(s[1].mean()), 4)}
                   for n, s in splits.items()},
        "tuning": {"rows": len(X_tune), "cv": "StratifiedKFold(3, shuffle)", "scoring": "average_precision",
                   "quick_mode": quick},
        "models": results,
        "selected": {
            "curves_test": M.curves(y_te, p_te),
            "threshold_table_val": M.threshold_table(y_val, p_val),
            "bootstrap_test": M.bootstrap_ci(y_te, p_te),
            "duplicate_sensitivity": sensitivity,
        },
        "environment": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                        "xgboost": xgboost.__version__},
        "trained_at": artifact["trained_at"],
    }
    (out_dir / "metrics.json").write_text(json.dumps(report, indent=2))
    (MODELS_DIR / "registry.json").write_text(json.dumps(
        {MODEL_NAME: {"active_version": MODEL_VERSION, "path": f"{MODEL_NAME}/{MODEL_VERSION}"}}, indent=2))
    log.info("Saved artifact to %s", out_dir)
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--quick", action="store_true", help="smaller tuning budget for smoke tests")
    run(p.parse_args().quick)
