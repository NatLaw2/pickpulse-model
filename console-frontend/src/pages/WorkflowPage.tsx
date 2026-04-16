import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useActiveMode } from '../lib/ActiveModeContext';
import { useDataset } from '../lib/DatasetContext';
import { usePredictions } from '../lib/PredictionContext';
import { api } from '../lib/api';
import type { ProviderInfo, HealthResponse, IntegrationAccount, TrainJobStatus, CrmDataSufficiencyResponse } from '../lib/api';
import { DatasetsPage } from './DatasetsPage';
import { TrainPage } from './TrainPage';
import { formatCurrency } from '../lib/format';
import {
  CheckCircle2, ExternalLink, Loader2, RefreshCw, Play,
  LayoutDashboard, ChevronRight,
  Upload, AlertCircle, Brain, XCircle, Zap,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Brand configs — no external assets, all inline
// ---------------------------------------------------------------------------

const BRAND = {
  hubspot: {
    name: 'HubSpot',
    color: '#FF7A59',
    descColor: 'text-[#FF7A59]',
    borderClass: 'border-[#FF7A59]/30',
    bgClass: 'from-[#FF7A59]/6 to-transparent',
  },
  salesforce: {
    name: 'Salesforce',
    color: '#00A1E0',
    descColor: 'text-[#00A1E0]',
    borderClass: 'border-[#00A1E0]/30',
    bgClass: 'from-[#00A1E0]/6 to-transparent',
  },
} as const;

// ---------------------------------------------------------------------------
// Step badge
// ---------------------------------------------------------------------------

function StepBadge({ n, done }: { n: number; done?: boolean }) {
  if (done) {
    return (
      <div className="w-6 h-6 rounded-full bg-[var(--color-success)]/15 flex items-center justify-center shrink-0">
        <CheckCircle2 size={14} className="text-[var(--color-success)]" />
      </div>
    );
  }
  return (
    <div className="w-6 h-6 rounded-full bg-[var(--color-accent)]/12 flex items-center justify-center shrink-0 text-[11px] font-bold text-[var(--color-accent)]">
      {n}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CRM-native train section — builds dataset from Supabase, trains isolated model
// ---------------------------------------------------------------------------

const POLL_MS = 3000;

function CrmTrainSection({
  mode,
  syncCount,
  onTrainingComplete,
}: {
  mode: 'hubspot' | 'salesforce';
  syncCount: number;
  onTrainingComplete?: () => void;
}) {
  const [sufficiency, setSufficiency] = useState<CrmDataSufficiencyResponse | null>(null);
  const [loadingSufficiency, setLoadingSufficiency] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<TrainJobStatus | null>(null);
  const [error, setError] = useState('');

  // Persists "model was trained" across page navigations (sessionStorage bridge)
  const [alreadyTrained, setAlreadyTrained] = useState<boolean>(() => {
    try { return !!sessionStorage.getItem(`pp_crm_trained_${mode}`); } catch { return false; }
  });

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Re-fetch sufficiency whenever sync completes
  useEffect(() => {
    let cancelled = false;
    setLoadingSufficiency(true);
    setError('');
    api.crmDataSufficiency(mode)
      .then((res) => { if (!cancelled) setSufficiency(res); })
      .catch((e: any) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoadingSufficiency(false); });
    return () => { cancelled = true; };
  }, [mode, syncCount]);

  // Poll training job
  useEffect(() => {
    if (!jobId) return;
    if (jobStatus?.status === 'complete' || jobStatus?.status === 'failed') return;

    const poll = async () => {
      try {
        const status = await api.crmTrainStatus(mode, jobId);
        setJobStatus(status);
        if (status.status === 'complete' || status.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.startsWith('404')) {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setJobId(null);
          setJobStatus(null);
          setError('Training job not found — the server may have restarted. Try again.');
        }
      }
    };

    poll();
    pollRef.current = setInterval(poll, POLL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [jobId, jobStatus?.status, mode]);

  // Persist trained state and notify parent when training finishes
  useEffect(() => {
    if (jobStatus?.status === 'complete') {
      setAlreadyTrained(true);
      try { sessionStorage.setItem(`pp_crm_trained_${mode}`, 'true'); } catch {}
      onTrainingComplete?.();
    }
  }, [jobStatus?.status, mode, onTrainingComplete]);

  const handleTrain = async () => {
    setSubmitting(true);
    setError('');
    setJobId(null);
    setJobStatus(null);
    try {
      const res = await api.crmTrain(mode, 0.2);
      setJobId(res.job_id);
      setJobStatus({
        job_id: res.job_id,
        status: 'pending',
        version_str: null,
        metrics: null,
        error_message: null,
        started_at: null,
        completed_at: null,
      });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const isRunning = jobStatus?.status === 'pending' || jobStatus?.status === 'running';
  const isComplete = jobStatus?.status === 'complete';
  const isFailed = jobStatus?.status === 'failed';

  if (loadingSufficiency) {
    return (
      <p className="text-xs text-[var(--color-text-muted)] flex items-center gap-1.5">
        <Loader2 size={11} className="animate-spin" /> Checking data…
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {/* Simple readiness status */}
      {sufficiency && !jobId && !isComplete && !alreadyTrained && (
        <p className="text-xs text-[var(--color-text-muted)] flex items-center gap-1.5">
          <CheckCircle2 size={11} className="text-[var(--color-success)]" />
          {sufficiency.stats.account_count.toLocaleString()} accounts ready for training
        </p>
      )}

      {/* Cross-session trained badge */}
      {alreadyTrained && !jobId && !isComplete && (
        <p className="text-xs text-[var(--color-success)] flex items-center gap-1.5">
          <CheckCircle2 size={11} />
          Model trained successfully
        </p>
      )}

      {/* Seed failure diagnostic (demo only) */}
      {sufficiency?.seed_warning && (
        <div className="flex items-start gap-2 p-2.5 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">
          <AlertCircle size={13} className="shrink-0 mt-0.5" />
          <span>{sufficiency.seed_warning}</span>
        </div>
      )}

      {/* Train button — never blocked by churn-count sufficiency */}
      <button
        onClick={handleTrain}
        disabled={submitting || isRunning}
        className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
      >
        {submitting || isRunning ? (
          <>
            <Loader2 size={14} className="animate-spin" />
            {submitting ? 'Submitting…' : 'Training…'}
          </>
        ) : (
          <>
            <Brain size={14} />
            {alreadyTrained ? 'Retrain Model' : 'Train Model'}
          </>
        )}
      </button>

      {isRunning && (
        <p className="text-xs text-[var(--color-text-muted)] flex items-center gap-1.5">
          <Loader2 size={11} className="animate-spin" />
          Training in progress — this runs in the background.
        </p>
      )}
      {isComplete && (
        <p className="text-xs text-[var(--color-success)] flex items-center gap-1.5">
          <CheckCircle2 size={11} />
          Training complete
          {jobStatus?.version_str ? ` · ${jobStatus.version_str}` : ''}
          {jobStatus?.metrics?.auc ? ` · AUC ${jobStatus.metrics.auc}` : ''}
        </p>
      )}
      {isFailed && (
        <p className="text-xs text-[var(--color-danger)] flex items-center gap-1.5">
          <XCircle size={11} />
          {jobStatus?.error_message || 'Training failed'}
        </p>
      )}
      {error && <p className="text-xs text-[var(--color-danger)]">{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CRM Workflow (HubSpot or Salesforce — strictly one provider only)
// ---------------------------------------------------------------------------

function CrmWorkflow({ mode }: { mode: 'hubspot' | 'salesforce' }) {
  const brand = BRAND[mode];
  const navigate = useNavigate();
  const { setPredictions } = usePredictions();

  const [provider, setProvider] = useState<ProviderInfo | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [accounts, setAccounts] = useState<IntegrationAccount[]>([]);
  const [syncCount, setSyncCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [scoring, setScoring] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // Track training and scoring completion — persisted across page navigations via sessionStorage
  const [modelTrained, setModelTrained] = useState<boolean>(() => {
    try { return !!sessionStorage.getItem(`pp_crm_trained_${mode}`); } catch { return false; }
  });
  const [scoringDone, setScoringDone] = useState(false);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 5000);
  };

  // loadData declared before handleTrainingComplete so the callback can depend on it.
  const loadData = useCallback(async () => {
    try {
      const intRes = await api.integrations().catch(() => ({ providers: [], connectors: [] }));
      let providerList: ProviderInfo[] = [];

      if (intRes.providers?.length) {
        providerList = intRes.providers;
      } else if (intRes.connectors?.length) {
        providerList = (intRes.connectors as any[]).map((c) => ({
          provider: c.name,
          display_name: c.display_name,
          category: '',
          auth_method: 'api_key' as const,
          icon: 'plug',
          description: '',
          status: c.status,
          enabled: c.enabled,
          connected_at: c.last_synced_at,
          template_status: 'available' as const,
          integration_id: null,
          account_count: c.account_count,
        }));
      }

      // Strictly filter to only the active mode's provider — never show the other
      const activeProvider = providerList.find((p) => p.provider === mode) ?? null;
      setProvider(activeProvider);

      // Always fetch accounts from Supabase — integrationAccounts queries the DB
      // directly (not the CRM API), so it works regardless of OAuth/connection state.
      // This is essential in demo mode where no real CRM connection exists but
      // 2000 synthetic accounts have been loaded into Supabase by trigger_sync.
      const acctRes = await api
        .integrationAccounts(mode)
        .catch(() => ({ accounts: [], total: 0, showing: 0 }));
      setAccounts(acctRes.accounts ?? []);

      if (
        activeProvider &&
        (activeProvider.enabled ||
          activeProvider.status === 'healthy' ||
          activeProvider.status === 'connected')
      ) {
        try {
          const h = await api.integrationHealth(mode);
          setHealth(h);
        } catch {
          /* health check can fail when not yet connected */
        }
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [mode]);

  const handleTrainingComplete = useCallback(() => {
    setModelTrained(true);
    // Refresh accounts + health immediately after training so Score All
    // reflects the latest state without requiring a page navigation.
    loadData();
  }, [loadData]);

  // Detect OAuth return (redirected back from provider)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauthStatus = params.get('oauth');
    const oauthProvider = params.get('provider');
    if (oauthStatus === 'success' && oauthProvider) {
      showToast(`${brand.name} connected successfully! Syncing data…`);
      window.history.replaceState({}, '', window.location.pathname);
    }
    loadData();
  }, [loadData, brand.name]);

  const isConnected =
    health?.connected ||
    (provider?.enabled && provider?.status !== 'not_configured') ||
    false;

  const handleConnect = async () => {
    try {
      // Both HubSpot and Salesforce use OAuth
      const redirectUri = `${window.location.origin}/workflow`;
      const res = await api.startOAuth(mode, redirectUri);
      window.location.href = res.auth_url;
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setError(null);
    try {
      const result = await api.syncIntegration(mode);
      showToast(`Synced ${result.accounts_synced} accounts from ${brand.name}`);
      await loadData();
      setSyncCount((c) => c + 1); // triggers CrmTrainSection to re-fetch sufficiency
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSyncing(false);
    }
  };

  const handleScore = async () => {
    setScoring(true);
    setError(null);
    try {
      const result = await api.triggerScoring(mode);
      setScoringDone(true);
      showToast(
        `Scored ${result.accounts_scored} accounts — ${formatCurrency(result.total_arr_at_risk)} ARR at risk`
      );
      await loadData();
      try {
        const cached = await api.cachedPredictions();
        setPredictions(cached);
      } catch {
        /* non-critical */
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setScoring(false);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm(`Disconnect ${brand.name}? This removes the connection but keeps your synced accounts and predictions.`)) return;
    setDisconnecting(true);
    setError(null);
    try {
      await api.disconnectIntegration(mode);
      await api.setMode('none');
    } catch (e: any) {
      setError(e.message);
      setDisconnecting(false);
      return;
    }
    // Return to WelcomePage — mode is now 'none' on the backend
    navigate('/');
    window.location.reload();
  };

  const lastSync =
    health?.sync_states
      ?.map((s) => s.last_synced_at)
      .filter(Boolean)
      .sort()
      .reverse()[0] ?? null;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-[var(--color-accent)]" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-emerald-50 border border-emerald-200 text-[var(--color-success)] px-4 py-2.5 rounded-xl text-sm flex items-center gap-2 shadow-md">
          <CheckCircle2 size={14} />
          {toast}
        </div>
      )}

      {/* Page header with brand */}
      <div
        className={`mb-6 rounded-2xl p-5 bg-gradient-to-br ${brand.bgClass} border ${brand.borderClass}`}
      >
        <h1 className="text-xl font-bold">{brand.name} Workflow</h1>
        <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
          Connect, sync, train, and score your {brand.name} accounts
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-xl text-sm text-[var(--color-danger)] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle size={14} />
            {error}
          </div>
          <button onClick={() => setError(null)} className="text-xs ml-4 shrink-0">
            Dismiss
          </button>
        </div>
      )}

      <div className="space-y-3">
        {/* ── Step 1: Connect ── */}
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <div className="flex items-center gap-3 mb-3">
            <StepBadge n={1} done={isConnected} />
            <h2 className="text-sm font-semibold">Connect {brand.name}</h2>
            {isConnected && (
              <span className="ml-auto text-[10px] text-[var(--color-success)] font-medium flex items-center gap-1">
                <CheckCircle2 size={11} /> Connected
              </span>
            )}
          </div>

          {!isConnected ? (
            <button
              onClick={handleConnect}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl text-white hover:opacity-90 transition-opacity"
              style={{ background: brand.color }}
            >
              <ExternalLink size={14} />
              Connect {brand.name}
            </button>
          ) : (
            <div className="flex items-center justify-between">
              <p className="text-xs text-[var(--color-text-muted)]">
                {brand.name} is connected.
                {lastSync && (
                  <> Last synced {new Date(lastSync).toLocaleString()}.</>
                )}
              </p>
              <button
                onClick={handleDisconnect}
                disabled={disconnecting}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-red-200 text-red-500 hover:bg-red-50 disabled:opacity-40 transition-colors"
              >
                {disconnecting ? <Loader2 size={11} className="animate-spin" /> : null}
                Disconnect
              </button>
            </div>
          )}
        </div>

        {/* ── Step 2: Sync accounts ── */}
        <div
          className={`bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)] transition-opacity ${
            !isConnected ? 'opacity-40 pointer-events-none' : ''
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <StepBadge n={2} done={(health?.account_count ?? accounts.length) > 0} />
            <h2 className="text-sm font-semibold">Sync Accounts</h2>
            {(health?.account_count ?? accounts.length) > 0 && (
              <span className="ml-auto text-[10px] text-[var(--color-success)] font-medium flex items-center gap-1">
                <CheckCircle2 size={11} /> Accounts synced
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleSync}
              disabled={syncing}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-xl bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] disabled:opacity-40 transition-colors"
            >
              {syncing ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              {syncing ? 'Syncing…' : 'Sync Now'}
            </button>
          </div>
        </div>

        {/* ── Step 3: Train model ── */}
        <div
          className={`bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)] transition-opacity ${
            !isConnected ? 'opacity-40 pointer-events-none' : ''
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <StepBadge n={3} done={modelTrained} />
            <h2 className="text-sm font-semibold">Train Model</h2>
          </div>
          <p className="text-xs text-[var(--color-text-muted)] mb-3">
            Build a prediction model using your synced {brand.name} account data.
          </p>
          <CrmTrainSection mode={mode} syncCount={syncCount} onTrainingComplete={handleTrainingComplete} />
        </div>

        {/* ── Step 4: Score accounts ── */}
        {/* Gate on combined account count: prefer health.account_count (DB total) but fall
            back to accounts.length (the fetched page). Use || not ?? so a literal 0 from
            the health endpoint doesn't override a non-zero accounts array. */}
        <div
          className={`bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)] transition-opacity ${
            (health?.account_count || accounts.length) === 0 ? 'opacity-40 pointer-events-none' : ''
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <StepBadge n={4} done={scoringDone} />
            <h2 className="text-sm font-semibold">Score Accounts</h2>
          </div>

          <div className="space-y-2.5">
            <div className="flex items-center gap-3">
              <button
                onClick={handleScore}
                disabled={scoring || (health?.account_count || accounts.length) === 0}
                className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-xl bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40 transition-opacity"
              >
                {scoring ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Play size={14} />
                )}
                {scoring ? 'Scoring…' : scoringDone ? 'Rescore Accounts' : 'Score All'}
              </button>
            </div>
            {scoringDone && (
              <p className="text-xs text-[var(--color-success)] flex items-center gap-1.5">
                <CheckCircle2 size={11} />
                Scoring complete — accounts are ready to view
              </p>
            )}
          </div>
        </div>

        {/* ── CTAs ── */}
        <div className="flex gap-3 pt-2">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 px-5 py-2.5 bg-[var(--color-accent)] text-white rounded-xl text-sm font-medium hover:opacity-90 transition-opacity"
          >
            <LayoutDashboard size={15} />
            Go to Overview
          </button>
          <button
            onClick={() => navigate('/predict')}
            className="flex items-center gap-2 px-5 py-2.5 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-secondary)] rounded-xl text-sm font-medium hover:text-[var(--color-text-primary)] transition-colors"
          >
            View Accounts
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CSV Workflow
// ---------------------------------------------------------------------------

function CsvWorkflow() {
  const navigate = useNavigate();
  const { dataset } = useDataset();
  const { predictions, setPredictions } = usePredictions();
  const [predicting, setPredicting] = useState(false);
  const [predError, setPredError] = useState('');

  const handlePredict = async () => {
    setPredicting(true);
    setPredError('');
    try {
      const res = await api.predict();
      setPredictions(res);
    } catch (e: any) {
      setPredError(e.message);
    } finally {
      setPredicting(false);
    }
  };

  const existingPredictions = predictions?.predictions?.length ?? 0;

  return (
    <div className="max-w-2xl">
      {/* Page header */}
      <div className="mb-6 rounded-2xl p-5 bg-gradient-to-br from-[var(--color-accent)]/6 to-transparent border border-[var(--color-accent)]/20">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[var(--color-accent)]/12 flex items-center justify-center shrink-0">
            <Upload size={20} className="text-[var(--color-accent)]" />
          </div>
          <div>
            <h1 className="text-xl font-bold">CSV Workflow</h1>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
              Upload your data, train a model, and generate predictions
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {/* ── Step 1: Upload ── */}
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <div className="flex items-center gap-3 mb-4">
            <StepBadge n={1} done={!!dataset} />
            <h2 className="text-sm font-semibold">Upload CSV</h2>
            {dataset && (
              <span className="ml-auto text-[10px] text-[var(--color-text-muted)]">
                {dataset.rows != null ? `${dataset.rows.toLocaleString()} rows` : ''}{' '}
                {dataset.name ? `· ${dataset.name}` : ''}
              </span>
            )}
          </div>
          <DatasetsPage embedded />
        </div>

        {/* ── Step 2: Train ── */}
        <div
          className={`bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)] transition-opacity ${
            !dataset ? 'opacity-40 pointer-events-none' : ''
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <StepBadge n={2} />
            <h2 className="text-sm font-semibold">Train Churn Model</h2>
          </div>
          <TrainPage embedded />
        </div>

        {/* ── Step 3: Generate predictions ── */}
        <div
          className={`bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)] transition-opacity ${
            !dataset ? 'opacity-40 pointer-events-none' : ''
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <StepBadge n={3} done={existingPredictions > 0} />
            <h2 className="text-sm font-semibold">Generate Predictions</h2>
          </div>
          <p className="text-xs text-[var(--color-text-muted)] mb-3">
            {existingPredictions > 0
              ? `${existingPredictions.toLocaleString()} accounts scored. Re-run after retraining to refresh.`
              : 'Score all accounts against the trained model.'}
          </p>
          <button
            onClick={handlePredict}
            disabled={predicting || !dataset}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40 transition-opacity"
          >
            {predicting ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Zap size={14} />
            )}
            {predicting
              ? 'Scoring…'
              : existingPredictions > 0
              ? 'Rescore Accounts'
              : 'Generate Predictions'}
          </button>
          {predError && (
            <p className="mt-2 text-xs text-[var(--color-danger)]">{predError}</p>
          )}
        </div>

        {/* ── CTAs ── */}
        <div className="flex gap-3 pt-2">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 px-5 py-2.5 bg-[var(--color-accent)] text-white rounded-xl text-sm font-medium hover:opacity-90 transition-opacity"
          >
            <LayoutDashboard size={15} />
            Go to Overview
          </button>
          <button
            onClick={() => navigate('/predict')}
            className="flex items-center gap-2 px-5 py-2.5 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-secondary)] rounded-xl text-sm font-medium hover:text-[var(--color-text-primary)] transition-colors"
          >
            View Accounts
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export — routes by active mode, strictly isolated
// ---------------------------------------------------------------------------

export function WorkflowPage() {
  const { mode } = useActiveMode();

  if (mode === 'hubspot') return <CrmWorkflow mode="hubspot" />;
  if (mode === 'salesforce') return <CrmWorkflow mode="salesforce" />;
  if (mode === 'csv') return <CsvWorkflow />;

  // mode === 'none' is gated by AppContent — this branch should not render
  return null;
}
