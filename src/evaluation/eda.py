"""Exploratory data analysis on the TRAINING split only (test data stays unseen).

Writes: docs/figures/eda_*.png and data/processed/eda_report.json
Usage:  python -m src.evaluation.eda
"""
import json
import logging

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from scipy import stats  # noqa: E402

from src.config import (  # noqa: E402
    BINARY_FEATURES,
    CONTINUOUS_FEATURES,
    DATA_PROCESSED,
    FIGURES_DIR,
    ORDINAL_FEATURES,
    RAW_FEATURES,
    TARGET,
)
from src.feature_engineering.features import BMI_BINS, BMI_LABELS  # noqa: E402

log = logging.getLogger("eda")
NAVY, TEAL = "#1e3a5f", "#14b8a6"
sns.set_theme(style="whitegrid", font_scale=0.9)


def _save(fig, name):
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / f"eda_{name}.png", dpi=120)
    plt.close(fig)


def cramers_v(table: pd.DataFrame) -> float:
    chi2 = stats.chi2_contingency(table, correction=False)[0]
    n = table.values.sum()
    r, k = table.shape
    return float(np.sqrt(chi2 / (n * (min(r, k) - 1))))


def run():
    df = pd.read_csv(DATA_PROCESSED / "train.csv")
    report: dict = {"split": "train", "shape": list(df.shape)}
    report["missing"] = int(df.isna().sum().sum())
    report["duplicate_feature_rows"] = int(df[RAW_FEATURES + [TARGET]].duplicated().sum())
    report["describe"] = df[RAW_FEATURES].describe().T.round(3).to_dict(orient="index")
    report["class_distribution"] = df[TARGET].value_counts(normalize=True).round(4).to_dict()

    # Class distribution
    fig, ax = plt.subplots(figsize=(4, 3))
    df[TARGET].map({0: "No diabetes", 1: "Prediabetes/diabetes"}).value_counts().plot.bar(ax=ax, color=[NAVY, TEAL])
    ax.set_title("Class distribution (train)")
    ax.set_ylabel("Respondents")
    ax.tick_params(axis="x", rotation=0)
    _save(fig, "class_distribution")

    # Univariate: continuous + ordinal
    fig, axes = plt.subplots(2, 4, figsize=(14, 6))
    for ax, col in zip(axes.flat, CONTINUOUS_FEATURES + ORDINAL_FEATURES):
        sns.histplot(df[col], ax=ax, bins=30 if col == "BMI" else None, discrete=col != "BMI", color=NAVY)
        ax.set_title(col)
    axes.flat[-1].axis("off")
    _save(fig, "univariate")

    # Outliers (IQR rule) for continuous variables
    outliers = {}
    for col in CONTINUOUS_FEATURES:
        q1, q3 = df[col].quantile([0.25, 0.75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outliers[col] = {
            "iqr_low": float(lo), "iqr_high": float(hi),
            "n_outside": int(((df[col] < lo) | (df[col] > hi)).sum()),
            "p99_9": float(df[col].quantile(0.999)), "max": float(df[col].max()),
        }
    report["outliers_iqr"] = outliers
    fig, ax = plt.subplots(figsize=(8, 3))
    sns.boxplot(data=df[CONTINUOUS_FEATURES], orient="h", ax=ax, color=TEAL)
    ax.set_title("Continuous variables — outlier inspection")
    _save(fig, "outliers")

    # Bivariate: prevalence by feature + statistical association
    assoc = {}
    for col in BINARY_FEATURES + ORDINAL_FEATURES:
        table = pd.crosstab(df[col], df[TARGET])
        p = stats.chi2_contingency(table)[1]
        assoc[col] = {"test": "chi2", "p_value": float(p), "cramers_v": round(cramers_v(table), 4),
                      "prevalence_by_level": df.groupby(col)[TARGET].mean().round(4).to_dict()}
    for col in CONTINUOUS_FEATURES:
        a, b = df.loc[df[TARGET] == 1, col], df.loc[df[TARGET] == 0, col]
        u, p = stats.mannwhitneyu(a, b)
        assoc[col] = {"test": "mann_whitney_u", "p_value": float(p),
                      "rank_biserial": round(float(2 * u / (len(a) * len(b)) - 1), 4),
                      "median_pos": float(a.median()), "median_neg": float(b.median())}
    report["association_with_target"] = assoc

    fig, axes = plt.subplots(1, 4, figsize=(15, 3.5))
    for ax, col in zip(axes, ["GenHlth", "Age", "Income", "HighBP"]):
        df.groupby(col)[TARGET].mean().plot.bar(ax=ax, color=NAVY)
        ax.set_title(f"Prevalence by {col}")
        ax.set_ylabel("Positive rate")
        ax.tick_params(axis="x", rotation=0)
    _save(fig, "prevalence_by_feature")

    bmi_cat = pd.cut(df["BMI"], bins=BMI_BINS, labels=BMI_LABELS, right=False)
    report["prevalence_by_bmi_category"] = df.groupby(bmi_cat, observed=True)[TARGET].mean().round(4).to_dict()
    fig, ax = plt.subplots(figsize=(6, 3.5))
    sns.kdeplot(data=df, x="BMI", hue=TARGET, common_norm=False, ax=ax, palette=[NAVY, TEAL])
    ax.set_xlim(10, 70)
    ax.set_title("BMI density by class")
    _save(fig, "bmi_by_class")

    # Correlation (Spearman — mostly ordinal/binary variables)
    corr = df[RAW_FEATURES + [TARGET]].corr(method="spearman")
    report["spearman_with_target"] = corr[TARGET].drop(TARGET).sort_values(key=abs, ascending=False).round(4).to_dict()
    top_pairs = (
        corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).stack().sort_values(key=abs, ascending=False).head(8)
    )
    report["top_feature_correlations"] = {f"{a}~{b}": round(float(v), 4) for (a, b), v in top_pairs.items()}
    fig, ax = plt.subplots(figsize=(11, 9))
    sns.heatmap(corr, cmap="vlag", center=0, ax=ax, square=True, cbar_kws={"shrink": 0.7})
    ax.set_title("Spearman correlation (train)")
    _save(fig, "correlation")

    (DATA_PROCESSED / "eda_report.json").write_text(json.dumps(report, indent=2, default=str))
    log.info("EDA complete. Top target correlations: %s", list(report["spearman_with_target"].items())[:6])
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
