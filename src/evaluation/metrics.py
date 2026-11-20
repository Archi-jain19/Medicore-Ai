"""Classification metrics with attention to false negatives/positives (not accuracy alone)."""
import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    fbeta_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)


def threshold_metrics(y, p, threshold: float) -> dict:
    yhat = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, yhat, labels=[0, 1]).ravel()
    return {
        "threshold": round(float(threshold), 4),
        "accuracy": accuracy_score(y, yhat),
        "precision": precision_score(y, yhat, zero_division=0),
        "recall": recall_score(y, yhat),
        "specificity": tn / (tn + fp) if (tn + fp) else 0.0,
        "f1": f1_score(y, yhat),
        "f2": fbeta_score(y, yhat, beta=2),
        "false_negative_rate": fn / (fn + tp) if (fn + tp) else 0.0,
        "false_positive_rate": fp / (fp + tn) if (fp + tn) else 0.0,
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def ranking_metrics(y, score) -> dict:
    return {"roc_auc": roc_auc_score(y, score), "pr_auc": average_precision_score(y, score)}


def full_report(y, p, threshold: float) -> dict:
    out = {**ranking_metrics(y, p), "brier": brier_score_loss(y, p), "prevalence": float(np.mean(y))}
    out["at_threshold"] = threshold_metrics(y, p, threshold)
    out["at_0_5"] = threshold_metrics(y, p, 0.5)
    return _round(out)


def select_threshold_f2(y, p) -> float:
    """Threshold maximising F2 (recall weighted 2x precision): missing an at-risk person (FN) is
    treated as costlier than an unnecessary follow-up (FP) for a screening-style tool."""
    prec, rec, thr = precision_recall_curve(y, p)
    f2 = 5 * prec * rec / np.clip(4 * prec + rec, 1e-12, None)
    return float(thr[int(np.nanargmax(f2[:-1]))])


def curves(y, p, n_points: int = 101) -> dict:
    fpr, tpr, _ = roc_curve(y, p)
    prec, rec, _ = precision_recall_curve(y, p)
    grid = np.linspace(0, 1, n_points)
    roc = np.interp(grid, fpr, tpr)
    # precision as a function of recall (recall is decreasing in sklearn's output)
    pr = np.interp(grid, rec[::-1], prec[::-1])
    frac_pos, mean_pred = calibration_curve(y, p, n_bins=10, strategy="quantile")
    return {
        "roc": [{"fpr": round(float(x), 3), "tpr": round(float(v), 4)} for x, v in zip(grid, roc)],
        "pr": [{"recall": round(float(x), 3), "precision": round(float(v), 4)} for x, v in zip(grid, pr)],
        "calibration": [
            {"mean_predicted": round(float(m), 4), "observed_rate": round(float(f), 4)}
            for m, f in zip(mean_pred, frac_pos)
        ],
    }


def threshold_table(y, p, thresholds=None) -> list[dict]:
    thresholds = thresholds if thresholds is not None else np.round(np.arange(0.05, 0.65, 0.05), 2)
    return [_round(threshold_metrics(y, p, t)) for t in thresholds]


def bootstrap_ci(y, p, n: int = 200, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    y, p = np.asarray(y), np.asarray(p)
    rocs, prs = [], []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        rocs.append(roc_auc_score(y[idx], p[idx]))
        prs.append(average_precision_score(y[idx], p[idx]))
    q = lambda a: [round(float(np.quantile(a, 0.025)), 4), round(float(np.quantile(a, 0.975)), 4)]  # noqa: E731
    return {"roc_auc_95ci": q(rocs), "pr_auc_95ci": q(prs), "n_bootstrap": n}


def _round(d):
    if isinstance(d, dict):
        return {k: _round(v) for k, v in d.items()}
    if isinstance(d, float | np.floating):
        return round(float(d), 4)
    return d
