import { useState } from 'react';
import { api } from '../lib/api';
import type { FieldMapping, ProviderInfo } from '../lib/api';
import {
  ArrowLeft, ArrowRight, Check, ExternalLink, Loader2, Upload, X,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Wizard steps
// ---------------------------------------------------------------------------

type WizardStep = 'connect' | 'map' | 'preview' | 'confirm';

const STEPS: { key: WizardStep; label: string }[] = [
  { key: 'connect', label: 'Connect' },
  { key: 'map', label: 'Map Fields' },
  { key: 'preview', label: 'Preview' },
  { key: 'confirm', label: 'Confirm' },
];

// ---------------------------------------------------------------------------
// Main Wizard
// ---------------------------------------------------------------------------

export function IntegrationWizard({
  provider,
  onClose,
  onComplete,
}: {
  provider: ProviderInfo;
  onClose: () => void;
  onComplete: () => void;
}) {
  const [step, setStep] = useState<WizardStep>('connect');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 1 state
  const [apiKey, setApiKey] = useState('');
  const [connected, setConnected] = useState(provider.enabled);

  // Step 2 state
  const [mappings, setMappings] = useState<FieldMapping[]>([]);
  const [mappingsLoaded, setMappingsLoaded] = useState(false);

  // Step 3 state
  const [previewData, setPreviewData] = useState<any[]>([]);
  const [previewTotal, setPreviewTotal] = useState(0);

  // Step 4 state
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<any>(null);

  const stepIndex = STEPS.findIndex((s) => s.key === step);

  // ------------------------------------------------------------------
  // Step handlers
  // ------------------------------------------------------------------

  const handleConnect = async () => {
    setLoading(true);
    setError(null);
    try {
      if (provider.auth_method === 'oauth') {
        const redirectUri = `${window.location.origin}/integrations`;
        const res = await api.startOAuth(provider.provider, redirectUri);
        window.location.href = res.auth_url;
        return;
      }

      await api.connectIntegration(provider.provider, apiKey);
      setConnected(true);
      setStep('map');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLoadMappings = async () => {
    if (mappingsLoaded) return;
    setLoading(true);
    try {
      const res = await api.getFieldMappings(provider.provider);
      setMappings(res.mappings);
      setMappingsLoaded(true);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLoadPreview = async () => {
    setLoading(true);
    setError(null);
    try {
      // Save mappings first
      if (mappings.length > 0) {
        await api.updateFieldMappings(provider.provider, mappings).catch(() => {});
      }
      const res = await api.previewIntegration(provider.provider);
      setPreviewData(res.preview);
      setPreviewTotal(res.total_available);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setError(null);
    try {
      const res = await api.syncIntegration(provider.provider);
      setSyncResult(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSyncing(false);
    }
  };

  const goNext = () => {
    const nextIdx = stepIndex + 1;
    if (nextIdx < STEPS.length) {
      const nextStep = STEPS[nextIdx].key;
      setStep(nextStep);
      if (nextStep === 'map') handleLoadMappings();
      if (nextStep === 'preview') handleLoadPreview();
    }
  };

  const goBack = () => {
    const prevIdx = stepIndex - 1;
    if (prevIdx >= 0) setStep(STEPS[prevIdx].key);
  };

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-[var(--color-border)]">
          <div>
            <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
              Connect {provider.display_name}
            </h2>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
              {provider.description}
            </p>
          </div>
          <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">
            <X size={18} />
          </button>
        </div>

        {/* Step indicator */}
        <div className="flex items-center gap-1 px-5 py-3 border-b border-[var(--color-border)]">
          {STEPS.map((s, i) => (
            <div key={s.key} className="flex items-center gap-1">
              <div className={`
                w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold
                ${i < stepIndex ? 'bg-green-500/20 text-green-400' :
                  i === stepIndex ? 'bg-[var(--color-accent)]/20 text-[var(--color-accent)]' :
                  'bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]'}
              `}>
                {i < stepIndex ? <Check size={12} /> : i + 1}
              </div>
              <span className={`text-xs ${i === stepIndex ? 'text-[var(--color-text-primary)] font-medium' : 'text-[var(--color-text-muted)]'}`}>
                {s.label}
              </span>
              {i < STEPS.length - 1 && (
                <div className="w-8 h-px bg-[var(--color-border)] mx-1" />
              )}
            </div>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5">
          {error && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-sm text-red-300 flex items-center justify-between">
              <span>{error}</span>
              <button onClick={() => setError(null)} className="text-red-400 text-xs">Dismiss</button>
            </div>
          )}

          {step === 'connect' && (
            <ConnectStep
              provider={provider}
              apiKey={apiKey}
              onApiKeyChange={setApiKey}
              connected={connected}
              loading={loading}
              onConnect={handleConnect}
            />
          )}

          {step === 'map' && (
            <MapStep
              mappings={mappings}
              onMappingsChange={setMappings}
              loading={loading}
            />
          )}

          {step === 'preview' && (
            <PreviewStep
              data={previewData}
              total={previewTotal}
              loading={loading}
            />
          )}

          {step === 'confirm' && (
            <ConfirmStep
              provider={provider}
              mappings={mappings}
              syncing={syncing}
              syncResult={syncResult}
              onSync={handleSync}
              onComplete={onComplete}
            />
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-5 border-t border-[var(--color-border)]">
          <button
            onClick={stepIndex === 0 ? onClose : goBack}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
          >
            <ArrowLeft size={12} /> {stepIndex === 0 ? 'Cancel' : 'Back'}
          </button>

          {step !== 'confirm' && (
            <button
              onClick={step === 'connect' ? handleConnect : goNext}
              disabled={loading || (step === 'connect' && !connected && !apiKey.trim())}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40"
            >
              {loading ? <Loader2 size={12} className="animate-spin" /> : null}
              {step === 'connect' && !connected ? 'Test & Connect' : 'Next'}
              {step !== 'connect' || connected ? <ArrowRight size={12} /> : null}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step components
// ---------------------------------------------------------------------------

function ConnectStep({
  provider,
  apiKey,
  onApiKeyChange,
  connected,
  loading,
  onConnect,
}: {
  provider: ProviderInfo;
  apiKey: string;
  onApiKeyChange: (v: string) => void;
  connected: boolean;
  loading: boolean;
  onConnect: () => void;
}) {
  if (connected) {
    return (
      <div className="text-center py-8">
        <div className="w-12 h-12 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-3">
          <Check size={20} className="text-green-400" />
        </div>
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-1">Connected</h3>
        <p className="text-xs text-[var(--color-text-muted)]">
          {provider.display_name} is connected. Continue to configure field mappings.
        </p>
      </div>
    );
  }

  if (provider.auth_method === 'oauth') {
    return (
      <div className="text-center py-8">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-2">
          Sign in with {provider.display_name}
        </h3>
        <p className="text-xs text-[var(--color-text-muted)] mb-6 max-w-sm mx-auto">
          You'll be redirected to {provider.display_name} to authorize PickPulse Intelligence to access your data.
        </p>
        <button
          onClick={onConnect}
          disabled={loading}
          className="inline-flex items-center gap-2 px-6 py-3 text-sm font-medium rounded-xl bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <ExternalLink size={14} />}
          Connect {provider.display_name}
        </button>
      </div>
    );
  }

  if (provider.auth_method === 'none') {
    return (
      <div className="text-center py-8">
        <Upload size={32} className="mx-auto mb-3 text-[var(--color-text-muted)]" />
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-1">Upload CSV</h3>
        <p className="text-xs text-[var(--color-text-muted)]">
          CSV import is configured through the Datasets page.
        </p>
      </div>
    );
  }

  // API key flow
  return (
    <div className="max-w-sm mx-auto py-4">
      <label className="block text-xs text-[var(--color-text-secondary)] mb-1.5">
        API Key
      </label>
      <input
        type="password"
        value={apiKey}
        onChange={(e) => onApiKeyChange(e.target.value)}
        placeholder="sk-..."
        className="w-full px-3 py-2.5 text-sm bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg text-[var(--color-text-primary)] focus:border-[var(--color-accent)] focus:outline-none"
        onKeyDown={(e) => e.key === 'Enter' && apiKey.trim() && onConnect()}
      />
      <p className="text-[10px] text-[var(--color-text-muted)] mt-2">
        We'll test the connection before saving. Your key is encrypted at rest with AES-256-GCM.
      </p>
    </div>
  );
}

function MapStep({
  mappings,
  onMappingsChange,
  loading,
}: {
  mappings: FieldMapping[];
  onMappingsChange: (m: FieldMapping[]) => void;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 size={20} className="animate-spin text-[var(--color-accent)]" />
      </div>
    );
  }

  const updateMapping = (idx: number, field: keyof FieldMapping, value: string) => {
    const updated = [...mappings];
    updated[idx] = { ...updated[idx], [field]: value };
    onMappingsChange(updated);
  };

  const targetOptions = [
    'name', 'domain', 'arr', 'plan', 'industry', 'company_size', 'seats',
    'monthly_logins', 'support_tickets', 'nps_score', 'days_since_last_login',
    'days_until_renewal', 'created_at',
  ];

  return (
    <div>
      <p className="text-xs text-[var(--color-text-muted)] mb-4">
        Map source fields from your provider to PickPulse account fields.
        Defaults are pre-configured — adjust as needed.
      </p>

      <div className="space-y-2">
        <div className="grid grid-cols-3 gap-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-medium px-1">
          <span>Source Field</span>
          <span>Target Field</span>
          <span>Transform</span>
        </div>

        {mappings.map((m, i) => (
          <div key={i} className="grid grid-cols-3 gap-3">
            <input
              value={m.source_field}
              onChange={(e) => updateMapping(i, 'source_field', e.target.value)}
              className="px-2.5 py-1.5 text-xs bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
            />
            <select
              value={m.target_field}
              onChange={(e) => updateMapping(i, 'target_field', e.target.value)}
              className="px-2.5 py-1.5 text-xs bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
            >
              {targetOptions.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
            <select
              value={m.transform}
              onChange={(e) => updateMapping(i, 'transform', e.target.value)}
              className="px-2.5 py-1.5 text-xs bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
            >
              <option value="direct">Direct</option>
              <option value="to_float">To Float</option>
              <option value="to_int">To Integer</option>
              <option value="date_parse">Parse Date</option>
              <option value="unix_timestamp">Unix Timestamp</option>
              <option value="employee_bucket">Employee Bucket</option>
              <option value="monthly_to_annual">Monthly → Annual</option>
              <option value="cents_to_annual">Cents → Annual</option>
            </select>
          </div>
        ))}
      </div>

      {mappings.length === 0 && (
        <div className="text-center py-8 text-xs text-[var(--color-text-muted)]">
          No field mappings configured. Default mappings will be used.
        </div>
      )}
    </div>
  );
}

function PreviewStep({
  data,
  total,
  loading,
}: {
  data: any[];
  total: number;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 size={20} className="animate-spin text-[var(--color-accent)]" />
        <span className="ml-2 text-xs text-[var(--color-text-muted)]">Loading preview...</span>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="text-center py-8 text-xs text-[var(--color-text-muted)]">
        No records found. Check your connection and field mappings.
      </div>
    );
  }

  const fields = ['name', 'external_id', 'source', 'email', 'plan', 'arr', 'industry'];

  return (
    <div>
      <p className="text-xs text-[var(--color-text-muted)] mb-3">
        Showing {data.length} of {total} records with current mapping.
      </p>
      <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-[var(--color-bg-tertiary)]">
              {fields.map((f) => (
                <th key={f} className="text-left py-2 px-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-medium">
                  {f}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i} className="border-t border-[var(--color-border)]/50">
                {fields.map((f) => (
                  <td key={f} className="py-2 px-3 text-[var(--color-text-secondary)]">
                    {row[f] != null ? String(row[f]) : '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ConfirmStep({
  provider,
  mappings,
  syncing,
  syncResult,
  onSync,
  onComplete,
}: {
  provider: ProviderInfo;
  mappings: FieldMapping[];
  syncing: boolean;
  syncResult: any;
  onSync: () => void;
  onComplete: () => void;
}) {
  if (syncResult) {
    return (
      <div className="text-center py-6">
        <div className="w-12 h-12 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-3">
          <Check size={20} className="text-green-400" />
        </div>
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-1">
          Sync Complete
        </h3>
        <p className="text-xs text-[var(--color-text-muted)] mb-4">
          {syncResult.accounts_synced} accounts and {syncResult.signals_synced} signals synced.
        </p>
        {syncResult.errors?.length > 0 && (
          <div className="text-xs text-red-400 mb-4">
            {syncResult.errors.join(', ')}
          </div>
        )}
        <button
          onClick={onComplete}
          className="px-6 py-2.5 text-sm font-medium rounded-xl bg-[var(--color-accent)] text-white hover:opacity-90"
        >
          Done
        </button>
      </div>
    );
  }

  return (
    <div className="py-4">
      <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-4">
        Ready to Sync
      </h3>

      <div className="space-y-3 mb-6">
        <div className="flex items-center justify-between px-4 py-3 bg-[var(--color-bg-tertiary)] rounded-lg">
          <span className="text-xs text-[var(--color-text-muted)]">Provider</span>
          <span className="text-xs text-[var(--color-text-primary)] font-medium">{provider.display_name}</span>
        </div>
        <div className="flex items-center justify-between px-4 py-3 bg-[var(--color-bg-tertiary)] rounded-lg">
          <span className="text-xs text-[var(--color-text-muted)]">Auth Method</span>
          <span className="text-xs text-[var(--color-text-primary)] font-medium capitalize">{provider.auth_method.replace('_', ' ')}</span>
        </div>
        <div className="flex items-center justify-between px-4 py-3 bg-[var(--color-bg-tertiary)] rounded-lg">
          <span className="text-xs text-[var(--color-text-muted)]">Field Mappings</span>
          <span className="text-xs text-[var(--color-text-primary)] font-medium">{mappings.length} fields</span>
        </div>
      </div>

      <button
        onClick={onSync}
        disabled={syncing}
        className="w-full flex items-center justify-center gap-2 px-6 py-3 text-sm font-medium rounded-xl bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40"
      >
        {syncing ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} />}
        {syncing ? 'Syncing...' : 'Start Initial Sync'}
      </button>
    </div>
  );
}

export default IntegrationWizard;
