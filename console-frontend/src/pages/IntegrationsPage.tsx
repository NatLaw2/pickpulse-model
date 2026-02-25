import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { ConnectorInfo, IntegrationScore, RunDemoResponse } from '../lib/api';
import { formatCurrency } from '../lib/format';
import {
  Plug, RefreshCw, Play, Key, CheckCircle2, XCircle,
  AlertTriangle, Loader2, Users, Zap, ArrowRight,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Connector card
// ---------------------------------------------------------------------------

function ConnectorCard({
  connector,
  onConfigure,
  onSync,
  onRunDemo,
  demoRunning,
}: {
  connector: ConnectorInfo;
  onConfigure: (name: string) => void;
  onSync: (name: string) => void;
  onRunDemo: (name: string) => void;
  demoRunning: boolean;
}) {
  const statusColor: Record<string, string> = {
    not_configured: 'text-[var(--color-text-muted)]',
    configured: 'text-[var(--color-accent)]',
    syncing: 'text-[var(--color-warning)]',
    healthy: 'text-green-400',
    error: 'text-red-400',
  };

  const StatusIcon = connector.status === 'healthy'
    ? CheckCircle2
    : connector.status === 'error'
      ? XCircle
      : connector.status === 'not_configured'
        ? Key
        : Plug;

  return (
    <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-5 hover:border-[var(--color-accent)]/30 transition-all">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Plug size={16} className="text-[var(--color-accent)]" />
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
            {connector.display_name}
          </h3>
        </div>
        <div className="flex items-center gap-1.5">
          <StatusIcon size={14} className={statusColor[connector.status] || 'text-gray-400'} />
          <span className={`text-xs capitalize ${statusColor[connector.status]}`}>
            {connector.status.replace('_', ' ')}
          </span>
        </div>
      </div>

      {connector.enabled && (
        <div className="text-xs text-[var(--color-text-muted)] mb-3">
          {connector.account_count} accounts synced
        </div>
      )}

      {connector.error_message && (
        <div className="flex items-start gap-1.5 mb-3 text-xs text-red-400">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span>{connector.error_message}</span>
        </div>
      )}

      <div className="flex gap-2">
        {!connector.enabled ? (
          <button
            onClick={() => onConfigure(connector.name)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90 transition-opacity"
          >
            <Key size={12} /> Connect
          </button>
        ) : (
          <button
            onClick={() => onSync(connector.name)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors border border-[var(--color-border)]"
          >
            <RefreshCw size={12} /> Sync Now
          </button>
          <button
            onClick={() => onRunDemo(connector.name)}
            disabled={demoRunning}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40 transition-opacity"
          >
            {demoRunning ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
            Run Demo Sync + Score
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Configure modal (simple)
// ---------------------------------------------------------------------------

function ConfigureModal({
  connectorName,
  onClose,
  onSave,
}: {
  connectorName: string;
  onClose: () => void;
  onSave: (key: string) => void;
}) {
  const [apiKey, setApiKey] = useState('');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-6 w-full max-w-md">
        <h2 className="text-lg font-semibold text-[var(--color-text-primary)] mb-1">
          Connect {connectorName}
        </h2>
        <p className="text-xs text-[var(--color-text-muted)] mb-4">
          Enter your API key to connect. We'll test the connection before saving.
        </p>

        <label className="block text-xs text-[var(--color-text-secondary)] mb-1.5">API Key</label>
        <input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="sk-..."
          className="w-full px-3 py-2 text-sm bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg text-[var(--color-text-primary)] focus:border-[var(--color-accent)] focus:outline-none"
        />

        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium rounded-lg text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(apiKey)}
            disabled={!apiKey.trim()}
            className="px-4 py-2 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40 transition-opacity"
          >
            Test & Save
          </button>
        </div>
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
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [scores, setScores] = useState<IntegrationScore[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [scoring, setScoring] = useState(false);
  const [runningDemo, setRunningDemo] = useState<string | null>(null);
  const [configuring, setConfiguring] = useState<string | null>(null);
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
      setConnectors(intRes.connectors);
      setScores(scoresRes.scores);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleConfigure = async (apiKey: string) => {
    if (!configuring) return;
    try {
      await api.configureIntegration(configuring, apiKey);
      showToast(`${configuring} connected successfully`);
      setConfiguring(null);
      loadData();
    } catch (e: any) {
      setError(e.message);
    }
  };

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
        `Demo complete: synced ${result.sync.accounts_synced} accounts, scored ${result.scoring.accounts_scored} — ${formatCurrency(result.scoring.total_arr_at_risk)} ARR at risk`
      );
      loadData();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunningDemo(null);
    }
  };

  const totalAccounts = connectors.reduce((sum, c) => sum + c.account_count, 0);
  const enabledCount = connectors.filter((c) => c.enabled).length;

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

      {/* Configure modal */}
      {configuring && (
        <ConfigureModal
          connectorName={configuring}
          onClose={() => setConfiguring(null)}
          onSave={handleConfigure}
        />
      )}

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">Integrations</h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Connect HubSpot, Stripe, or other systems to score real accounts against your churn model.
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
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-4">
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Connectors</div>
          <div className="text-xl font-bold text-[var(--color-text-primary)]">
            {enabledCount}<span className="text-[var(--color-text-muted)] text-sm font-normal">/{connectors.length}</span>
          </div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-4">
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Accounts Synced</div>
          <div className="text-xl font-bold text-[var(--color-text-primary)]">{totalAccounts.toLocaleString()}</div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-4">
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Scored Accounts</div>
          <div className="text-xl font-bold text-[var(--color-text-primary)]">{scores.length.toLocaleString()}</div>
        </div>
      </div>

      {/* Connectors */}
      <div className="mb-6">
        <h2 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
          <Plug size={14} /> Available Connectors
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {connectors.map((c) => (
            <ConnectorCard
              key={c.name}
              connector={c}
              onConfigure={(name) => setConfiguring(name)}
              onSync={(name) => syncing ? undefined : handleSync(name)}
              onRunDemo={(name) => runningDemo ? undefined : handleRunDemo(name)}
              demoRunning={runningDemo === c.name}
            />
          ))}
        </div>
      </div>

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
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40 transition-opacity"
            >
              {scoring ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Play size={12} />
              )}
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
