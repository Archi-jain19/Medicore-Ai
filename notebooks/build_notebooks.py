"""Generates the four analysis notebooks from the src/ pipeline modules, so notebooks and production
code cannot drift apart. Execute afterwards with:

    jupyter nbconvert --to notebook --execute --inplace notebooks/0*.ipynb

Usage: python notebooks/build_notebooks.py
"""
from pathlib import Path

import nbformat as nbf

HERE = Path(__file__).parent
SETUP = """import sys, json
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()
sys.path.insert(0, str(ROOT))
import pandas as pd, numpy as np
import matplotlib.pyplot as plt
from IPython.display import Image, display
pd.set_option('display.max_columns', 40)"""


def nb(cells):
    book = nbf.v4.new_notebook()
    book.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    book.cells = [nbf.v4.new_markdown_cell(c[3:]) if c.startswith("md:") else nbf.v4.new_code_cell(c) for c in cells]
    return book


NOTEBOOKS = {
    "01_data_exploration.ipynb": [
        "md:# 01 · Data exploration\n\nDataset: **UCI CDC Diabetes Health Indicators** (id 891, DOI 10.24432/C53919), derived from "
        "the CDC BRFSS 2015 telephone survey. 253,680 responses, 21 features, binary target `Diabetes_binary` "
        "(0 = no diabetes, 1 = prediabetes or diabetes, self-reported).\n\nEDA is run on the **training split only** "
        "so that no information from the test split influences modelling decisions.",
        SETUP,
        "from src.config import DATA_RAW, DATA_PROCESSED\nprint(json.dumps(json.loads((DATA_RAW/'PROVENANCE.json').read_text()), indent=2))",
        "raw = pd.read_csv(DATA_RAW/'cdc_diabetes_health_indicators.csv')\nprint(raw.shape)\nraw.head()",
        "raw.dtypes.value_counts(), raw.isna().sum().sum()",
        "md:## Validation report\nSchema, value domains (from the BRFSS data dictionary), duplicates and class balance.",
        "print(json.dumps(json.loads((DATA_PROCESSED/'validation_report.json').read_text()), indent=2))",
        "md:## EDA (training split)",
        "from src.evaluation import eda\nreport = eda.run()\npd.DataFrame(report['describe']).T",
        "pd.Series(report['class_distribution'])",
        "for f in ['class_distribution','univariate','outliers','prevalence_by_feature','bmi_by_class','correlation']:\n"
        "    display(Image(filename=str(ROOT/'docs'/'figures'/f'eda_{f}.png')))",
        "pd.DataFrame(report['outliers_iqr']).T",
        "md:`MentHlth` / `PhysHlth` are zero-inflated day counts (0–30), so the IQR rule flags many valid values. They are "
        "kept unchanged. BMI has a long right tail (max 98), so it is winsorised at training-set quantiles inside the pipeline.",
        "assoc = pd.DataFrame(report['association_with_target']).T\nassoc[['test','p_value','cramers_v','rank_biserial']].sort_values('p_value')",
        "pd.Series(report['prevalence_by_bmi_category'])",
        "md:**Observations.** Self-rated general health, high blood pressure, BMI, walking difficulty, high cholesterol and age "
        "have the strongest associations with the target. Prevalence rises monotonically across BMI bands, which motivates "
        "the engineered `bmi_category` feature. Education and income are moderately correlated (ρ≈0.45), as are general "
        "health and physical-health days. With n≈150k almost every p-value is tiny, so the effect sizes matter more.",
    ],
    "02_preprocessing.ipynb": [
        "md:# 02 · Preprocessing & feature engineering\n\nAll transformations live in an sklearn `Pipeline`, so every CV fold "
        "fits imputers, scalers and clipping bounds on its own training portion only (no leakage).",
        SETUP,
        "from src.config import RAW_FEATURES, TARGET, DATA_PROCESSED\nfrom src.preprocessing.pipeline import build_preprocessor\n"
        "train = pd.read_csv(DATA_PROCESSED/'train.csv')\nX, y = train[RAW_FEATURES], train[TARGET]\nX.shape",
        "md:## Splits\nStratified 60/20/20: **train** (tuning + fit), **validation** (model selection, isotonic calibration, "
        "threshold), **test** (reported once).",
        "pd.DataFrame(json.loads((DATA_PROCESSED/'validation_report.json').read_text())['splits']).T",
        "md:## Duplicates\n24,206 feature rows are exact duplicates. Features are coarse survey codes, so identical rows are "
        "expected from distinct respondents, and dropping them would distort prevalence. They are **kept**. The training "
        "report measures test performance on rows whose feature vector never appears in train as a sensitivity check.",
        "pre = build_preprocessor().fit(X)\npre",
        "names = pre.get_feature_names_out()\nZ = pre.transform(X.head(5))\npd.DataFrame(Z, columns=names)",
        "print('Learned BMI clip bounds:', pre.named_steps['clip'].bounds_)",
        "md:## Engineered features\n| Feature | Definition | Rationale |\n|---|---|---|\n"
        "| `bmi_category` | WHO adult BMI bands (one-hot) | Non-linear BMI risk; interpretable |\n"
        "| `cardiometabolic_count` | HighBP + HighChol + HeartDisease + Stroke | Co-occurring conditions summarised |\n"
        "| `lifestyle_score` | PhysActivity + Fruits + Veggies + (1−Smoker) + (1−HvyAlcohol) | Protective behaviours |\n"
        "| `poor_health_days` | MentHlth + PhysHlth | Recent wellbeing |\n"
        "| `access_barrier` | No coverage OR cost barrier | Healthcare access |",
        "from src.feature_engineering.features import HealthFeatureBuilder\nfe = HealthFeatureBuilder().fit_transform(train)\n"
        "fe.groupby('cardiometabolic_count')[TARGET].agg(['mean','size'])",
        "fe.groupby('lifestyle_score')[TARGET].agg(['mean','size'])",
    ],
    "03_model_training.ipynb": [
        "md:# 03 · Model training & tuning\n\nThe full run is `python -m src.training.train`. This notebook loads its "
        "persisted outputs rather than retraining.\n\n* Hyper-parameter search: Grid (LR, DT, SVM, KNN) or Randomized (RF, "
        "HistGB, XGBoost), **StratifiedKFold(3)** on a 50k stratified subsample of the training split, scored by "
        "**average precision (PR-AUC)**, not accuracy.\n* Class imbalance: `class_weight='balanced'` / `scale_pos_weight`.\n"
        "* Final refit on the full training split (KNN capped at 40k rows for inference cost; SVM is a calibrated linear SVM "
        "because kernel SVMs do not scale to 150k rows).",
        SETUP,
        "from src.config import MODELS_DIR\nreg = json.loads((MODELS_DIR/'registry.json').read_text())\n"
        "m = json.loads((MODELS_DIR/reg['diabetes_risk']['path']/'metrics.json').read_text())\nprint(m['tuning'])",
        "pd.DataFrame({k: {'best_params': v['best_params'], 'cv_pr_auc': f\"{v['cv_pr_auc_mean']:.4f} ± {v['cv_pr_auc_std']:.4f}\", "
        "'train_rows': v['train_rows'], 'seconds': v['train_seconds']} for k, v in m['models'].items()}).T",
        "md:Model selection uses **validation PR-AUC**. The test split is never used to choose a model or a threshold.",
        "pd.Series({k: v['validation']['pr_auc'] for k, v in m['models'].items()}).sort_values(ascending=False)",
        "print('Selected:', m['selected_model'])",
    ],
    "04_model_evaluation.ipynb": [
        "md:# 04 · Model evaluation & explainability",
        SETUP,
        "from src.config import MODELS_DIR\nreg = json.loads((MODELS_DIR/'registry.json').read_text())\nd = MODELS_DIR/reg['diabetes_risk']['path']\n"
        "m = json.loads((d/'metrics.json').read_text())",
        "rows = {}\nfor k, v in m['models'].items():\n    t = v['test']; a = t['at_threshold']\n"
        "    rows[v['display_name']] = {'ROC-AUC': t['roc_auc'], 'PR-AUC': t['pr_auc'], 'Brier': t['brier'], 'threshold': a['threshold'],\n"
        "        'recall': a['recall'], 'precision': a['precision'], 'specificity': a['specificity'], 'F1': a['f1'], 'F2': a['f2'],\n"
        "        'FN': a['confusion_matrix']['fn'], 'FP': a['confusion_matrix']['fp'], 'accuracy@0.5': t['at_0_5']['accuracy']}\n"
        "pd.DataFrame(rows).T.sort_values('PR-AUC', ascending=False).round(4)",
        "md:Accuracy at 0.5 looks high for every model only because 86% of respondents are negative. A model that always "
        "predicts 'no diabetes' would score 0.86. PR-AUC, recall and the FN/FP counts are the informative metrics here.",
        "sel = m['selected']\nprint(json.dumps(sel['bootstrap_test'], indent=2)); print(json.dumps(sel['duplicate_sensitivity'], indent=2))",
        "c = sel['curves_test']\nfig, ax = plt.subplots(1, 3, figsize=(14, 4))\n"
        "r = pd.DataFrame(c['roc']); ax[0].plot(r.fpr, r.tpr); ax[0].plot([0,1],[0,1],'--',c='grey'); ax[0].set(title='ROC', xlabel='FPR', ylabel='TPR')\n"
        "p = pd.DataFrame(c['pr']); ax[1].plot(p.recall, p.precision); ax[1].axhline(m['splits']['test']['positive_rate'], ls='--', c='grey'); ax[1].set(title='Precision-recall', xlabel='Recall')\n"
        "k = pd.DataFrame(c['calibration']); ax[2].plot(k.mean_predicted, k.observed_rate, 'o-'); ax[2].plot([0,k.mean_predicted.max()],[0,k.mean_predicted.max()],'--',c='grey'); ax[2].set(title='Calibration', xlabel='Predicted')\n"
        "plt.tight_layout()",
        "pd.DataFrame(sel['threshold_table_val']).drop(columns='confusion_matrix').round(3)",
        "md:## Explainability (SHAP)\nGlobal importance on 2,000 held-out test respondents. SHAP values describe the model's "
        "behaviour. They are **not causal effects**.",
        "from src.evaluation import explain_global\ns = explain_global.run()\n"
        "pd.DataFrame([{k: f[k] for k in ('label','mean_abs_shap','mean_shap')} for f in s['features']])",
        "display(Image(filename=str(ROOT/'docs'/'figures'/'shap_summary.png')))",
        "md:## Segmentation",
        "from src.segmentation import cluster\nseg = cluster.run()\npd.DataFrame(seg['selection'])",
        "display(Image(filename=str(ROOT/'docs'/'figures'/'segmentation.png')))",
        "pd.DataFrame([{**{'segment': s['name'], 'share': s['share'], 'diabetes_rate': s['observed_diabetes_rate']}, **s['feature_means']} for s in seg['segments']])",
    ],
}

if __name__ == "__main__":
    for name, cells in NOTEBOOKS.items():
        nbf.write(nb(cells), HERE / name)
        print("wrote", name)
