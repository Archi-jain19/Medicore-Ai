"""Unsupervised respondent segmentation (K-Means) on standardised health-indicator features.

Clusters are described by their statistical profile only. They are NOT diagnoses or disease labels.
The diabetes target is excluded from clustering and only used afterwards to describe segments.

Usage: python -m src.segmentation.cluster
"""
import json
import logging

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402
from sklearn.decomposition import PCA  # noqa: E402
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from src.config import DATA_PROCESSED, FIGURES_DIR, MODELS_DIR, RANDOM_STATE, TARGET  # noqa: E402
from src.feature_engineering.features import HealthFeatureBuilder  # noqa: E402

log = logging.getLogger("segmentation")

SEGMENT_FEATURES = ["BMI", "GenHlth", "MentHlth", "PhysHlth", "Age", "Income",
                    "cardiometabolic_count", "lifestyle_score", "DiffWalk"]
K_RANGE = range(2, 9)
SAMPLE = 30_000          # silhouette is O(n^2); evaluate on a stratified sample
SIL_SAMPLE = 10_000


def describe(profile: pd.Series, overall: pd.Series, std: pd.Series) -> list[str]:
    """Statistical, non-clinical description: features whose mean differs most from the overall mean."""
    z = ((profile - overall) / std).sort_values(key=abs, ascending=False)
    out = []
    for f, v in z.head(3).items():
        if abs(v) < 0.25:
            continue
        out.append(f"{'higher' if v > 0 else 'lower'} {f} than average ({profile[f]:.2f} vs {overall[f]:.2f})")
    return out or ["close to the overall average on all features"]


def run():
    df = pd.read_csv(DATA_PROCESSED / "train.csv")
    feats = HealthFeatureBuilder().fit_transform(df)
    X = feats[SEGMENT_FEATURES].astype(float)
    Xs = X.sample(n=SAMPLE, random_state=RANDOM_STATE)
    scaler = StandardScaler().fit(Xs)
    Zs = scaler.transform(Xs)

    rng = np.random.default_rng(RANDOM_STATE)
    sil_idx = rng.choice(len(Zs), SIL_SAMPLE, replace=False)
    selection = []
    for k in K_RANGE:
        km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit(Zs)
        selection.append({
            "k": k, "inertia": round(float(km.inertia_), 1),
            "silhouette": round(float(silhouette_score(Zs[sil_idx], km.labels_[sil_idx])), 4),
            "davies_bouldin": round(float(davies_bouldin_score(Zs, km.labels_)), 4),
            "calinski_harabasz": round(float(calinski_harabasz_score(Zs, km.labels_)), 1),
        })
        log.info("k=%d inertia=%.0f silhouette=%.4f", k, km.inertia_, selection[-1]["silhouette"])

    # Elbow: largest second difference of inertia; final k = best silhouette among k in [3, 6]
    # (k=2 usually wins silhouette trivially but is too coarse to be useful for profiling)
    inertia = np.array([s["inertia"] for s in selection])
    elbow_k = list(K_RANGE)[int(np.argmax(np.diff(inertia, 2))) + 1]
    candidates = [s for s in selection if 3 <= s["k"] <= 6]
    best_k = max(candidates, key=lambda s: s["silhouette"])["k"]

    model = Pipeline([("scale", StandardScaler()),
                      ("kmeans", KMeans(n_clusters=best_k, n_init=10, random_state=RANDOM_STATE))])
    labels = model.fit_predict(X)
    feats["segment"] = labels

    overall, std = X.mean(), X.std()
    segments = []
    for c in range(best_k):
        part = feats[feats.segment == c]
        prof = part[SEGMENT_FEATURES].mean()
        segments.append({
            "id": int(c),
            "name": f"Segment {chr(65 + c)}",
            "size": int(len(part)),
            "share": round(len(part) / len(feats), 4),
            "feature_means": {k: round(float(v), 3) for k, v in prof.items()},
            "observed_diabetes_rate": round(float(part[TARGET].mean()), 4),
            "description": describe(prof, overall, std),
        })

    pca = PCA(n_components=2, random_state=RANDOM_STATE).fit(model.named_steps["scale"].transform(X))
    show_idx = rng.choice(len(X), 1500, replace=False)
    proj = pca.transform(model.named_steps["scale"].transform(X.iloc[show_idx]))
    points = [{"x": round(float(a), 3), "y": round(float(b), 3), "segment": int(s)}
              for (a, b), s in zip(proj, labels[show_idx])]

    out = {
        "algorithm": "KMeans (StandardScaler, n_init=10)",
        "features": SEGMENT_FEATURES,
        "n_rows": int(len(X)),
        "selection": selection,
        "elbow_k": int(elbow_k),
        "chosen_k": int(best_k),
        "choice_rule": "highest silhouette (10k-row sample) among k in [3, 6]; elbow reported for reference",
        "final_silhouette_sample": round(float(silhouette_score(
            model.named_steps["scale"].transform(X.iloc[show_idx]), labels[show_idx])), 4),
        "pca_explained_variance": [round(float(v), 4) for v in pca.explained_variance_ratio_],
        "segments": segments,
        "pca_points": points,
        "note": "Segments group respondents with similar survey answers. They are statistical groupings, "
                "not diagnoses. The diabetes rate is shown descriptively and was not used for clustering.",
    }
    seg_dir = MODELS_DIR / "segmentation"
    seg_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": model, "pca": pca, "features": SEGMENT_FEATURES}, seg_dir / "kmeans.joblib", compress=3)
    (seg_dir / "clusters.json").write_text(json.dumps(out, indent=2))

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].plot(list(K_RANGE), inertia, marker="o", color="#1e3a5f")
    axes[0].axvline(best_k, ls="--", color="#14b8a6")
    axes[0].set(title="Elbow (inertia)", xlabel="k")
    ax2 = axes[0].twinx()
    ax2.plot(list(K_RANGE), [s["silhouette"] for s in selection], marker="s", color="#94a3b8")
    ax2.set_ylabel("silhouette")
    axes[1].scatter(proj[:, 0], proj[:, 1], c=labels[show_idx], cmap="tab10", s=6, alpha=0.6)
    axes[1].set(title=f"PCA projection (k={best_k})", xlabel="PC1", ylabel="PC2")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "segmentation.png", dpi=120)
    plt.close(fig)
    log.info("Chosen k=%d (elbow=%d). Segments: %s", best_k, elbow_k,
             [(s["name"], s["size"], s["observed_diabetes_rate"]) for s in segments])
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
