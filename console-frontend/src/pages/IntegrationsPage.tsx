import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { ProviderInfo, IntegrationScore, RunDemoResponse } from '../lib/api';
import { formatCurrency } from '../lib/format';
import { IntegrationWizard } from '../components/IntegrationWizard';
import {
  Plug, RefreshCw, Play, Key, CheckCircle2, XCircle,
  AlertTriangle, Loader2, Users, Zap, ArrowRight, ExternalLink,
  Unplug, Clock, Shield,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Provider card (new platform)
// ---------------------------------------------------------------------------

const CATEGORY_COLORS: Record<string, string> = {
  CRM: 'bg-blue-500/10 text-blue-400',
  Billing: 'bg-green-500/10 text-green-400',
  Support: 'bg-orange-500/10 text-orange-400',
  Analytics: 'bg-purple-500/10 text-purple-400',
  Import: 'bg-[var(--color-accent)]/10 text-[var(--color-accent)]',
};

function ProviderCard({
  provider,
  onSetup,
  onSync,
  onRunDemo,
  onDisconnect,
  demoRunning,
}: {
  provider: ProviderInfo;
  onSetup: (p: ProviderInfo) => void;
  onSync: (name: string) => void;
  onRunDemo: (name: string) => void;
  onDisconnect: (name: string) => void;
  demoRunning: boolean;
}) {
  const isComingSoon = provider.template_status === 'coming_soon';
  const isConnected = provider.enabled && provider.status !== 'not_configured';

  const statusColor: Record<string, string> = {
    not_configured: 'text-[var(--color-text-muted)]',
    pending: 'text-[var(--color-warning)]',
    connected: 'text-[var(--color-accent)]',
    syncing: 'text-[var(--color-warning)]',
    healthy: 'text-green-400',
    error: 'text-red-400',
    disconnected: 'text-[var(--color-text-muted)]',
  };

  const StatusIcon = isConnected
    ? provider.status === 'healthy' ? CheckCircle2
      : provider.status === 'error' ? XCircle
      : provider.status === 'syncing' ? Loader2
      : Plug
    : Key;

  return (
    <div className={`
      bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-5
      ${isComingSoon ? 'opacity-50' : 'hover:border-[var(--color-accent)]/30'} transition-all
    `}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Plug size={16} className="text-[var(--color-accent)]" />
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
        <div className="flex items-center gap-3 mb-3">
          <div className="flex items-center gap-1">
            <StatusIcon size={12} className={statusColor[provider.status] || 'text-gray-400'} />
            <span className={`text-[10px] capitalize ${statusColor[provider.status]}`}>
              {provider.status.replace('_', ' ')}
            </span>
          </div>
          <span className="text-[10px] text-[var(--color-text-muted)]">
            {provider.account_count} accounts
          </span>
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        {isComingSoon ? (
          <span className="flex items-center gap-1 px-3 py-1.5 text-[10px] font-medium rounded-lg bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]">
            <Clock size={10} /> Coming Soon
          </span>
        ) : !isConnected ? (
          <button
            onClick={() => onSetup(provider)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90"
          >
            <Key size={12} /> Connect
          </button>
        ) : (
          <>
            <button
              onClick={() => onSync(provider.provider)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] border border-[var(--color-border)]"
            >
              <RefreshCw size={12} /> Sync
            </button>
            <button
              onClick={() => onRunDemo(provider.provider)}
              disabled={demoRunning}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40"
            >
              {demoRunning ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
              Sync + Score
            </button>
            <button
              onClick={() => onDisconnect(provider.provider)}
              className="flex items-center gap-1 px-2 py-1.5 text-xs rounded-lg text-[var(--color-text-muted)] hover:text-red-400"
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
// Scores table
// ---------------------------------------------------------------------------

function ScoresTable({ scores }: { scores: IntegrationScore[] }) {
  if (scores.length === 0) return null;

  const tierColor = (tier: string) => {
    if (tier === 'High Risk') return 'text-red-400';
    if (tier === 'Medium Risk') return 'text-[var(--color-warning)]';
    return 'text-green-400';
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
            <tr key={i} className="border-b border-[var(--color-border)]/50 hover:bg-[rgba(255,255,255,0.02)]">
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

export function IntegrationsPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [scores, setScores] = useState<IntegrationScore[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [scoring, setScoring] = useState(false);
  const [runningDemo, setRunningDemo] = useState<string | null>(null);
  const [wizardProvider, setWizardProvider] = useState<ProviderInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const loadData = useCallback(async () => {
    try {
      const [intRes, scoresRes] = await Promise.all([
        api.integrations(),
        api.latestScores().catch(() => ({ scores: [], count: 0 })),
      ]);

      // Handle both new platform and legacy responses
      if (intRes.providers) {
        setProviders(intRes.providers);
      } else if (intRes.connectors) {
        // Map legacy connectors to ProviderInfo shape
        setProviders(intRes.connectors.map((c) => ({
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
        })));
      }

      setScores(scoresRes.scores);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSync = async (name: string) => {
    setSyncing(name);
    try {
      const result = await api.syncIntegration(name);
      showToast(`Synced ${result.accounts_synced} accounts from ${name}`);
      loadData();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSyncing(null);
    }
  };

  const handleScore = async () => {
    setScoring(true);
    try {
      const result = await api.triggerScoring();
      showToast(`Scored ${result.accounts_scored} accounts — ${formatCurrency(result.total_arr_at_risk)} ARR at risk`);
      loadData();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setScoring(false);
    }
  };

  const handleRunDemo = async (connectorName: string) => {
    setRunningDemo(connectorName);
    try {
      const result: RunDemoResponse = await api.runDemo(connectorName);
      showToast(
        `Synced ${result.synced_accounts} accounts, scored ${result.scored_accounts} — ${formatCurrency(result.total_arr_at_risk)} ARR at risk`
      );
      loadData();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunningDemo(null);
    }
  };

  const handleDisconnect = async (provider: string) => {
    try {
      await api.disconnectIntegration(provider);
      showToast(`${provider} disconnected`);
      loadData();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const connectedProviders = providers.filter((p) => p.enabled);
  const totalAccounts = providers.reduce((sum, p) => sum + (p.account_count || 0), 0);
  const enabledCount = connectedProviders.length;

  // Group by category
  const categories = ['CRM', 'Billing', 'Support', 'Analytics', 'Import'];
  const grouped = categories.map((cat) => ({
    category: cat,
    providers: providers.filter((p) => p.category === cat),
  })).filter((g) => g.providers.length > 0);

  // Ungrouped
  const groupedProviders = new Set(grouped.flatMap((g) => g.providers.map((p) => p.provider)));
  const ungrouped = providers.filter((p) => !groupedProviders.has(p.provider));

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-[var(--color-accent)]" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl">
      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-green-500/20 border border-green-500/30 text-green-300 px-4 py-2.5 rounded-xl text-sm backdrop-blur-md">
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
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">Integrations</h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Connect your CRM, billing, support, and analytics tools to score real accounts against your churn model.
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-sm text-red-300 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300 text-xs">Dismiss</button>
        </div>
      )}

      {/* Summary strip */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-4">
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Connected</div>
          <div className="text-xl font-bold text-[var(--color-text-primary)]">
            {enabledCount}<span className="text-[var(--color-text-muted)] text-sm font-normal">/{providers.length}</span>
          </div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-4">
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Accounts Synced</div>
          <div className="text-xl font-bold text-[var(--color-text-primary)]">{totalAccounts.toLocaleString()}</div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-4">
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Scored</div>
          <div className="text-xl font-bold text-[var(--color-text-primary)]">{scores.length.toLocaleString()}</div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-4">
          <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
            <Shield size={10} /> Encryption
          </div>
          <div className="text-xs font-medium text-green-400 mt-1">AES-256-GCM</div>
        </div>
      </div>

      {/* Provider cards by category */}
      {grouped.map((group) => (
        <div key={group.category} className="mb-6">
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
            {group.category}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {group.providers.map((p) => (
              <ProviderCard
                key={p.provider}
                provider={p}
                onSetup={setWizardProvider}
                onSync={handleSync}
                onRunDemo={handleRunDemo}
                onDisconnect={handleDisconnect}
                demoRunning={runningDemo === p.provider}
              />
            ))}
          </div>
        </div>
      ))}

      {ungrouped.length > 0 && (
        <div className="mb-6">
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3">Other</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {ungrouped.map((p) => (
              <ProviderCard
                key={p.provider}
                provider={p}
                onSetup={setWizardProvider}
                onSync={handleSync}
                onRunDemo={handleRunDemo}
                onDisconnect={handleDisconnect}
                demoRunning={runningDemo === p.provider}
              />
            ))}
          </div>
        </div>
      )}

      {/* Pipeline: Sync → Score */}
      {enabledCount > 0 && (
        <div className="mb-6 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
            <Zap size={14} className="text-[var(--color-accent)]" /> Scoring Pipeline
          </h2>
          <div className="flex items-center gap-3">
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
              Score All Accounts
            </button>
            <ArrowRight size={14} className="text-[var(--color-text-muted)]" />
            <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-bg-tertiary)] border border-[var(--color-border)]">
              <Zap size={14} className="text-[var(--color-text-muted)]" />
              <span className="text-xs text-[var(--color-text-secondary)]">{scores.length} scored</span>
            </div>
          </div>
        </div>
      )}

      {/* Scores table */}
      {scores.length > 0 && (
        <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
            <Zap size={14} className="text-[var(--color-accent)]" /> Latest Churn Scores
          </h2>
          <ScoresTable scores={scores} />
        </div>
      )}
    </div>
  );
}

export default IntegrationsPage;
