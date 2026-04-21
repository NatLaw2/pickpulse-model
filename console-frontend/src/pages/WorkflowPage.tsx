import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useActiveMode } from '../lib/ActiveModeContext';
import { useDataset } from '../lib/DatasetContext';
import { usePredictions } from '../lib/PredictionContext';
import { api } from '../lib/api';
import type {
  ProviderInfo, HealthResponse, IntegrationAccount,
  TrainJobStatus, ScoringResponse, SyncResponse,
} from '../lib/api';
import { DatasetsPage } from './DatasetsPage';
import { formatCurrency } from '../lib/format';
import {
  CheckCircle2, ExternalLink, Loader2, RefreshCw,
  LayoutDashboard, ChevronRight, Upload, AlertCircle, Brain, XCircle,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Brand configs
// ---------------------------------------------------------------------------

const BRAND = {
  hubspot: {
    name: 'HubSpot',
    color: '#FF7A59',
    borderClass: 'border-[#FF7A59]/30',
    bgClass: 'from-[#FF7A59]/6 to-transparent',
  },
  salesforce: {
    name: 'Salesforce',
    color: '#00A1E0',
    borderClass: 'border-[#00A1E0]/30',
    bgClass: 'from-[#00A1E0]/6 to-transparent',
  },
} as const;

// ---------------------------------------------------------------------------
// Step badge — idle / active (spinning) / done (checkmark)
// ---------------------------------------------------------------------------

function StepBadge({ n, done, active }: { n: number; done?: boolean; active?: boolean }) {
  if (done) {
    return (
      <div className="w-6 h-6 rounded-full bg-[var(--color-success)]/15 flex items-center justify-center shrink-0">
        <CheckCircle2 size={14} className="text-[var(--color-success)]" />
      </div>
    );
  }
  if (active) {
    return (
      <div className="w-6 h-6 rounded-full bg-[var(--color-accent)]/15 flex items-center justify-center shrink-0">
        <Loader2 size={14} className="text-[var(--color-accent)] animate-spin" />
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
// Constants
// ---------------------------------------------------------------------------

const POLL_MS = 3_000;
const REDIRECT_DELAY_MS = 800;

// ---------------------------------------------------------------------------
// CRM Workflow (HubSpot or Salesforce)
// ---------------------------------------------------------------------------

type CrmFlowStage = 'idle' | 'syncing' | 'training' | 'scoring' | 'done' | 'error';

function CrmWorkflow({ mode }: { mode: 'hubspot' | 'salesforce' }) {
  const brand = BRAND[mode];
  const navigate = useNavigate();
  const { setPredictions } = usePredictions();

  // ── Provider / account data ────────────────────────────────────────────────
  const [provider, setProvider] = useState<ProviderInfo | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [accounts, setAccounts] = useState<IntegrationAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [disconnecting, setDisconnecting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // ── One-click flow state ───────────────────────────────────────────────────
  const [flowStage, setFlowStage] = useState<CrmFlowStage>('idle');
  const [flowError, setFlowError] = useState<{ stage: string; message: string } | null>(null);
  const [syncResult, setSyncResult] = useState<SyncResponse | null>(null);
  const [trainStatus, setTrainStatus] = useState<TrainJobStatus | null>(null);
  const [scoringResult, setScoringResult] = useState<ScoringResponse | null>(null);

  // Persists trained state across navigations via sessionStorage
  const [modelTrained, setModelTrained] = useState<boolean>(() => {
    try { return !!sessionStorage.getItem(`pp_crm_trained_${mode}`); } catch { return false; }
  });

  // Guard against duplicate concurrent flow invocations
  const flowActiveRef = useRef(false);

  // ── Data loading ───────────────────────────────────────────────────────────
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
      const activeProvider = providerList.find((p) => p.provider === mode) ?? null;
      setProvider(activeProvider);

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
        } catch { /* health check can fail when not yet connected */ }
      }
    } catch { /* ignore top-level errors */ } finally {
      setLoading(false);
    }
  }, [mode]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('oauth') === 'success') {
      setToast(`${brand.name} connected successfully!`);
      setTimeout(() => setToast(null), 4_000);
      window.history.replaceState({}, '', window.location.pathname);
    }
    loadData();
  }, [loadData, brand.name]);

  // Cancel in-flight polling if the component unmounts mid-flow
  useEffect(() => () => { flowActiveRef.current = false; }, []);

  // ── Derived connection state ───────────────────────────────────────────────
  const isConnected =
    health?.connected ||
    (provider?.enabled && provider?.status !== 'not_configured') ||
    false;

  const hasAccounts = (health?.account_count || accounts.length) > 0;

  // ── Promise-based training poller ─────────────────────────────────────────
  const pollTrainingUntilDone = useCallback(
    (jobId: string): Promise<TrainJobStatus> =>
      new Promise((resolve, reject) => {
        let handle: ReturnType<typeof setInterval> | null = null;
        const cleanup = () => {
          if (handle !== null) { clearInterval(handle); handle = null; }
        };
        const tick = async () => {
          if (!flowActiveRef.current) { cleanup(); reject(new Error('Cancelled')); return; }
          try {
            const s = await api.crmTrainStatus(mode, jobId);
            setTrainStatus(s);
            if (s.status === 'complete') { cleanup(); resolve(s); }
            else if (s.status === 'failed') {
              cleanup();
              reject(new Error(s.error_message || 'Training failed'));
            }
          } catch (e) { cleanup(); reject(e); }
        };
        tick();
        handle = setInterval(tick, POLL_MS);
      }),
    [mode],
  );

  // ── Score-only helper (used for retry) ────────────────────────────────────
  const runScoring = useCallback(async () => {
    setFlowStage('scoring');
    try {
      const result = await api.triggerScoring(mode);
      setScoringResult(result);
      try { const cached = await api.cachedPredictions(); setPredictions(cached); } catch { /* non-critical */ }
      setFlowStage('done');
      flowActiveRef.current = false;
      await new Promise((r) => setTimeout(r, REDIRECT_DELAY_MS));
      navigate('/');
    } catch (e: any) {
      setFlowError({ stage: 'scoring', message: e.message });
      setFlowStage('error');
      flowActiveRef.current = false;
    }
  }, [mode, setPredictions, navigate]);

  // ── Main orchestration: Sync → Train → Score → Navigate ───────────────────
  const handleRunFlow = useCallback(async () => {
    if (flowActiveRef.current) return;
    flowActiveRef.current = true;

    setFlowError(null);
    setSyncResult(null);
    setTrainStatus(null);
    setScoringResult(null);

    // Stage 1: Sync
    setFlowStage('syncing');
    try {
      const result = await api.syncIntegration(mode);
      setSyncResult(result);
      await loadData();
    } catch (e: any) {
      setFlowError({ stage: 'syncing', message: e.message });
      setFlowStage('error');
      flowActiveRef.current = false;
      return;
    }

    // Stage 2: Train
    setFlowStage('training');
    try {
      const accepted = await api.crmTrain(mode, 0.2);
      setTrainStatus({
        job_id: accepted.job_id, status: 'pending',
        version_str: null, metrics: null, error_message: null,
        started_at: null, completed_at: null,
      });
      await pollTrainingUntilDone(accepted.job_id);
      setModelTrained(true);
      try { sessionStorage.setItem(`pp_crm_trained_${mode}`, 'true'); } catch {}
    } catch (e: any) {
      if (e.message === 'Cancelled') { flowActiveRef.current = false; return; }
      setFlowError({ stage: 'training', message: e.message });
      setFlowStage('error');
      flowActiveRef.current = false;
      return;
    }

    // Stage 3: Score → Navigate
    await runScoring();
  }, [mode, loadData, pollTrainingUntilDone, runScoring]);

  // ── Connect / Disconnect ───────────────────────────────────────────────────
  const handleConnect = async () => {
    try {
      const redirectUri = `${window.location.origin}/workflow`;
      const res = await api.startOAuth(mode, redirectUri);
      window.location.href = res.auth_url;
    } catch (e: any) {
      setFlowError({ stage: 'idle', message: e.message });
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm(
      `Disconnect ${brand.name}? This removes the connection but keeps your synced accounts and predictions.`
    )) return;
    setDisconnecting(true);
    try {
      await api.disconnectIntegration(mode);
      await api.setMode('none');
    } catch (e: any) {
      setFlowError({ stage: 'idle', message: e.message });
      setDisconnecting(false);
      return;
    }
    navigate('/');
    window.location.reload();
  };

  // ── Derived step states ────────────────────────────────────────────────────
  const flowActive = flowStage === 'syncing' || flowStage === 'training' || flowStage === 'scoring';

  const syncDone =
    flowStage === 'training' || flowStage === 'scoring' || flowStage === 'done' ||
    (flowStage === 'error' && flowError?.stage !== 'syncing' && hasAccounts);

  const trainDone =
    flowStage === 'scoring' || flowStage === 'done' ||
    (flowStage === 'error' && flowError?.stage === 'scoring') ||
    (modelTrained && flowStage === 'idle');

  const scoreDone = flowStage === 'done' || !!scoringResult;

  const lastSync =
    health?.sync_states
      ?.map((s) => s.last_synced_at)
      .filter(Boolean)
      .sort()
      .reverse()[0] ?? null;

  // ── Render ─────────────────────────────────────────────────────────────────
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

      {/* Page header */}
      <div className={`mb-6 rounded-2xl p-5 bg-gradient-to-br ${brand.bgClass} border ${brand.borderClass}`}>
        <h1 className="text-xl font-bold">{brand.name} Workflow</h1>
        <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
          Connect, sync, train, and score your {brand.name} accounts
        </p>
      </div>

      {/* Global error banner — connect/disconnect only (stage-level errors show inline) */}
      {flowError && flowStage !== 'error' && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-xl text-sm text-[var(--color-danger)] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle size={14} />
            {flowError.message}
          </div>
          <button onClick={() => setFlowError(null)} className="text-xs ml-4 shrink-0">
            Dismiss
          </button>
        </div>
      )}

      <div className="space-y-3">
        {/* ── Step 1: Connect ─────────────────────────────────────────────── */}
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
              disabled={flowActive}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
              style={{ background: brand.color }}
            >
              <ExternalLink size={14} />
              Connect {brand.name}
            </button>
          ) : (
            <div className="flex items-center justify-between">
              <p className="text-xs text-[var(--color-text-muted)]">
                {brand.name} is connected.
                {lastSync && <> Last synced {new Date(lastSync).toLocaleString()}.</>}
              </p>
              <button
                onClick={handleDisconnect}
                disabled={disconnecting || flowActive}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-red-200 text-red-500 hover:bg-red-50 disabled:opacity-40 transition-colors"
              >
                {disconnecting && <Loader2 size={11} className="animate-spin" />}
                Disconnect
              </button>
            </div>
          )}
        </div>

        {/* ── Step 2: Sync Accounts — primary launch point ────────────────── */}
        <div
          className={`bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)] transition-opacity ${
            !isConnected ? 'opacity-40 pointer-events-none' : ''
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <StepBadge n={2} done={syncDone} active={flowStage === 'syncing'} />
            <h2 className="text-sm font-semibold">Sync Accounts</h2>
            {syncDone && flowStage !== 'syncing' && (
              <span className="ml-auto text-[10px] text-[var(--color-success)] font-medium flex items-center gap-1">
                <CheckCircle2 size={11} />
                {syncResult
                  ? `${syncResult.accounts_synced.toLocaleString()} accounts synced`
                  : 'Accounts synced'}
              </span>
            )}
          </div>

          {flowStage === 'syncing' && (
            <p className="text-xs text-[var(--color-text-muted)] flex items-center gap-1.5">
              <Loader2 size={11} className="animate-spin" />
              Syncing accounts from {brand.name}…
            </p>
          )}

          {flowStage === 'error' && flowError?.stage === 'syncing' && (
            <div className="space-y-2">
              <p className="text-xs text-[var(--color-danger)] flex items-center gap-1.5">
                <XCircle size={11} /> {flowError.message}
              </p>
              <button
                onClick={handleRunFlow}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90"
              >
                <RefreshCw size={11} /> Retry
              </button>
            </div>
          )}

          {/* Primary action — only shown when not actively running */}
          {!flowActive && flowStage !== 'error' && (
            <button
              onClick={handleRunFlow}
              disabled={!isConnected}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-xl bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40 transition-opacity"
            >
              <RefreshCw size={14} />
              {hasAccounts || flowStage === 'done' ? 'Resync Now' : 'Sync Now'}
            </button>
          )}
        </div>

        {/* ── Step 3: Train Model ─────────────────────────────────────────── */}
        <div
          className={`bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)] transition-opacity ${
            flowStage === 'idle' && !modelTrained ? 'opacity-40' : ''
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <StepBadge n={3} done={trainDone} active={flowStage === 'training'} />
            <h2 className="text-sm font-semibold">Train Model</h2>
          </div>

          {flowStage === 'idle' && !modelTrained && (
            <p className="text-xs text-[var(--color-text-muted)]">
              Model will be trained automatically after sync.
            </p>
          )}
          {flowStage === 'training' && (
            <p className="text-xs text-[var(--color-text-muted)] flex items-center gap-1.5">
              <Loader2 size={11} className="animate-spin" />
              Training model on {brand.name} account data…
            </p>
          )}
          {trainDone && flowStage !== 'training' && (
            <p className="text-xs text-[var(--color-success)] flex items-center gap-1.5">
              <CheckCircle2 size={11} />
              Model trained
              {trainStatus?.version_str ? ` · ${trainStatus.version_str}` : ''}
              {trainStatus?.metrics?.auc != null ? ` · AUC ${trainStatus.metrics.auc.toFixed(3)}` : ''}
            </p>
          )}
          {flowStage === 'error' && flowError?.stage === 'training' && (
            <div className="space-y-2">
              <p className="text-xs text-[var(--color-danger)] flex items-center gap-1.5">
                <XCircle size={11} /> {flowError.message}
              </p>
              <button
                onClick={handleRunFlow}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90"
              >
                <RefreshCw size={11} /> Retry from sync
              </button>
            </div>
          )}
        </div>

        {/* ── Step 4: Score Accounts ──────────────────────────────────────── */}
        <div
          className={`bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)] transition-opacity ${
            flowStage === 'idle' && !scoreDone ? 'opacity-40' : ''
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <StepBadge n={4} done={scoreDone} active={flowStage === 'scoring'} />
            <h2 className="text-sm font-semibold">Score Accounts</h2>
          </div>

          {flowStage === 'idle' && !scoreDone && (
            <p className="text-xs text-[var(--color-text-muted)]">
              Scores will be generated automatically after training.
            </p>
          )}
          {flowStage === 'scoring' && (
            <p className="text-xs text-[var(--color-text-muted)] flex items-center gap-1.5">
              <Loader2 size={11} className="animate-spin" /> Scoring accounts…
            </p>
          )}
          {scoreDone && flowStage !== 'scoring' && (
            <p className="text-xs text-[var(--color-success)] flex items-center gap-1.5">
              <CheckCircle2 size={11} />
              {scoringResult
                ? `${scoringResult.accounts_scored.toLocaleString()} accounts scored — ${formatCurrency(scoringResult.total_arr_at_risk)} ARR at risk`
                : 'Scoring complete'}
            </p>
          )}
          {flowStage === 'done' && (
            <p className="text-xs text-[var(--color-text-muted)] mt-1.5 flex items-center gap-1.5">
              <Loader2 size={11} className="animate-spin" /> Redirecting to overview…
            </p>
          )}
          {flowStage === 'error' && flowError?.stage === 'scoring' && (
            <div className="space-y-2">
              <p className="text-xs text-[var(--color-danger)] flex items-center gap-1.5">
                <XCircle size={11} /> {flowError.message}
              </p>
              <button
                onClick={() => {
                  if (flowActiveRef.current) return;
                  flowActiveRef.current = true;
                  setFlowError(null);
                  runScoring();
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90"
              >
                <RefreshCw size={11} /> Retry scoring
              </button>
            </div>
          )}
        </div>

        {/* ── CTAs ────────────────────────────────────────────────────────── */}
        {!flowActive && flowStage !== 'done' && (
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
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CSV Workflow
// ---------------------------------------------------------------------------

type CsvFlowStage = 'idle' | 'training' | 'scoring' | 'done' | 'error';

function CsvWorkflow() {
  const navigate = useNavigate();
  const { dataset } = useDataset();
  const { setPredictions } = usePredictions();

  const [csvFlowStage, setCsvFlowStage] = useState<CsvFlowStage>('idle');
  const [csvFlowError, setCsvFlowError] = useState<{ stage: string; message: string } | null>(null);
  const [csvTrainStatus, setCsvTrainStatus] = useState<TrainJobStatus | null>(null);
  const [csvScoringCount, setCsvScoringCount] = useState<number | null>(null);

  const csvFlowActiveRef = useRef(false);

  useEffect(() => () => { csvFlowActiveRef.current = false; }, []);

  // ── Promise-based CSV training poller ─────────────────────────────────────
  const pollCsvTrainingUntilDone = (jobId: string): Promise<TrainJobStatus> =>
    new Promise((resolve, reject) => {
      let handle: ReturnType<typeof setInterval> | null = null;
      const cleanup = () => {
        if (handle !== null) { clearInterval(handle); handle = null; }
      };
      const tick = async () => {
        if (!csvFlowActiveRef.current) { cleanup(); reject(new Error('Cancelled')); return; }
        try {
          const s = await api.trainStatus(jobId);
          setCsvTrainStatus(s);
          if (s.status === 'complete') { cleanup(); resolve(s); }
          else if (s.status === 'failed') {
            cleanup();
            reject(new Error(s.error_message || 'Training failed'));
          }
        } catch (e) { cleanup(); reject(e); }
      };
      tick();
      handle = setInterval(tick, POLL_MS);
    });

  // ── Score-only helper (used for retry) ────────────────────────────────────
  const runCsvScoring = useCallback(async () => {
    setCsvFlowStage('scoring');
    try {
      const res = await api.predict();
      setPredictions(res);
      setCsvScoringCount(res.predictions?.length ?? 0);
      setCsvFlowStage('done');
      csvFlowActiveRef.current = false;
      await new Promise((r) => setTimeout(r, REDIRECT_DELAY_MS));
      navigate('/');
    } catch (e: any) {
      setCsvFlowError({ stage: 'scoring', message: e.message });
      setCsvFlowStage('error');
      csvFlowActiveRef.current = false;
    }
  }, [setPredictions, navigate]);

  // ── Main CSV orchestration: Train → Score → Navigate ──────────────────────
  const handleRunCsvFlow = useCallback(async () => {
    if (csvFlowActiveRef.current || !dataset) return;
    csvFlowActiveRef.current = true;

    setCsvFlowError(null);
    setCsvTrainStatus(null);
    setCsvScoringCount(null);

    // Stage 1: Train
    setCsvFlowStage('training');
    try {
      const accepted = await api.train(0.2);
      setCsvTrainStatus({
        job_id: accepted.job_id, status: 'pending',
        version_str: null, metrics: null, error_message: null,
        started_at: null, completed_at: null,
      });
      await pollCsvTrainingUntilDone(accepted.job_id);
    } catch (e: any) {
      if (e.message === 'Cancelled') { csvFlowActiveRef.current = false; return; }
      setCsvFlowError({ stage: 'training', message: e.message });
      setCsvFlowStage('error');
      csvFlowActiveRef.current = false;
      return;
    }

    // Stage 2: Score → Navigate
    await runCsvScoring();
  }, [dataset, runCsvScoring]);

  // ── Derived step states ────────────────────────────────────────────────────
  const csvFlowActive = csvFlowStage === 'training' || csvFlowStage === 'scoring';

  const csvTrainDone =
    csvFlowStage === 'scoring' || csvFlowStage === 'done' ||
    (csvFlowStage === 'error' && csvFlowError?.stage === 'scoring');

  const csvScoreDone = csvFlowStage === 'done' || csvScoringCount != null;

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
        {/* ── Step 1: Upload ──────────────────────────────────────────────── */}
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <div className="flex items-center gap-3 mb-4">
            <StepBadge n={1} done={!!dataset} />
            <h2 className="text-sm font-semibold">Upload CSV</h2>
            {dataset && (
              <span className="ml-auto text-[10px] text-[var(--color-text-muted)]">
                {dataset.rows != null ? `${dataset.rows.toLocaleString()} rows` : ''}
                {dataset.name ? ` · ${dataset.name}` : ''}
              </span>
            )}
          </div>
          <DatasetsPage embedded />
        </div>

        {/* ── Step 2: Train — one-click "Run Analysis" ─────────────────────── */}
        <div
          className={`bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)] transition-opacity ${
            !dataset ? 'opacity-40 pointer-events-none' : ''
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <StepBadge n={2} done={csvTrainDone} active={csvFlowStage === 'training'} />
            <h2 className="text-sm font-semibold">Train Churn Model</h2>
          </div>

          {csvFlowStage === 'idle' && (
            <div className="space-y-3">
              <p className="text-xs text-[var(--color-text-muted)]">
                {dataset
                  ? 'Dataset ready — click Run Analysis to train and score your accounts automatically.'
                  : 'Upload a dataset to enable training.'}
              </p>
              {dataset && (
                <button
                  onClick={handleRunCsvFlow}
                  disabled={csvFlowActive}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40 transition-opacity"
                >
                  <Brain size={14} />
                  Run Analysis
                </button>
              )}
            </div>
          )}

          {csvFlowStage === 'training' && (
            <p className="text-xs text-[var(--color-text-muted)] flex items-center gap-1.5">
              <Loader2 size={11} className="animate-spin" /> Training model…
            </p>
          )}

          {csvTrainDone && csvFlowStage !== 'training' && (
            <p className="text-xs text-[var(--color-success)] flex items-center gap-1.5">
              <CheckCircle2 size={11} />
              Model trained
              {csvTrainStatus?.version_str ? ` · ${csvTrainStatus.version_str}` : ''}
              {csvTrainStatus?.metrics?.auc != null
                ? ` · AUC ${csvTrainStatus.metrics.auc.toFixed(3)}`
                : ''}
            </p>
          )}

          {csvFlowStage === 'error' && csvFlowError?.stage === 'training' && (
            <div className="space-y-2 mt-1">
              <p className="text-xs text-[var(--color-danger)] flex items-center gap-1.5">
                <XCircle size={11} /> {csvFlowError.message}
              </p>
              <button
                onClick={handleRunCsvFlow}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90"
              >
                <RefreshCw size={11} /> Retry
              </button>
            </div>
          )}
        </div>

        {/* ── Step 3: Generate Predictions ─────────────────────────────────── */}
        <div
          className={`bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)] transition-opacity ${
            !dataset ? 'opacity-40 pointer-events-none' : ''
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <StepBadge n={3} done={csvScoreDone} active={csvFlowStage === 'scoring'} />
            <h2 className="text-sm font-semibold">Generate Predictions</h2>
          </div>

          {csvFlowStage === 'idle' && !csvScoreDone && (
            <p className="text-xs text-[var(--color-text-muted)]">
              Predictions will be generated automatically after training.
            </p>
          )}
          {csvFlowStage === 'scoring' && (
            <p className="text-xs text-[var(--color-text-muted)] flex items-center gap-1.5">
              <Loader2 size={11} className="animate-spin" /> Scoring accounts…
            </p>
          )}
          {csvScoreDone && csvFlowStage !== 'scoring' && (
            <p className="text-xs text-[var(--color-success)] flex items-center gap-1.5">
              <CheckCircle2 size={11} />
              {csvScoringCount != null
                ? `${csvScoringCount.toLocaleString()} accounts scored`
                : 'Scoring complete'}
            </p>
          )}
          {csvFlowStage === 'done' && (
            <p className="text-xs text-[var(--color-text-muted)] mt-1.5 flex items-center gap-1.5">
              <Loader2 size={11} className="animate-spin" /> Redirecting to overview…
            </p>
          )}
          {csvFlowStage === 'error' && csvFlowError?.stage === 'scoring' && (
            <div className="space-y-2 mt-1">
              <p className="text-xs text-[var(--color-danger)] flex items-center gap-1.5">
                <XCircle size={11} /> {csvFlowError.message}
              </p>
              <button
                onClick={() => {
                  if (csvFlowActiveRef.current) return;
                  csvFlowActiveRef.current = true;
                  setCsvFlowError(null);
                  runCsvScoring();
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90"
              >
                <RefreshCw size={11} /> Retry scoring
              </button>
            </div>
          )}
        </div>

        {/* ── CTAs ────────────────────────────────────────────────────────── */}
        {!csvFlowActive && csvFlowStage !== 'done' && (
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
        )}
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
