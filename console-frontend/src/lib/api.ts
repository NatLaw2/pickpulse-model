import { supabase } from './supabase';

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'https://pickpulse-churn-api.onrender.com/api';
const MOD = 'churn';

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data: { session }, error } = await supabase.auth.getSession();
  console.log('[api] getAuthHeaders — session:', !!session, 'token:', session?.access_token ? session.access_token.substring(0, 20) + '...' : 'NONE', 'error:', error?.message ?? 'none');
  if (session?.access_token) {
    return { Authorization: `Bearer ${session.access_token}` };
  }
  return {};
}

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const authHeaders = await getAuthHeaders();
  const hasToken = 'Authorization' in authHeaders;
  console.log(`[api] ${opts?.method ?? 'GET'} ${path} — token attached: ${hasToken}`);

  let res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...authHeaders, ...opts?.headers },
    ...opts,
  });

  console.log(`[api] ${path} — status: ${res.status}`);

  // If 401, try refreshing the session once
  if (res.status === 401) {
    const errBody = await res.clone().text().catch(() => '');
    console.warn(`[api] 401 on ${path} — body: ${errBody}. Attempting refresh...`);
    const { data: { session } } = await supabase.auth.refreshSession();
    console.log('[api] refresh result — session:', !!session, 'token:', session?.access_token ? 'present' : 'NONE');
    if (session?.access_token) {
      res = await fetch(`${BASE}${path}`, {
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
          ...opts?.headers,
        },
        ...opts,
      });
      console.log(`[api] retry ${path} — status: ${res.status}`);
    }
    if (res.status === 401) {
      console.warn('[api] 401 after refresh — session may be invalid');
      throw new Error('Unauthorized');
    }
  }

  if (!res.ok) {
    const body = await res.text();
    console.error(`[api] ${path} error — ${res.status}: ${body}`);
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

  revenueImpact: () =>
    request<RevenueImpactResponse>('/dashboard/revenue-impact'),

  // Modules
  modules: () => request<ModuleInfo[]>('/modules'),
  module: () => request<ModuleDetail>(`/modules/${MOD}`),

  // Datasets
  loadSample: (variant?: string) =>
    request<UploadResponse>(`/datasets/${MOD}/sample${variant ? `?variant=${variant}` : ''}`, { method: 'POST' }),
  uploadDataset: async (file: File) => {
    const form = new FormData();
    form.append('file', file);
    const authHeaders = await getAuthHeaders();
    const res = await fetch(`${BASE}/datasets/${MOD}/upload`, {
      method: 'POST',
      body: form,
      headers: authHeaders,
    });
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
  downloadReport: async () => {
    const authHeaders = await getAuthHeaders();
    const res = await fetch(`${BASE}/evaluate/${MOD}/report`, {
      method: 'POST',
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'churn_risk_report.pdf';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  // Predict
  predict: (limit = 200, includeArchived = false) =>
    request<PredictResponse>(`/predict/${MOD}?limit=${limit}&include_archived=${includeArchived}`, { method: 'POST' }),
  exportPredictions: async () => {
    const authHeaders = await getAuthHeaders();
    const res = await fetch(`${BASE}/predict/${MOD}/export`, {
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'churn_predictions.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  cachedPredictions: () =>
    request<PredictResponse>(`/predict/${MOD}/cached`),

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
  downloadTemplate: async () => {
    const authHeaders = await getAuthHeaders();
    const res = await fetch(`${BASE}/onboarding/template/${MOD}`, {
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'churn_data_template.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  // -----------------------------------------------------------------------
  // Integrations (new platform)
  // -----------------------------------------------------------------------
  integrations: () => request<IntegrationsListResponse>('/integrations'),

  integrationMetadata: (provider: string) =>
    request<ProviderTemplate>(`/integrations/${provider}/metadata`),

  connectIntegration: (provider: string, apiKey: string) =>
    request<ConnectResponse>(
      `/integrations/${provider}/connect?api_key=${encodeURIComponent(apiKey)}`,
      { method: 'POST' },
    ),

  // Legacy alias
  configureIntegration: (name: string, apiKey: string) =>
    request<ConnectResponse>(
      `/integrations/${name}/configure?api_key=${encodeURIComponent(apiKey)}`,
      { method: 'POST' },
    ),

  startOAuth: (provider: string, redirectUri: string) =>
    request<OAuthStartResponse>(
      `/integrations/${provider}/oauth/start?redirect_uri=${encodeURIComponent(redirectUri)}`,
    ),

  disconnectIntegration: (provider: string) =>
    request<{ status: string; provider: string }>(
      `/integrations/${provider}/disconnect`, { method: 'POST' }
    ),

  integrationStatus: (name: string) => request<IntegrationStatusResponse>(`/integrations/${name}/status`),

  syncIntegration: (name: string) => request<SyncResponse>(`/integrations/${name}/sync`, { method: 'POST' }),

  syncStatus: (provider: string) => request<SyncStatusResponse>(`/integrations/${provider}/sync/status`),

  getFieldMappings: (provider: string) =>
    request<FieldMappingsResponse>(`/integrations/${provider}/mappings`),

  updateFieldMappings: (provider: string, mappings: FieldMapping[]) =>
    request<{ provider: string; updated: number }>(
      `/integrations/${provider}/mappings`,
      { method: 'PUT', body: JSON.stringify(mappings) },
    ),

  previewIntegration: (provider: string) =>
    request<PreviewResponse>(`/integrations/${provider}/preview`, { method: 'POST' }),

  integrationHealth: (provider: string) =>
    request<HealthResponse>(`/integrations/${provider}/health`),

  integrationEvents: (provider: string, limit = 50) =>
    request<EventsResponse>(`/integrations/${provider}/events?limit=${limit}`),

  integrationAccounts: (source?: string, limit = 200) =>
    request<IntegrationAccountsResponse>(
      `/integrations/accounts?limit=${limit}${source ? `&source=${source}` : ''}`,
    ),

  triggerScoring: () => request<ScoringResponse>('/integrations/score', { method: 'POST' }),
  latestScores: (limit = 200) => request<LatestScoresResponse>(`/integrations/scores/latest?limit=${limit}`),

  // Run demo: sync + score a connector in one call
  runDemo: (connectorName: string) =>
    request<RunDemoResponse>(`/integrations/${connectorName}/run-demo`, { method: 'POST' }),

  // -----------------------------------------------------------------------
  // AI Outreach Drafts
  // -----------------------------------------------------------------------
  draftOutreachEmail: (req: DraftEmailRequest) =>
    request<DraftEmailResponse>('/outreach/draft-email', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  // -----------------------------------------------------------------------
  // Account Explain + Playbook
  // -----------------------------------------------------------------------
  explainAccount: (customerId: string) =>
    request<ExplainResponse>(`/predictions/${encodeURIComponent(customerId)}/explain`),

  downloadIcs: async (customerId: string) => {
    const authHeaders = await getAuthHeaders();
    const res = await fetch(`${BASE}/predictions/${encodeURIComponent(customerId)}/ics`, {
      headers: { ...authHeaders },
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${customerId}_renewal.ics`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  logPlaybookAction: (customerId: string, actionType: string) =>
    request<{ status: string; action: string }>('/predictions/playbook/log', {
      method: 'POST',
      body: JSON.stringify({ customer_id: customerId, action_type: actionType }),
    }),

  // -----------------------------------------------------------------------
  // Notifications / Executive Summary
  // -----------------------------------------------------------------------
  sendExecutiveSummary: (req: ExecutiveSummaryRequest) =>
    request<ExecutiveSummaryResponse>('/notifications/executive-summary', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  getNotificationSettings: () =>
    request<NotificationSettings>('/notifications/settings'),

  updateNotificationSettings: (recipients: string[]) =>
    request<NotificationSettings>('/notifications/settings', {
      method: 'PUT',
      body: JSON.stringify({ recipients }),
    }),

  // Demo reset
  resetDemo: () =>
    request<DemoResetResponse>('/demo/reset', { method: 'POST' }),
};

// -----------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------

export interface ExecutiveSummaryRequest {
  recipients: string[];
  total_arr_at_risk: number;
  projected_recoverable_arr: number;
  save_rate: number;
  high_risk_in_window: number;
  renewing_90d: number;
  top_accounts: Record<string, unknown>[];
  tier_counts: Record<string, number>;
  risk_drivers: string[];
}

export interface ExecutiveSummaryResponse {
  status: string;
  recipients: string[];
  subject: string;
  html_body: string;
  generated_at: string;
}

export interface NotificationSettings {
  recipients: string[];
}

export interface DemoResetResponse {
  status: string;
  tenant_id: string;
  cleared: string[];
}

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
  recovery_buckets: {
    high_confidence_saves: number;
    medium_confidence_saves: number;
    low_confidence_saves: number;
  };
  top_at_risk: ChurnPrediction[];
  tier_counts: Record<string, number>;
  top_risk_drivers: { feature: string; importance: number }[];
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

export interface DraftEmailRequest {
  customer_id: string;
  customer_name?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  churn_risk_pct: number;
  arr: number;
  arr_at_risk: number;
  days_until_renewal: number;
  recommended_action?: string | null;
  risk_driver_summary?: string | null;
  tier?: string | null;
  tone: 'friendly' | 'direct' | 'executive';
}

export interface DraftEmailResponse {
  subject: string;
  body: string;
  mailto_url: string;
}

export interface ExplainResponse {
  customer_id: string;
  churn_risk_pct: number;
  arr: number;
  arr_at_risk: number;
  days_until_renewal: number;
  renewal_window_label: string;
  tier: string;
  recommended_action: string;
  risk_drivers: string[];
  risk_driver_summary: string;
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

// -----------------------------------------------------------------------
// Integration types (new platform)
// -----------------------------------------------------------------------

export interface ProviderInfo {
  provider: string;
  display_name: string;
  category: string;
  auth_method: 'api_key' | 'oauth' | 'none';
  icon: string;
  description: string;
  status: string;
  enabled: boolean;
  connected_at: string | null;
  template_status: 'available' | 'coming_soon';
  integration_id: string | null;
  account_count: number;
}

export interface IntegrationsListResponse {
  providers?: ProviderInfo[];
  // Legacy fallback
  connectors?: ConnectorInfo[];
}

export interface ProviderTemplate {
  provider: string;
  display_name: string;
  category: string;
  auth_method: string;
  icon: string;
  description: string;
  default_field_map: Record<string, { target: string; transform: string }>;
  supported_resources: string[];
  sample_payload: any;
  status: string;
  oauth_scopes?: string[];
  requires_config?: Record<string, { label: string; placeholder: string; default?: string }>;
}

export interface ConnectResponse {
  status: string;
  connector: string;
  integration_id?: string;
}

export interface OAuthStartResponse {
  auth_url: string;
  state: string;
}

export interface SyncStatusResponse {
  provider: string;
  status: string;
  sync_states: SyncState[];
}

export interface SyncState {
  resource_type: string;
  status: string;
  last_synced_at: string | null;
  records_synced: number;
  error_message: string | null;
}

export interface FieldMapping {
  source_field: string;
  target_field: string;
  transform: string;
  is_default?: boolean;
}

export interface FieldMappingsResponse {
  provider: string;
  mappings: FieldMapping[];
}

export interface PreviewResponse {
  provider: string;
  preview: any[];
  total_available: number;
}

export interface HealthResponse {
  provider: string;
  status: string;
  connected: boolean;
  enabled: boolean;
  account_count: number;
  connected_at: string | null;
  sync_states: SyncState[];
}

export interface IntegrationEvent {
  id: string;
  event_type: string;
  details: any;
  created_at: string;
}

export interface EventsResponse {
  provider: string;
  events: IntegrationEvent[];
}

// Legacy types (kept for backward compat)
export interface ConnectorInfo {
  name: string;
  display_name: string;
  status: 'not_configured' | 'configured' | 'syncing' | 'healthy' | 'error';
  enabled: boolean;
  last_synced_at: string | null;
  account_count: number;
  error_message: string | null;
}

export interface IntegrationStatusResponse {
  name: string;
  status: string;
  enabled: boolean;
  account_count: number;
  last_sync?: any;
}

export interface SyncResponse {
  status: string;
  accounts_synced: number;
  signals_synced: number;
  errors: string[];
  duration_seconds: number;
}

export interface IntegrationAccount {
  id: string;
  external_id: string;
  source: string;
  name: string;
  domain?: string | null;
  email?: string | null;
  arr: number | null;
  mrr?: number | null;
  status?: string | null;
  metadata?: {
    plan?: string | null;
    seats?: number | null;
    industry?: string | null;
    company_size?: string | null;
    [key: string]: unknown;
  };
  created_at: string;
  updated_at: string;
}

export interface IntegrationAccountsResponse {
  accounts: IntegrationAccount[];
  total: number;
  showing: number;
}

export interface ScoringResponse {
  status: string;
  accounts_scored: number;
  tier_counts: Record<string, number>;
  total_arr_at_risk: number;
}

export interface IntegrationScore {
  external_id: string;
  scored_at: string;
  churn_probability: number;
  tier: string;
  arr_at_risk: number | null;
  urgency_score: number | null;
  recommended_action: string | null;
  name?: string;
  email?: string;
  plan?: string;
  arr?: number;
  source?: string;
}

export interface LatestScoresResponse {
  scores: IntegrationScore[];
  count: number;
}

export interface RunDemoResponse {
  status: string;
  connector: string;
  synced_accounts: number;
  synced_signals: number;
  scored_accounts: number;
  tier_counts: Record<string, number>;
  total_arr_at_risk: number;
  sync_errors: string[];
  score_error: string | null;
}

export interface RevenueImpactResponse {
  total_revenue_impact: number;
  confirmed_saves: number;
  risk_reduction: number;
  accounts_impacted: number;
  is_demo: boolean;
  illustrative: boolean;
  label: string;
  subtext: string;
}
