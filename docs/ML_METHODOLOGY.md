# ML Methodology — Diabetes / Prediabetes Risk Model

> The model estimates how likely it is that a **2015 US survey respondent** with given answers reported
> prediabetes or diabetes. It is not a diagnostic test and has not been clinically validated.

## 1. Data

| | |
|---|---|
| Dataset | CDC Diabetes Health Indicators, UCI ML Repository id 891 |
| DOI | [10.24432/C53919](https://doi.org/10.24432/C53919) |
| Origin | CDC Behavioral Risk Factor Surveillance System (BRFSS) 2015 telephone survey, cleaned by the dataset authors |
| License | CC BY 4.0 as listed on the UCI page — verify before redistribution |
| Size | 253,680 responses × 21 features, no missing values |
| Target | `Diabetes_binary`: 0 = no diabetes, 1 = prediabetes **or** diabetes (self-reported) |
| Prevalence | 13.93 % |

**Lineage.** `src/ingestion/download.py` fetches the CSV once into `data/raw/` and writes
`PROVENANCE.json` with the URL, timestamp and SHA-256. Raw files are never modified.
`src/preprocessing/validate.py` checks the schema and value domains from the BRFSS data dictionary.
It casts types and writes stratified `train/val/test` CSVs plus `validation_report.json` to
`data/processed/`.

**Data dictionary (as used).** Binary: HighBP, HighChol, CholCheck, Smoker, Stroke,
HeartDiseaseorAttack, PhysActivity, Fruits, Veggies, HvyAlcoholConsump, AnyHealthcare, NoDocbcCost,
DiffWalk, Sex. Ordinal: GenHlth (1–5), Age (13 bands), Education (1–6), Income (1–8).
Continuous: BMI (12–98), MentHlth and PhysHlth (0–30 days).

## 2. Splits and leakage prevention

| Split | Rows | Used for |
|---|---|---|
| train (60 %) | 152,208 | EDA, hyper-parameter search (CV), final fit |
| validation (20 %) | 50,736 | model selection, isotonic calibration, threshold choice |
| test (20 %) | 50,736 | final reporting only, touched once |

* All splits are stratified on the target with a fixed seed (42).
* EDA runs on the training split only.
* All preprocessing is inside an sklearn `Pipeline`, so in every CV fold the imputers, scaler,
  clipping quantiles and one-hot encoder are fitted on that fold's training portion only.
* The model and the threshold are both chosen on validation data, never on test data.

## 3. Preprocessing

```
QuantileClipper(BMI, 0.1%–99.9%)  →  HealthFeatureBuilder  →  ColumnTransformer
                                                                ├─ numeric: median impute → StandardScaler
                                                                ├─ binary:  most-frequent impute
                                                                └─ bmi_category: OneHotEncoder
```

* **Missing values.** None in the source. Imputers are kept for robustness and are fitted in-pipeline.
* **Duplicates.** 24,206 identical feature rows are kept. The features are coarse survey codes, so
  identical answers from different respondents are expected, and dropping them would bias prevalence.
  As a sensitivity check, test performance is also reported on test rows whose feature vector never
  appears in train.
* **Outliers.** BMI has a long right tail (99.9th percentile ≈ 81, max 98), so it is winsorised at
  training quantiles. MentHlth and PhysHlth are zero-inflated day counts: the IQR rule flags valid
  values, so they are left unchanged.
* **Encoding.** Ordinal codes are kept as ordered numbers. The engineered `bmi_category` is one-hot encoded.

## 4. Feature engineering

| Feature | Definition | Why |
|---|---|---|
| `bmi_category` | WHO bands: <18.5, 18.5–25, 25–30, 30–35, 35–40, ≥40 | Prevalence rises non-linearly across bands (5.6 % normal → 34 % obese III in train), which lets linear models capture thresholds |
| `cardiometabolic_count` | HighBP + HighChol + HeartDiseaseorAttack + Stroke | Summarises co-occurring cardiometabolic conditions |
| `lifestyle_score` | PhysActivity + Fruits + Veggies + (1−Smoker) + (1−HvyAlcoholConsump) | Single index of self-reported protective behaviours |
| `poor_health_days` | MentHlth + PhysHlth | Combined recent-wellbeing indicator |
| `access_barrier` | AnyHealthcare = 0 OR NoDocbcCost = 1 | Healthcare-access barrier |

## 5. Models and tuning

| Model | Search | Space (abridged) | Notes |
|---|---|---|---|
| Logistic Regression | Grid | C ∈ {0.01…10} | `class_weight=balanced` |
| Decision Tree | Grid | depth, min_samples_leaf | balanced |
| Random Forest | Randomized (12) | depth, leaf size, max_features | 200 trees, balanced_subsample |
| SVM | Grid | C | Linear SVM + isotonic calibration. RBF kernels scale O(n²) and are impractical at 150k rows |
| KNN | Grid | k ∈ {25, 75, 151}, weights | Final fit on a 40k stratified subsample, to keep inference cost manageable |
| Gradient Boosting | Randomized (12) | lr, leaves, leaf size, L2 | sklearn `HistGradientBoostingClassifier` |
| XGBoost | Randomized (12) | depth, lr, subsample, colsample, min_child_weight, λ | `scale_pos_weight = neg/pos` |

* Search uses **StratifiedKFold(3, shuffle)** on a **50,000-row stratified subsample** of the training split
  (a compute budget choice), scored by **average precision (PR-AUC)**, because accuracy is misleading at
  14 % prevalence. The best configuration is then refit on the full training split.
* **Selection:** highest validation PR-AUC.
* **Calibration:** class weighting distorts probabilities, so every model is wrapped in
  `CalibratedClassifierCV(FrozenEstimator(model), method="isotonic")`, which is fitted on the validation split.
* **Threshold:** maximises F2 on validation (recall weighted twice as heavily as precision). For a
  screening-style tool, a missed at-risk respondent (false negative) is treated as costlier than an
  unnecessary follow-up (false positive). The full threshold/recall/precision trade-off table is
  published, so other operating points can be chosen.

## 6. Evaluation

Every metric below comes from `models/diabetes_risk/<version>/metrics.json`, produced by
`python -m src.training.train` on the untouched test split. Results: see
[§8](#8-results) and the in-app **Predictive Analytics → Model performance** tab.

Metrics: accuracy, precision, recall, specificity, F1, F2, ROC-AUC, PR-AUC, Brier score, confusion
matrix, FNR/FPR, calibration curve, and 95 % bootstrap CIs for ROC-AUC and PR-AUC (200 resamples).

## 7. Explainability and segmentation

* **SHAP.** Tree models use `TreeExplainer`, linear models use `LinearExplainer` (with a background of
  500 training rows), and other models use a permutation explainer. The values explain the
  *uncalibrated* model's output (log-odds for boosted and linear models). Isotonic calibration is
  monotonic, so contribution directions are preserved. One-hot BMI-category columns are summed back
  into one feature. SHAP values describe model behaviour, **not causal effects**.
* **Segmentation.** K-Means on nine standardised indicators (BMI, GenHlth, MentHlth, PhysHlth, Age,
  Income, cardiometabolic_count, lifestyle_score, DiffWalk). k is chosen by the best silhouette score
  (10k-row sample) in k ∈ [3, 6], with the elbow reported for reference, and the result is visualised
  with PCA. The target is **not** used for clustering. Each segment's observed diabetes rate is shown
  for description only, and segments are never labelled as diseases.

## 8. Results

Measured on the held-out test split (50,736 respondents, 13.93 % prevalence). Recall, precision and
specificity are at each model's own validation-selected F2 threshold. Source: `models/diabetes_risk/1.0.0/metrics.json`.

| Model | CV PR-AUC | Val PR-AUC | Test ROC-AUC | Test PR-AUC | Recall | Precision | Specificity |
|---|---|---|---|---|---|---|---|
| **XGBoost (selected)** | 0.439 ± 0.009 | 0.436 | 0.827 | 0.416 | 0.855 | 0.278 | 0.640 |
| Gradient Boosting (HistGB) | 0.436 ± 0.009 | 0.433 | 0.827 | 0.414 | 0.837 | 0.287 | 0.663 |
| Random Forest | 0.432 ± 0.007 | 0.426 | 0.822 | 0.406 | 0.836 | 0.282 | 0.655 |
| Linear SVM (calibrated) | 0.424 ± 0.005 | 0.414 | 0.820 | 0.393 | 0.834 | 0.283 | 0.658 |
| Logistic Regression | 0.423 ± 0.005 | 0.413 | 0.820 | 0.392 | 0.832 | 0.286 | 0.664 |
| K-Nearest Neighbors | 0.417 ± 0.008 | 0.410 | 0.813 | 0.391 | 0.841 | 0.268 | 0.628 |
| Decision Tree | 0.401 ± 0.004 | 0.402 | 0.815 | 0.390 | 0.838 | 0.275 | 0.642 |

**Selected model (XGBoost)** — 95 % bootstrap CI: ROC-AUC [0.822, 0.832], PR-AUC [0.405, 0.429].
Confusion matrix at threshold 0.121: TN 27,930 · FP 15,737 · FN 1,025 · TP 6,044.

**How to read this honestly**

* The seven models are close. The gap between XGBoost and logistic regression (ROC-AUC 0.827 vs 0.820)
  is small relative to the bootstrap CI width, so the choice of XGBoost is a marginal one, not a decisive win.
* The F2 threshold deliberately favours recall: the model catches ~85 % of positive respondents but
  only ~28 % of those flagged are positive (precision), i.e. roughly 2.6 false alarms per true case.
  That is a screening-style trade-off, and the full threshold table is available in the app.
* PR-AUC 0.416 against a 0.139 baseline is a real but modest signal. This is survey data without labs.
* Performance on test rows whose exact feature vector never occurs in training (n = 44,649) is
  ROC-AUC 0.818 / PR-AUC 0.423, so duplicates are not inflating the headline numbers.
* Subgroup fairness (by sex, age, income) has **not** been audited yet.

## 9. Limitations

* Self-reported, cross-sectional survey data from one country and one year (2015).
* The target merges prediabetes and diabetes. Undiagnosed cases appear as negatives (label noise).
* No laboratory measurements (HbA1c, fasting glucose), which are what clinicians use for diagnosis.
* Socio-economic features (income, education) are proxies and may encode structural inequities.
  Subgroup performance has not yet been audited.
* Tuning used a 50k subsample and modest search budgets, so a larger search might find slightly better
  configurations.
