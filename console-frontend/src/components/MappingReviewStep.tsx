import { useEffect, useState } from 'react';
import { CheckCircle2, AlertCircle, Info, ChevronDown, Loader2 } from 'lucide-react';
import { api, type CanonicalSchemaField, type MappingSuggestion, type ReadinessReport } from '../lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface Props {
  rawPath: string;
  filename: string;
  sourceColumns: string[];
  suggestion: MappingSuggestion;
  onConfirmed: (readiness: ReadinessReport) => void;
  onCancel: () => void;
}

// Canonical fields to show in the mapping UI (ordered by importance)
const FIELD_ORDER = [
  'account_id', 'snapshot_date', 'churned',
  'arr', 'mrr', 'renewal_date', 'days_until_renewal',
  'contract_start_date', 'login_days_30d', 'seats_purchased',
  'seats_active_30d', 'support_tickets_30d', 'nps_score',
  'plan_type', 'auto_renew_flag',
  'company_name', 'csm_owner', 'industry', 'region',
];

const CONFIDENCE_STYLES: Record<string, string> = {
  HIGH:   'bg-green-50 text-green-700 border-green-200',
  MEDIUM: 'bg-amber-50 text-amber-700 border-amber-200',
  LOW:    'bg-red-50 text-red-600 border-red-200',
  NONE:   'bg-gray-50 text-gray-400 border-gray-200',
};

const CONFIDENCE_LABELS: Record<string, string> = {
  HIGH:   'Auto-detected',
  MEDIUM: 'Likely match',
  LOW:    'Suggested — confirm',
  NONE:   'Not found',
};

