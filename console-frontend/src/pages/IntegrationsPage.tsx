import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';
import type {
  ProviderInfo, IntegrationScore, HealthResponse,
  IntegrationAccount,
} from '../lib/api';
import { usePredictions } from '../lib/PredictionContext';
import { formatCurrency } from '../lib/format';
import { IntegrationWizard } from '../components/IntegrationWizard';
import {
  Plug, RefreshCw, Play, Key, CheckCircle2, XCircle,
  AlertTriangle, Loader2, Users, Zap, ArrowRight, ExternalLink,
  Unplug, Activity,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(iso: string | null): string {
  if (!iso) return 'never';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ---------------------------------------------------------------------------
// Provider visibility config
// ---------------------------------------------------------------------------

// Providers hidden from the UI until they are demo-ready.
// Data is still fetched normally — this is a render-only filter.
const HIDDEN_PROVIDERS = new Set(['custom', 'custom_crm']);

// ---------------------------------------------------------------------------
// Provider card
// ---------------------------------------------------------------------------

const CATEGORY_COLORS: Record<string, string> = {
  CRM: 'bg-blue-500/10 text-blue-400',
  Billing: 'bg-green-500/10 text-[var(--color-success)]',
  Support: 'bg-orange-500/10 text-orange-400',
  Analytics: 'bg-purple-500/10 text-purple-400',
  Import: 'bg-[var(--color-accent)]/10 text-[var(--color-accent)]',
};

function ProviderCard({
  provider,
  health,
  onSetup,
  onSync,
  onDisconnect,
  syncing,
}: {
  provider: ProviderInfo;
  health: HealthResponse | null;
  onSetup: (p: ProviderInfo) => void;
  onSync: (name: string) => void;
  onDisconnect: (name: string) => void;
  syncing: boolean;
}) {
  const isConnected = health?.connected || (provider.enabled && provider.status !== 'not_configured');

  const statusColor: Record<string, string> = {
    not_configured: 'text-[var(--color-text-muted)]',
    pending: 'text-[var(--color-warning)]',
    connected: 'text-[var(--color-accent)]',
    syncing: 'text-[var(--color-warning)]',
    healthy: 'text-[var(--color-success)]',
    error: 'text-[var(--color-danger)]',
    disconnected: 'text-[var(--color-text-muted)]',
  };

  const displayStatus = health?.status || provider.status;

  const StatusIcon = isConnected
    ? displayStatus === 'healthy' ? CheckCircle2
      : displayStatus === 'error' ? XCircle
      : displayStatus === 'syncing' ? Loader2
      : Plug
    : Key;

  // Find last sync time from health data
  const lastSync = health?.sync_states
    ?.map(s => s.last_synced_at)
    .filter(Boolean)
    .sort()
    .reverse()[0] ?? null;

  const isHubSpot = provider.provider === 'hubspot';

  return (
    <div className={`
      rounded-2xl p-5 transition-all duration-200
      ${isHubSpot
        ? 'border border-[#FF7A59]/30 bg-gradient-to-br from-[#FF7A59]/8 to-[#FF7A59]/4 hover:border-[#FF7A59]/50 hover:shadow-md hover:shadow-[#FF7A59]/8'
        : 'bg-[var(--color-bg-secondary)] border border-[var(--color-border)] hover:border-[var(--color-accent)]/30'
      }
    `}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {isHubSpot ? (
            <div className="w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0" style={{ background: '#FF7A59' }}>
              <svg width="12" height="12" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="10" cy="10" r="3.5" fill="white" />
                <circle cx="10" cy="3" r="1.5" fill="white" />
                <circle cx="10" cy="17" r="1.5" fill="white" />
                <circle cx="3" cy="10" r="1.5" fill="white" />
                <circle cx="17" cy="10" r="1.5" fill="white" />
                <circle cx="5.05" cy="5.05" r="1.5" fill="white" />
                <circle cx="14.95" cy="14.95" r="1.5" fill="white" />
                <circle cx="14.95" cy="5.05" r="1.5" fill="white" />
                <circle cx="5.05" cy="14.95" r="1.5" fill="white" />
              </svg>
            </div>
          ) : (
            <Plug size={16} className="text-[var(--color-accent)]" />
          )}
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
            {provider.display_name}
          </h3>
        </div>
        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${CATEGORY_COLORS[provider.category] || 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]'}`}>
          {provider.category}
        </span>
      </div>

      <p className="text-[11px] text-[var(--color-text-muted)] mb-3 line-clamp-2">
        {provider.description}
      </p>

      {isConnected && (
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <div className="flex items-center gap-1">
            <StatusIcon size={12} className={statusColor[displayStatus] || 'text-gray-400'} />
            <span className={`text-[10px] capitalize ${statusColor[displayStatus]}`}>
              {displayStatus.replace('_', ' ')}
            </span>
          </div>
          <span className="text-[10px] text-[var(--color-text-muted)]">
            {health?.account_count ?? provider.account_count} accounts
          </span>
          {lastSync && (
            <span className="text-[10px] text-[var(--color-text-muted)]">
              synced {timeAgo(lastSync)}
            </span>
          )}
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        {!isConnected ? (
          <button
            onClick={() => onSetup(provider)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg text-white hover:opacity-90"
            style={{ background: isHubSpot ? '#FF7A59' : 'var(--color-accent)' }}
          >
            {provider.auth_method === 'oauth' ? <ExternalLink size={12} /> : <Key size={12} />}
            Connect{provider.auth_method === 'oauth' ? ` ${provider.display_name}` : ''}
          </button>
        ) : (
          <>
            <button
              onClick={() => onSync(provider.provider)}
              disabled={syncing}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] border border-[var(--color-border)] disabled:opacity-40"
            >
              {syncing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              Sync Now
            </button>
            <button
              onClick={() => onDisconnect(provider.provider)}
              className="flex items-center gap-1 px-2 py-1.5 text-xs rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-danger)]"
              title="Disconnect"
            >
              <Unplug size={12} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Accounts table
// ---------------------------------------------------------------------------

function AccountsTable({ accounts }: { accounts: IntegrationAccount[] }) {
  if (accounts.length === 0) return null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border)]">
            <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Name</th>
            <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Source</th>
            <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Status</th>
            <th className="text-right py-2 px-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">ARR</th>
            <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Industry</th>
            <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Last Updated</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((a) => (
            <tr key={a.external_id} className="border-b border-[var(--color-border)]/50 hover:bg-[var(--color-bg-primary)]">
              <td className="py-2.5 px-3">
                <div className="text-[var(--color-text-primary)] font-medium">{a.name || a.external_id}</div>
                {a.domain && <div className="text-[10px] text-[var(--color-text-muted)]">{a.domain}</div>}
              </td>
              <td className="py-2.5 px-3 text-[var(--color-text-muted)] text-xs capitalize">{a.source}</td>
              <td className="py-2.5 px-3 text-xs text-[var(--color-text-secondary)] capitalize">{a.status || '—'}</td>
              <td className="py-2.5 px-3 text-right font-mono text-[var(--color-text-primary)]">
                {a.arr != null ? formatCurrency(a.arr) : '—'}
              </td>
              <td className="py-2.5 px-3 text-xs text-[var(--color-text-secondary)]">{a.metadata?.industry || '—'}</td>
              <td className="py-2.5 px-3 text-xs text-[var(--color-text-muted)]">{timeAgo(a.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scores table
// ---------------------------------------------------------------------------

function ScoresTable({ scores }: { scores: IntegrationScore[] }) {
  if (scores.length === 0) return null;

  const tierColor = (tier: string) => {
    if (tier === 'High Risk') return 'text-[var(--color-danger)]';
    if (tier === 'Medium Risk') return 'text-[var(--color-warning)]';
    return 'text-[var(--color-success)]';
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border)]">
            <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Account</th>
            <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Source</th>
            <th className="text-right py-2 px-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Churn Risk</th>
            <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Tier</th>
            <th className="text-right py-2 px-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">ARR at Risk</th>
            <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Action</th>
          </tr>
        </thead>
        <tbody>
          {scores.map((s, i) => (
            <tr key={i} className="border-b border-[var(--color-border)]/50 hover:bg-[var(--color-bg-primary)]">
              <td className="py-2.5 px-3">
                <div className="text-[var(--color-text-primary)] font-medium">{s.name || s.external_id}</div>
                {s.email && <div className="text-[10px] text-[var(--color-text-muted)]">{s.email}</div>}
              </td>
              <td className="py-2.5 px-3 text-[var(--color-text-muted)] text-xs capitalize">{s.source}</td>
              <td className="py-2.5 px-3 text-right font-mono text-[var(--color-text-primary)]">
                {(s.churn_probability * 100).toFixed(1)}%
              </td>
              <td className={`py-2.5 px-3 text-xs font-medium ${tierColor(s.tier)}`}>{s.tier}</td>
              <td className="py-2.5 px-3 text-right font-mono text-[var(--color-text-primary)]">
                {s.arr_at_risk != null ? formatCurrency(s.arr_at_risk) : '—'}
              </td>
              <td className="py-2.5 px-3 text-xs text-[var(--color-text-muted)]">
                {s.recommended_action || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function IntegrationsPage({ embedded }: { embedded?: boolean } = {}) {
  const { setPredictions } = usePredictions();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [healthMap, setHealthMap] = useState<Record<string, HealthResponse>>({});
  const [accounts, setAccounts] = useState<IntegrationAccount[]>([]);
  const [scores, setScores] = useState<IntegrationScore[]>([]);
  const [hasScored, setHasScored] = useState(false);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [scoring, setScoring] = useState(false);
  const [wizardProvider, setWizardProvider] = useState<ProviderInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 5000);
  };

  // ------------------------------------------------------------------
  // Data loading
  // ------------------------------------------------------------------

  const loadData = useCallback(async () => {
    try {
      // Fetch providers first so we can scope accounts to the active provider(s).
      const intRes = await api.integrations().catch(() => ({ providers: [], connectors: [] }));

      // Handle both new platform and legacy responses
      let providerList: ProviderInfo[] = [];
      if (intRes.providers && intRes.providers.length > 0) {
        providerList = intRes.providers;
      } else if (intRes.connectors && intRes.connectors.length > 0) {
        providerList = intRes.connectors.map((c) => ({
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
      setProviders(providerList);

      // Fetch health first — must happen before accounts so we can filter by truly connected providers.
      // provider.enabled alone is unreliable (HubSpot may retain enabled:true after disconnect).
      // Health is the authoritative signal for whether a provider is actually active.
      const candidateProviders = providerList.filter(
        (p) => p.enabled || p.status === 'healthy' || p.status === 'connected'
      );
      const healthResults: Record<string, HealthResponse> = {};
      await Promise.all(
        candidateProviders.map(async (p) => {
          try {
            healthResults[p.provider] = await api.integrationHealth(p.provider);
          } catch { /* ignore */ }
        })
      );
      setHealthMap(healthResults);

      // Determine truly connected providers using the same logic as ProviderCard.isConnected:
      //   health?.connected  OR  (provider.enabled AND status !== 'not_configured')
      // This matches what the cards show, so the account table stays in sync with the UI.
      const trulyConnected = providerList.filter(
        (p) => healthResults[p.provider]?.connected || (p.enabled && p.status !== 'not_configured')
      );
      // If exactly one provider is active, scope accounts to it. Otherwise show all (multi-connected).
      const sourceFilter = trulyConnected.length === 1 ? trulyConnected[0].provider : undefined;

      const [acctRes, scoresRes] = await Promise.all([
        api.integrationAccounts(sourceFilter).catch(() => ({ accounts: [], total: 0, showing: 0 })),
        api.latestScores().catch(() => ({ scores: [], count: 0 })),
      ]);

      setAccounts(acctRes.accounts ?? []);
      setScores(scoresRes.scores ?? []);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // ------------------------------------------------------------------
  // OAuth return detection
  // ------------------------------------------------------------------

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauthStatus = params.get('oauth');
    const oauthProvider = params.get('provider');

    if (oauthStatus === 'success' && oauthProvider) {
      showToast(`${oauthProvider.charAt(0).toUpperCase() + oauthProvider.slice(1)} connected successfully! Fetching latest data...`);
      // Clean up URL params without page reload
      window.history.replaceState({}, '', window.location.pathname);
    }

    loadData();
  }, [loadData]);

  // ------------------------------------------------------------------
  // Actions
  // ------------------------------------------------------------------

  const handleConnectOAuth = async (provider: ProviderInfo) => {
    if (provider.auth_method === 'oauth') {
      try {
        const redirectUri = `${window.location.origin}/data-sources`;
        const res = await api.startOAuth(provider.provider, redirectUri);
        window.location.href = res.auth_url;
      } catch (e: any) {
        setError(e.message);
      }
    } else {
      setWizardProvider(provider);
    }
  };

  const handleSync = async (name: string) => {
    setSyncing(name);
    setError(null);
    try {
      const result = await api.syncIntegration(name);
      showToast(`Synced ${result.accounts_synced} accounts, ${result.signals_synced} signals from ${name}`);
      await loadData();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSyncing(null);
    }
  };

  const handleScore = async () => {
    setScoring(true);
    setError(null);
    try {
      // Determine the active provider to scope scoring.
      // Always pick the first connected provider — passing undefined would cause
      // the backend to score all providers and record no specific source,
      // which is the primary source of cross-provider account mixing.
      const connected = providers.filter(
        (p) => healthMap[p.provider]?.connected || (p.enabled && p.status !== 'not_configured')
      );
      const activeProvider = connected[0]?.provider;
      const result = await api.triggerScoring(activeProvider);
      showToast(`Scored ${result.accounts_scored} accounts — ${formatCurrency(result.total_arr_at_risk)} ARR at risk`);
      await loadData();
      setHasScored(true);
      // Populate the predictions context so Accounts page shows CRM results without manual navigation
      try {
        const cached = await api.cachedPredictions();
        setPredictions(cached);
      } catch { /* non-critical */ }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setScoring(false);
    }
  };

  const handleDisconnect = async (provider: string) => {
    try {
      await api.disconnectIntegration(provider);
      showToast(`${provider} disconnected`);
      await loadData();
    } catch (e: any) {
      setError(e.message);
    }
  };

  // ------------------------------------------------------------------
  // Computed
  // ------------------------------------------------------------------

  const connectedProviders = providers.filter(
    (p) => p.enabled || healthMap[p.provider]?.connected
  );
  const totalAccounts = accounts.length;
  const enabledCount = connectedProviders.length;

  // Render-only filter: hide coming-soon and not-yet-ready providers
  const visibleProviders = providers.filter(
    (p) => p.template_status !== 'coming_soon' && !HIDDEN_PROVIDERS.has(p.provider)
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-[var(--color-accent)]" />
        <span className="ml-2 text-sm text-[var(--color-text-muted)]">Loading integrations...</span>
      </div>
    );
  }

  return (
    <div className="max-w-5xl">
      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-emerald-50 border border-emerald-200 text-[var(--color-success)] px-4 py-2.5 rounded-xl text-sm backdrop-blur-md flex items-center gap-2">
          <CheckCircle2 size={14} />
          {toast}
        </div>
      )}

      {/* Setup wizard */}
      {wizardProvider && (
        <IntegrationWizard
          provider={wizardProvider}
          onClose={() => setWizardProvider(null)}
          onComplete={() => {
            setWizardProvider(null);
            loadData();
          }}
        />
      )}

      {/* Header */}
      {!embedded && (
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">Integrations</h1>
          <p className="text-sm text-[var(--color-text-muted)] mt-1">
            Connect your CRM, billing, support, and analytics tools to score real accounts against your churn model.
          </p>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-xl text-sm text-[var(--color-danger)] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle size={14} />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-[var(--color-danger)] hover:text-[var(--color-danger)] text-xs ml-4">Dismiss</button>
        </div>
      )}

      {/* Provider cards — flat grid, no category grouping */}
      {visibleProviders.length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-[var(--color-text-secondary)] mb-3">Connect your data</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {visibleProviders.map((p) => (
              <ProviderCard
                key={p.provider}
                provider={p}
                health={healthMap[p.provider] || null}
                onSetup={handleConnectOAuth}
                onSync={handleSync}
                onDisconnect={handleDisconnect}
                syncing={syncing === p.provider}
              />
            ))}
          </div>
        </div>
      )}

      {/* Scoring pipeline — only shown when an integration is actually connected */}
      {enabledCount > 0 && (
        <div className="mb-6 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
            <Zap size={14} className="text-[var(--color-accent)]" /> Scoring Pipeline
          </h2>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-bg-tertiary)] border border-[var(--color-border)]">
              <Users size={14} className="text-[var(--color-text-muted)]" />
              <span className="text-xs text-[var(--color-text-secondary)]">{totalAccounts} accounts</span>
            </div>
            <ArrowRight size={14} className="text-[var(--color-text-muted)]" />
            <button
              onClick={handleScore}
              disabled={scoring || totalAccounts === 0}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40"
            >
              {scoring ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
              Rescore All
            </button>
            <ArrowRight size={14} className="text-[var(--color-text-muted)]" />
            <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-bg-tertiary)] border border-[var(--color-border)]">
              <Zap size={14} className="text-[var(--color-text-muted)]" />
              <span className="text-xs text-[var(--color-text-secondary)]">{scores.length} scored</span>
            </div>
          </div>
        </div>
      )}

      {/* Accounts table — only shown when an integration is actually connected */}
      {enabledCount > 0 && accounts.length > 0 && (
        <div className="mb-6 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
            <Users size={14} className="text-[var(--color-accent)]" /> Synced Accounts
            <span className="text-[10px] font-normal text-[var(--color-text-muted)] ml-1">({accounts.length})</span>
          </h2>
          <AccountsTable accounts={accounts} />
        </div>
      )}

      {/* Scores table — only shown after explicit Rescore All action this session */}
      {hasScored && scores.length > 0 && (
        <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
            <Activity size={14} className="text-[var(--color-accent)]" /> Latest Churn Scores
            <span className="text-[10px] font-normal text-[var(--color-text-muted)] ml-1">({scores.length})</span>
          </h2>
          <ScoresTable scores={scores} />
        </div>
      )}

      {/* Empty state */}
      {enabledCount === 0 && accounts.length === 0 && scores.length === 0 && (
        <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-8 text-center">
          <Plug size={32} className="mx-auto mb-3 text-[var(--color-text-muted)]" />
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-1">No integrations connected</h3>
          <p className="text-xs text-[var(--color-text-muted)] max-w-md mx-auto">
            Connect HubSpot, Stripe, or another provider above to sync real customer data and score it against your churn model.
          </p>
        </div>
      )}
    </div>
  );
}

export default IntegrationsPage;
