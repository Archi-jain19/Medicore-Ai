export interface User {
  id: number
  email: string
  full_name: string | null
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export type RiskBand = 'lower' | 'elevated' | 'high'

export interface Contribution {
  feature: string
  label: string
  value: number | string | null
  shap_value: number
  direction: 'increases' | 'decreases' | 'neutral'
  plain_label?: string | null
  plain_value?: string | null
}

export interface PatientInput {
  HighBP: 0 | 1
  HighChol: 0 | 1
  CholCheck: 0 | 1
  BMI: number
  Smoker: 0 | 1
  Stroke: 0 | 1
  HeartDiseaseorAttack: 0 | 1
  PhysActivity: 0 | 1
  Fruits: 0 | 1
  Veggies: 0 | 1
  HvyAlcoholConsump: 0 | 1
  AnyHealthcare: 0 | 1
  NoDocbcCost: 0 | 1
  GenHlth: number
  MentHlth: number
  PhysHlth: number
  DiffWalk: 0 | 1
  Sex: 0 | 1
  Age: number
  Education: number
  Income: number
}

export interface PredictionResult {
  id: number
  predicted_class: number
  predicted_label: string
  headline: string
  chance_text: string
  next_step: string
  probability: number
  threshold: number
  risk_band: RiskBand
  population_base_rate: number
  model_name: string
  model_version: string
  algorithm: string
  top_contributions: Contribution[]
  explanation: string
  limitations: string[]
  created_at: string
}

export interface ExplanationResult {
  probability: number
  base_value: number
  output_space: string
  contributions: Contribution[]
  explanation: string
  note: string
}

export interface PredictionHistoryItem {
  id: number
  probability: number
  predicted_class: number
  risk_band: RiskBand
  threshold: number
  created_at: string
  inputs: PatientInput
}

export interface ThresholdMetrics {
  threshold: number
  accuracy: number
  precision: number
  recall: number
  specificity: number
  f1: number
  f2: number
  false_negative_rate: number
  false_positive_rate: number
  confusion_matrix: { tn: number; fp: number; fn: number; tp: number }
}

export interface ModelResult {
  display_name: string
  best_params: Record<string, unknown>
  cv_pr_auc_mean: number
  cv_pr_auc_std: number
  train_rows: number
  train_seconds: number
  inference_ms_per_row: number
  validation: { roc_auc: number; pr_auc: number; selected_threshold: number }
  test: {
    roc_auc: number
    pr_auc: number
    brier: number
    prevalence: number
    at_threshold: ThresholdMetrics
    at_0_5: ThresholdMetrics
  }
}

export interface ModelPerformance {
  selected_model: string
  selection_criterion: string
  threshold_policy: string
  plain_summary: string
  tuning: { rows: number; cv: string; scoring: string; quick_mode: boolean }
  splits: Record<string, { rows: number; positive_rate: number }>
  models: Record<string, ModelResult>
  selected: {
    curves_test: {
      roc: { fpr: number; tpr: number }[]
      pr: { recall: number; precision: number }[]
      calibration: { mean_predicted: number; observed_rate: number }[]
    }
    threshold_table_val: ThresholdMetrics[]
    bootstrap_test: { roc_auc_95ci: [number, number]; pr_auc_95ci: [number, number]; n_bootstrap: number }
    duplicate_sensitivity: Record<string, number>
  }
}

export interface ShapGlobal {
  n_samples: number
  base_value: number
  output_space: string
  algorithm: string
  note: string
  features: {
    feature: string
    label: string
    plain_label: string
    mean_abs_shap: number
    mean_shap: number
    points: { shap: number; value_pct: number | null }[]
  }[]
}

export interface ClusterResult {
  algorithm: string
  features: string[]
  n_rows: number
  selection: { k: number; inertia: number; silhouette: number; davies_bouldin: number; calinski_harabasz: number }[]
  elbow_k: number
  chosen_k: number
  choice_rule: string
  final_silhouette_sample: number
  pca_explained_variance: number[]
  segments: {
    id: number
    name: string
    size: number
    share: number
    feature_means: Record<string, number>
    observed_diabetes_rate: number
    description: string[]
  }[]
  pca_points: { x: number; y: number; segment: number }[]
  note: string
}

export interface DashboardSummary {
  user: { email: string; full_name: string | null }
  counts: { reports: number; conversations: number; predictions: number; active_reminders: number }
  my_risk_distribution: { band: RiskBand; count: number }[]
  my_prediction_trend: { id: number; created_at: string; probability: number; risk_band: RiskBand }[]
  recent_activity: { id: number; action: string; label: string; created_at: string }[]
}

export interface PopulationAnalytics {
  source: string
  n_respondents: number
  prevalence: number
  prevalence_by_age: { level: number; rate: number }[]
  prevalence_by_genhlth: { level: number; rate: number }[]
  prevalence_by_bmi_category: { category: string; rate: number }[]
  top_associations: { feature: string; spearman: number }[]
  segments: { name: string; share: number; observed_diabetes_rate: number }[]
  model: {
    algorithm: string
    version: string
    test_roc_auc: number
    test_pr_auc: number
    test_recall: number
    test_precision: number
    threshold: number
  }
}

// ---------------------------------------------------------------- Assistant / RAG
export interface SourceDoc {
  rank: number
  chunk_id: string
  doc_id: string
  title: string
  source: string
  doc_type: string
  url: string
  published: string | null
  snippet: string
  relevance: number
  score_breakdown: { similarity: number; source_reliability: number; recency: number; clinical_relevance: number }
}

export interface ClaimCheck {
  text: string
  status: 'supported' | 'weak' | 'unsupported'
  similarity: number
  best_chunk_id: string | null
  cited: number[]
  issues: string[]
}

export interface Verification {
  claims: ClaimCheck[]
  supported_ratio: number | null
  flagged: number
  weak?: number
  method: string
  note: string
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  sources: SourceDoc[] | null
  verification: Verification | null
  retrieval_strategy: string | null
  created_at: string
  // present only on the live response, not persisted
  status?: ChatStatus
  emergency_notice?: string | null
  notes?: string[]
  analysis?: ChatAnalysis | null
}

export type ChatStatus =
  | 'ok'
  | 'extractive'
  | 'limited_evidence'
  | 'needs_more_info'
  | 'insufficient_evidence'
  | 'generation_unavailable'
  | 'knowledge_base_missing'

export interface ChatAnalysis {
  intent: string
  complexity: 'simple' | 'complex'
  complexity_score: number
  complexity_reasons: string[]
  safety_flags: string[]
  queries: string[]
}

export interface ChatResponse {
  conversation_id: number
  title: string
  user_message: ChatMessage
  reply: ChatMessage
  status: ChatStatus
  emergency_notice: string | null
  analysis: ChatAnalysis | null
  notes: string[]
  disclaimer: string
}

export interface Conversation {
  id: number
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[]
}

export interface RagStatus {
  knowledge_base_built: boolean
  generation_configured: boolean
  generation_model: string | null
  embedding_model: string
  chunks: number
  documents_by_source: Record<string, number>
  built_at: string | null
}

// ---------------------------------------------------------------- Reports
export type LabFlag = 'low' | 'high' | 'normal' | 'unknown'

export interface LabResult {
  id: number
  parameter: string
  printed_name: string | null
  value_text: string
  value_numeric: number | null
  unit: string | null
  ref_low: number | null
  ref_high: number | null
  ref_text: string | null
  flag: LabFlag
  flag_source: 'reference_range' | 'lab_flag' | 'none'
  explanation: {
    what_it_measures: string | null
    status: string
    context: string | null
    learn_more: { title: string; url: string; source: string; published: string | null } | null
  }
}

export interface ReportListItem {
  id: number
  original_filename: string
  mime_type: string
  size_bytes: number
  extraction_method: 'text' | 'ocr' | null
  page_count: number | null
  status: 'processed' | 'no_results'
  created_at: string
  result_count: number
  flagged_count: number
}

export interface ReportDetail extends ReportListItem {
  summary: string | null
  sha256: string
  results: LabResult[]
  disclaimer: string
}

// ---------------------------------------------------------------- Locator
export type PlaceCategory = 'hospital' | 'pharmacy' | 'clinic'

export interface Place {
  id: string
  name: string
  kind: PlaceCategory
  lat: number
  lon: number
  distance_m: number
  address: string | null
  phone: string | null
  website: string | null
  opening_hours: string | null
  emergency: string | null
  osm_url: string
  directions_url: string
}

export interface LocationsResponse {
  center: { lat: number; lon: number }
  category: PlaceCategory
  radius_m: number
  count: number
  places: Place[]
  attribution: string
  provider: 'overpass' | 'nominatim'
  note: string | null
  place: { lat: number; lon: number; display_name: string } | null
}

// ---------------------------------------------------------------- Reminders
export type Frequency = 'daily' | 'every_other_day' | 'weekly' | 'as_needed'

export interface Reminder {
  id: number
  medication_name: string
  dosage_note: string | null
  frequency: Frequency
  times: string[]
  days_of_week: number[] | null
  start_date: string
  end_date: string | null
  is_active: boolean
  status: 'active' | 'paused' | 'ended' | 'scheduled'
  created_at: string
  updated_at: string
}

export interface Dose {
  reminder_id: number
  medication_name: string
  dosage_note: string | null
  scheduled_date: string
  scheduled_time: string
  status: 'taken' | 'skipped' | 'pending'
  event_id: number | null
}

export interface DoseEvent {
  id: number
  reminder_id: number
  medication_name: string
  scheduled_date: string
  scheduled_time: string
  status: 'taken' | 'skipped' | 'missed'
  logged_at: string
}

// ---------------------------------------------------------------- Settings
export interface Profile {
  email: string
  full_name: string | null
  notify_reminders: boolean
  data_retention_days: number | null
  created_at: string
}
