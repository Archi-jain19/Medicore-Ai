"""Global SHAP analysis of the active model on a held-out test sample.

Writes models/<name>/<version>/shap_global.json and docs/figures/shap_summary.png
Usage: python -m src.evaluation.explain_global
"""
import json
import logging

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shap  # noqa: E402

from src.config import DATA_PROCESSED, FIGURES_DIR, MODELS_DIR, RANDOM_STATE, RAW_FEATURES  # noqa: E402
from src.inference.explainer import RiskExplainer  # noqa: E402

log = logging.getLogger("shap")


def active_artifact_dir():
    reg = json.loads((MODELS_DIR / "registry.json").read_text())
    return MODELS_DIR / reg["diabetes_risk"]["path"]


def run(n: int = 2000):
    d = active_artifact_dir()
    artifact = joblib.load(d / "model.joblib")
    test = pd.read_csv(DATA_PROCESSED / "test.csv").sample(n=n, random_state=RANDOM_STATE)
    X = test[RAW_FEATURES]
    exp = RiskExplainer(artifact)
    summary = exp.global_summary(X)
    summary["algorithm"] = artifact["algorithm"]
    summary["note"] = ("Mean |SHAP| measures how much the model relies on a feature. It reflects statistical "
                       "association in survey data and does not establish causation.")
    (d / "shap_global.json").write_text(json.dumps(summary))

    vals, _ = exp._raw_shap(X)
    keys, grouped = exp._group(vals)
    shown = exp._display_values(X)
    disp = pd.DataFrame({k: (shown["BMI"] if k == "bmi_category" else shown[k]).to_numpy(dtype=float)
                         for k in keys})
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    shap.summary_plot(grouped, disp, feature_names=keys, show=False, max_display=15)
    plt.title(f"SHAP summary — {artifact['algorithm_display']} ({exp.output_space})")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "shap_summary.png", dpi=120)
    plt.close()
    top = [(f["feature"], f["mean_abs_shap"]) for f in summary["features"][:8]]
    log.info("Top features by mean |SHAP|: %s", top)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    np.random.seed(RANDOM_STATE)
    run()
