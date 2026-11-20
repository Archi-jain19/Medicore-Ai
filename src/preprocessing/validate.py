"""Data validation and cleaning. Reads data/raw (read-only), writes data/processed.

Usage: python -m src.preprocessing.validate
"""
import json
import logging

import pandas as pd
from sklearn.model_selection import train_test_split

from src.config import DATA_PROCESSED, DATA_RAW, DATASET, ID_COL, RANDOM_STATE, RAW_FEATURES, TARGET, VALUE_DOMAINS

log = logging.getLogger("validate")


class DataValidationError(ValueError):
    pass


def load_raw() -> pd.DataFrame:
    path = DATA_RAW / DATASET["filename"]
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run: python -m src.ingestion.download")
    return pd.read_csv(path)


def validate(df: pd.DataFrame) -> dict:
    """Checks schema and value domains. Raises DataValidationError on hard failures."""
    expected = {ID_COL, TARGET, *RAW_FEATURES}
    missing_cols = expected - set(df.columns)
    if missing_cols:
        raise DataValidationError(f"Missing columns: {sorted(missing_cols)}")
    out_of_domain = {}
    for col, (lo, hi) in VALUE_DOMAINS.items():
        bad = int(((df[col] < lo) | (df[col] > hi)).sum())
        if bad:
            out_of_domain[col] = bad
    non_integer = [c for c in RAW_FEATURES + [TARGET] if not (df[c].dropna() % 1 == 0).all()]
    report = {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "missing_values": {c: int(n) for c, n in df.isna().sum().items() if n},
        "duplicate_ids": int(df[ID_COL].duplicated().sum()),
        "duplicate_feature_rows": int(df[RAW_FEATURES + [TARGET]].duplicated().sum()),
        "out_of_domain": out_of_domain,
        "non_integer_columns": non_integer,
        "target_distribution": {str(k): int(v) for k, v in df[TARGET].value_counts().sort_index().items()},
    }
    if report["duplicate_ids"] or out_of_domain or non_integer:
        raise DataValidationError(json.dumps(report, indent=2))
    return report


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Type casting only. Duplicate feature rows are *retained*: features are coarse survey codes, so
    identical rows are expected from distinct respondents and dropping them would distort prevalence."""
    df = df.copy()
    df[RAW_FEATURES + [TARGET]] = df[RAW_FEATURES + [TARGET]].astype("int64")
    df["BMI"] = df["BMI"].astype("float64")
    return df


def split(df: pd.DataFrame):
    """60/20/20 stratified split: fit / validation (calibration + threshold + model selection) / test."""
    train_full, test = train_test_split(df, test_size=0.20, stratify=df[TARGET], random_state=RANDOM_STATE)
    fit, val = train_test_split(train_full, test_size=0.25, stratify=train_full[TARGET], random_state=RANDOM_STATE)
    return fit, val, test


def run():
    df = load_raw()
    report = validate(df)
    df = clean(df)
    fit, val, test = split(df)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    for name, part in (("train", fit), ("val", val), ("test", test)):
        part.to_csv(DATA_PROCESSED / f"{name}.csv", index=False)
    report["splits"] = {
        n: {"rows": len(p), "positive_rate": round(float(p[TARGET].mean()), 4)}
        for n, p in (("train", fit), ("val", val), ("test", test))
    }
    (DATA_PROCESSED / "validation_report.json").write_text(json.dumps(report, indent=2))
    log.info("Validation passed: %s", json.dumps(report["splits"]))
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
