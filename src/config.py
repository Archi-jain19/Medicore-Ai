"""Shared paths and dataset constants for the offline pipelines."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
MODELS_DIR = ROOT / "models"
FIGURES_DIR = ROOT / "docs" / "figures"

RANDOM_STATE = 42

DATASET = {
    "name": "CDC Diabetes Health Indicators",
    "uci_id": 891,
    "doi": "10.24432/C53919",
    "url": "https://archive.ics.uci.edu/dataset/891/cdc+diabetes+health+indicators",
    "data_url": "https://archive.ics.uci.edu/static/public/891/data.csv",
    "metadata_api": "https://archive.ics.uci.edu/api/dataset?id=891",
    "license": "CC BY 4.0 (as listed on the UCI repository page — verify before redistribution)",
    "origin": "Derived from the CDC Behavioral Risk Factor Surveillance System (BRFSS) 2015 telephone survey",
    "filename": "cdc_diabetes_health_indicators.csv",
}

TARGET = "Diabetes_binary"
ID_COL = "ID"

BINARY_FEATURES = [
    "HighBP", "HighChol", "CholCheck", "Smoker", "Stroke", "HeartDiseaseorAttack",
    "PhysActivity", "Fruits", "Veggies", "HvyAlcoholConsump", "AnyHealthcare",
    "NoDocbcCost", "DiffWalk", "Sex",
]
ORDINAL_FEATURES = ["GenHlth", "Age", "Education", "Income"]
CONTINUOUS_FEATURES = ["BMI", "MentHlth", "PhysHlth"]
RAW_FEATURES = BINARY_FEATURES + ORDINAL_FEATURES + CONTINUOUS_FEATURES

# Valid value domains from the UCI / BRFSS data dictionary
VALUE_DOMAINS = {
    **{c: (0, 1) for c in BINARY_FEATURES},
    "GenHlth": (1, 5),
    "Age": (1, 13),
    "Education": (1, 6),
    "Income": (1, 8),
    "BMI": (12, 98),
    "MentHlth": (0, 30),
    "PhysHlth": (0, 30),
    TARGET: (0, 1),
}