const MODE_STYLES: Record<string, { bar: string; text: string; icon: 'ok' | 'warn' | 'block' }> = {
  TRAINING_READY:    { bar: 'bg-green-500',  text: 'text-green-700',  icon: 'ok' },
  TRAINING_DEGRADED: { bar: 'bg-amber-400',  text: 'text-amber-700',  icon: 'warn' },
  ANALYSIS_READY:    { bar: 'bg-blue-400',   text: 'text-blue-700',   icon: 'warn' },
  PARTIAL:           { bar: 'bg-orange-400', text: 'text-orange-700', icon: 'warn' },
  BLOCKED:           { bar: 'bg-red-500',    text: 'text-red-700',    icon: 'block' },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export function MappingReviewStep({ rawPath, filename, sourceColumns, suggestion, onConfirmed, onCancel }: Props) {
  const [schemaFields, setSchemaFields] = useState<CanonicalSchemaField[]>([]);
  const [mappings, setMappings] = useState<Record<string, string | null>>({});
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState('');

  // Initialise mappings from the suggestion.
  // LOW confidence = heuristic guess — don't pre-populate, require explicit user selection.
  useEffect(() => {
    const initial: Record<string, string | null> = {};
    for (const [canonical, col] of Object.entries(suggestion.suggested)) {
      const conf = suggestion.confidence[canonical];
      initial[canonical] = conf === 'LOW' ? null : (col ?? null);
    }
    setMappings(initial);
  }, [suggestion]);

  // Load schema field metadata
  useEffect(() => {
    api.canonicalSchema().then(r => setSchemaFields(r.fields)).catch(() => {});
  }, []);

  const fieldMeta: Record<string, CanonicalSchemaField> = Object.fromEntries(
    schemaFields.map(f => [f.name, f])
  );

  const dropdownOptions = ['', ...sourceColumns]; // '' = skip / not in dataset

  const handleConfirm = async () => {
    setConfirming(true);
    setError('');
    try {
      const res = await api.confirmMapping(rawPath, filename, mappings);
      onConfirmed(res.readiness);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setConfirming(false);
    }
  };

  // Derive a live preview of the mode based on current mappings
  const hasAccountId = !!mappings['account_id'];
  const hasChurned = !!mappings['churned'];
  const hasSnapshotDate = !!mappings['snapshot_date'];
  const featureCount = Object.entries(mappings).filter(
    ([k, v]) => v && !['account_id', 'snapshot_date', 'churned'].includes(k)
  ).length;

  let liveMode = 'BLOCKED';
  if (!hasAccountId) liveMode = 'BLOCKED';
  else if (featureCount < 2) liveMode = 'BLOCKED';
  else if (!hasChurned) liveMode = 'ANALYSIS_READY';
  else if (!hasSnapshotDate) liveMode = 'TRAINING_DEGRADED';
  else liveMode = 'TRAINING_READY';

  const modeStyle = MODE_STYLES[liveMode] ?? MODE_STYLES.BLOCKED;

  return (
    <div className="bg-white border border-[var(--color-border)] rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.08)] overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-[var(--color-border)]">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-sm">Map Your Columns</h3>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
              {filename} · {sourceColumns.length} source columns
            </p>
          </div>
          <button
            onClick={onCancel}
            className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] px-3 py-1.5 rounded-lg border border-[var(--color-border)]"
          >
            Cancel
          </button>
        </div>

        {/* Live mode badge */}
        <div className={`mt-3 flex items-center gap-2 text-xs font-medium ${modeStyle.text}`}>
          <div className={`w-2 h-2 rounded-full ${modeStyle.bar}`} />
          {liveMode === 'TRAINING_READY'    && 'Training-Ready'}
          {liveMode === 'TRAINING_DEGRADED' && 'Training-Ready (random split — no date column)'}
          {liveMode === 'ANALYSIS_READY'    && 'Analysis Mode — no churn label found'}
          {liveMode === 'PARTIAL'           && 'Partial — map more fields to proceed'}
          {liveMode === 'BLOCKED'           && 'Blocked — map account_id and at least 2 features'}
          <span className="text-[var(--color-text-muted)] font-normal ml-1">
            · {featureCount} feature{featureCount !== 1 ? 's' : ''} mapped
          </span>
        </div>
      </div>

      {/* Mapping table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)] bg-[var(--color-bg-primary)]">
              <th className="px-6 py-3 w-48">PickPulse Field</th>
              <th className="px-4 py-3">Your Column</th>
              <th className="px-4 py-3 w-40">Detection</th>
              <th className="px-4 py-3 w-24">Required</th>
            </tr>
          </thead>
          <tbody>
            {FIELD_ORDER.map((canonical, i) => {
              const meta = fieldMeta[canonical];
              const currentMapping = mappings[canonical] ?? null;
              const conf = suggestion.confidence[canonical] ?? 'NONE';
              const isRequired = meta?.required_for_training || meta?.required_for_analysis;
              const isMapped = !!currentMapping;
              const isDisplayOnly = meta?.display_only;
              const derivableFrom = meta?.derivable_from ?? [];

              // Section divider before display-only fields
              const isFirstDisplay = canonical === 'company_name';

              return (
                <>
                  {isFirstDisplay && (
                    <tr key={`${canonical}-divider`} className="bg-[var(--color-bg-primary)]">
                      <td colSpan={4} className="px-6 py-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                        Display Fields — not used in model
                      </td>
                    </tr>
                  )}
                  <tr
                    key={canonical}
                    className={`border-b border-[var(--color-border)]/50 ${i % 2 === 0 ? '' : 'bg-[var(--color-bg-primary)]/40'}`}
                  >
                    {/* Canonical field name */}
                    <td className="px-6 py-3">
                      <code className="text-xs text-[var(--color-accent)]">{canonical}</code>
                      {derivableFrom.length > 0 && !isMapped && (
                        <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5">
                          derivable from {derivableFrom.join(', ')}
                        </div>
                      )}
                      {meta?.description && (
                        <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5 max-w-[160px] leading-tight">
                          {meta.description}
                        </div>
                      )}
                    </td>

                    {/* Dropdown */}
                    <td className="px-4 py-3">
                      <div className="relative inline-block w-full max-w-[220px]">
                        <select
                          value={currentMapping ?? ''}
                          onChange={e => setMappings(prev => ({
                            ...prev,
                            [canonical]: e.target.value || null,
                          }))}
                          className="w-full appearance-none bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg px-3 py-1.5 pr-8 text-xs text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)] cursor-pointer"
                        >
                          <option value="">— Skip / Not in dataset —</option>
                          {dropdownOptions.filter(Boolean).map(col => (
                            <option key={col} value={col}>{col}</option>
                          ))}
                        </select>
                        <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] pointer-events-none" />
                      </div>
                    </td>

                    {/* Confidence badge */}
                    <td className="px-4 py-3">
                      {isMapped ? (
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 border rounded text-[10px] font-medium ${CONFIDENCE_STYLES[conf]}`}>
                          {CONFIDENCE_LABELS[conf] ?? conf}
                        </span>
                      ) : (
                        <span className="text-[10px] text-[var(--color-text-muted)]">
                          {isDisplayOnly ? 'Optional' : derivableFrom.length > 0 ? 'Will derive' : '—'}
                        </span>
                      )}
                    </td>

                    {/* Required badge */}
                    <td className="px-4 py-3">
                      {isRequired ? (
                        isMapped ? (
                          <CheckCircle2 size={14} className="text-[var(--color-success)]" />
                        ) : (
                          <AlertCircle size={14} className="text-[var(--color-danger)]" />
                        )
                      ) : (
                        <span className="text-[10px] text-[var(--color-text-muted)]">Optional</span>
                      )}
                    </td>
                  </tr>
                </>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Unmapped source columns */}
      {suggestion.unmapped_source_cols.length > 0 && (
        <div className="px-6 py-3 border-t border-[var(--color-border)] bg-[var(--color-bg-primary)]">
          <div className="flex items-center gap-1.5 mb-1.5">
            <Info size={12} className="text-[var(--color-text-muted)]" />
            <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
              Unrecognized columns ({suggestion.unmapped_source_cols.length})
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {suggestion.unmapped_source_cols.map(col => (
              <code key={col} className="text-[10px] px-1.5 py-0.5 bg-white border border-[var(--color-border)] rounded text-[var(--color-text-muted)]">
                {col}
              </code>
            ))}
          </div>
          <p className="text-[10px] text-[var(--color-text-muted)] mt-1.5">
            These columns weren't recognized. You can assign them above using the dropdowns.
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mx-6 mb-4 mt-2 flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-xl">
          <AlertCircle size={14} className="text-[var(--color-danger)] mt-0.5 shrink-0" />
          <p className="text-xs text-[var(--color-danger)]">{error}</p>
        </div>
      )}

      {/* Footer */}
      <div className="px-6 py-4 border-t border-[var(--color-border)] flex items-center justify-between">
        <p className="text-[11px] text-[var(--color-text-muted)]">
          Review your column mapping above, then confirm to proceed.
        </p>
        <button
          onClick={handleConfirm}
          disabled={confirming || liveMode === 'BLOCKED'}
          className="flex items-center gap-2 px-5 py-2 bg-[var(--color-accent)] text-white rounded-xl text-sm font-medium hover:bg-[var(--color-accent-glow)] transition-colors disabled:opacity-50 shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
        >
          {confirming && <Loader2 size={14} className="animate-spin" />}
          {confirming ? 'Normalizing...' : 'Confirm Mapping'}
        </button>
      </div>
    </div>
  );
}
