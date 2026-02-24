const BASE = '/api';
const MOD = 'churn';

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

/**
 * Check whether an API error is a "no dataset loaded" empty-state (not a real error).
 */
export function isNoDatasetError(msg: string): boolean {
  return /no dataset loaded/i.test(msg);
}

/**
 * Check whether an API error is a "no trained model" empty-state.
 */
export function isNoModelError(msg: string): boolean {
  return /no trained model|train first|train a model/i.test(msg);
}

export const api = {
  // Dashboard
  dashboard: (saveRate?: number) =>
    request<DashboardResponse>(`/dashboard${saveRate != null ? `?save_rate=${saveRate}` : ''}`),

  // Modules
  modules: () => request<ModuleInfo[]>('/modules'),
  module: () => request<ModuleDetail>(`/modules/${MOD}`),

  // Datasets
  loadSample: () => request<UploadResponse>(`/datasets/${MOD}/sample`, { method: 'POST' }),
  uploadDataset: async (file: File) => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${BASE}/datasets/${MOD}/upload`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    return res.json() as Promise<UploadResponse>;
  },
  validate: () => request<ValidationInfo>(`/datasets/${MOD}/validate`),
  currentDataset: () => request<DatasetInfo>(`/datasets/${MOD}/current`),

  // Train
  train: (valFrac = 0.2) =>
    request<TrainResponse>(`/train/${MOD}?val_frac=${valFrac}`, { method: 'POST' }),

  // Evaluate
  evaluate: () => request<EvalMetrics>(`/evaluate/${MOD}`),
  downloadReport: () => `${BASE}/evaluate/${MOD}/report`,

  // Predict
  predict: (limit = 200, includeArchived = false) =>
    request<PredictResponse>(`/predict/${MOD}?limit=${limit}&include_archived=${includeArchived}`, { method: 'POST' }),
  exportPredictions: () => `${BASE}/predict/${MOD}/export`,

  // Account status
  updateAccountStatus: (customerId: string, status: string) =>
    request<{ customer_id: string; status: string }>(
      `/accounts/${customerId}/status?status=${status}`, { method: 'POST' }
    ),

  // API docs
  apiDocs: () => request<ApiDocsResponse>('/api-docs'),

  // Onboarding
  onboarding: () => request<OnboardingResponse>('/onboarding'),
  completeStep: (id: string) =>
    request<{ step_id: string; status: string }>(`/onboarding/${id}/complete`, { method: 'POST' }),
  resetStep: (id: string) =>
    request<{ step_id: string; status: string }>(`/onboarding/${id}/reset`, { method: 'POST' }),
  downloadTemplate: () => `${BASE}/onboarding/template/${MOD}`,
};

// Types
export interface DashboardResponse {
  module: DashboardModule;
  dataset: DatasetInfo | null;
  kpis: {
    total_arr_at_risk: number;
    projected_recoverable_arr: number;
    assumed_save_rate: number;
    renewing_90d: number;
    high_risk_in_window: number;
  };
  top_at_risk: ChurnPrediction[];
}

export interface DashboardModule {
  name: string;
  display_name: string;
  has_model: boolean;
  has_dataset: boolean;
  trained_at: string | null;
  version: string | null;
  auc: number | null;
  calibration_error: number | null;
  lift_at_top10: number | null;
  n_train: number | null;
}

export interface ModuleInfo {
  name: string;
  display_name: string;
  has_model: boolean;
  has_dataset: boolean;
  metadata: any;
  required_columns: string[];
  optional_columns: string[];
  tiers: { high: string; medium: string; low: string };
}

export interface ModuleDetail extends ModuleInfo {
  dataset_info: DatasetInfo | null;
  metrics: EvalMetrics | null;
}

export interface DatasetInfo {
  path: string;
  name: string;
  rows: number;
  columns: number;
  is_demo: boolean;
  loaded_at: string;
}

export interface ValidationInfo {
  valid: boolean;
  module: string;
  n_rows: number;
  n_columns: number;
  missing_required: string[];
  warnings: string[];
  errors: string[];
  label_distribution: Record<string, number>;
  columns: ColumnInfo[];
}

export interface ColumnInfo {
  name: string;
  dtype: string;
  missing_count: number;
  missing_pct: number;
  n_unique: number;
  sample_values: string[];
}

export interface UploadResponse {
  status: string;
  validation: ValidationInfo;
  dataset_info: DatasetInfo;
}

export interface TrainResponse {
  status: string;
  metadata: any;
  metrics: EvalMetrics | null;
}

export interface EvalMetrics {
  module?: string;
  n: number;
  base_rate?: number;
  auc: number | null;
  pr_auc: number | null;
  brier: number;
  logloss: number;
  calibration_error?: number;
  accuracy?: number;
  precision?: number;
  recall?: number;
  f1?: number;
  threshold?: number;
  confusion_matrix?: number[][];
  calibration_bins?: CalibrationBin[];
  lift_table?: LiftRow[];
  lift_at_top10?: number;
  capture_at_top10?: number;
  tier_breakdown?: Record<string, TierInfo>;
  business_impact?: BusinessImpact;
  feature_importance?: FeatureImportance[];
}

export interface CalibrationBin {
  bin_lo: number;
  bin_hi: number;
  n: number;
  predicted_avg: number;
  actual_rate: number;
  delta?: number;
}

export interface LiftRow {
  decile: number;
  n: number;
  avg_prob: number;
  actual_rate: number;
  lift: number;
  cumulative_capture: number;
}

export interface TierInfo {
  count: number;
  actual_rate: number;
  avg_probability: number;
  total_value?: number;
  value_at_risk?: number;
}

export interface BusinessImpact {
  total_value: number;
  value_in_top_decile: number;
  arr_at_risk_top_decile?: number;
  total_arr_at_risk?: number;
  positives_in_top_decile: number;
  total_positives: number;
}

export interface FeatureImportance {
  feature: string;
  importance: number;
}

export interface ChurnPrediction {
  customer_id: string;
  churn_risk_pct: number;
  urgency_score: number;
  renewal_window_label: string;
  days_until_renewal: number;
  auto_renew_flag: number;
  arr: number;
  arr_at_risk: number;
  recommended_action: string;
  tier: string;
  rank: number;
}

export interface PredictResponse {
  predictions: ChurnPrediction[];
  total: number;
  showing: number;
  active_count: number;
  archived_count: number;
  tier_counts: Record<string, number>;
  summary: {
    total_arr_at_risk?: number;
    renewing_90d?: number;
    high_risk_in_window?: number;
  };
}

export interface ApiDocsResponse {
  base_url: string;
  endpoints: ApiEndpoint[];
}

export interface ApiEndpoint {
  method: string;
  path: string;
  description: string;
  curl?: string;
  request_body?: any;
  response_example?: any;
}

export interface OnboardingResponse {
  steps: OnboardingStep[];
}

export interface OnboardingStep {
  id: string;
  label: string;
  description: string;
  status: 'pending' | 'complete';
}
