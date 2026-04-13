import { useCallback, useState } from 'react';
import { Upload, Database, Briefcase, AlertTriangle, Building2, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { api, type StagedUploadResponse, type ReadinessReport, type UploadResponse } from '../lib/api';
import { useDataset } from '../lib/DatasetContext';
import { MappingReviewStep } from '../components/MappingReviewStep';
import { ReadinessReportCard } from '../components/ReadinessReportCard';

const DEMO_VARIANTS = [
  {
    key: 'balanced',
    label: 'Balanced Demo',
    description: 'Realistic mixed SaaS portfolio',
    accounts: '~2,000 accounts',
    icon: Briefcase,
    accent: 'var(--color-accent)',
  },
  {
    key: 'high_risk',
    label: 'High-Risk Demo',
    description: 'Curated urgent churn scenarios',
    accounts: '~1,000 accounts',
    icon: AlertTriangle,
    accent: 'var(--color-danger)',
  },
  {
    key: 'enterprise',
    label: 'Enterprise Demo',
    description: 'Large portfolio, higher ARR exposure',
    accounts: '~4,000 accounts',
    icon: Building2,
    accent: 'var(--color-success)',
  },
] as const;

// Upload flow step
type Step = 'idle' | 'mapping' | 'confirmed';

export function DatasetsPage({ embedded }: { embedded?: boolean } = {}) {
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [step, setStep] = useState<Step>('idle');
  const [showSampleData, setShowSampleData] = useState(false);

  // Upload state
  const [staged, setStaged] = useState<StagedUploadResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessReport | null>(null);

  // Sample data state (old ValidationInfo format)
  const [sampleResult, setSampleResult] = useState<UploadResponse | null>(null);

  const { dataset, refresh } = useDataset();

  // ---------------------------------------------------------------------------
  // Sample data load (unchanged flow)
  // ---------------------------------------------------------------------------
  const loadSample = useCallback(async (variant: string) => {
    setLoading(variant);
    setError('');
    setSampleResult(null);
    setStep('idle');
    setStaged(null);
    setReadiness(null);
    try {
      const res = await api.loadSample(variant);
      setSampleResult(res);
      refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(null);
    }
  }, [refresh]);

  // ---------------------------------------------------------------------------
  // Stage 1: Upload CSV → get mapping suggestion
  // ---------------------------------------------------------------------------
  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // Reset input so same file can be re-selected
    e.target.value = '';

    setLoading('upload');
    setError('');
    setSampleResult(null);
    setStaged(null);
    setReadiness(null);
    setStep('idle');

    try {
      const res = await api.uploadDataset(file);
      setStaged(res);
      setStep('mapping');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(null);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Stage 2: Confirm mapping → normalize + register
  // ---------------------------------------------------------------------------
  const handleMappingConfirmed = useCallback((report: ReadinessReport) => {
    setReadiness(report);
    setStep('confirmed');
    refresh();
  }, [refresh]);

  const handleMappingCancel = useCallback(() => {
    setStaged(null);
    setStep('idle');
  }, []);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  const v = sampleResult?.validation;

  return (
    <div>
      {!embedded && (
        <div className="mb-8">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">Data Sources</h1>
            {dataset?.is_demo && (
              <span
                className="px-2.5 py-1 bg-amber-50 border border-amber-200 rounded-lg text-[10px] font-bold tracking-widest uppercase text-[var(--color-warning)]"
                title="Illustrative metrics from a sample dataset. Upload your own data for production-grade insights."
              >
                Sample Data
              </span>
            )}
          </div>
          <p className="text-sm text-[var(--color-text-secondary)] mt-1">
            Connect your account data or explore with our pre-built demo datasets
          </p>
        </div>
      )}

      {/* Current dataset indicator */}
      {dataset && (
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-4 mb-6 flex items-center gap-4 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <Database size={18} className="text-[var(--color-success)] shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium truncate">{dataset.name}</div>
            <div className="text-xs text-[var(--color-text-muted)]">
              {dataset.rows != null ? `${dataset.rows.toLocaleString()} rows, ` : ''}{dataset.columns != null ? `${dataset.columns} columns` : ''}
              {dataset.is_demo && ' — sample data'}
            </div>
          </div>
          <span className="text-xs text-[var(--color-text-muted)] shrink-0">
            {dataset.loaded_at ? `Loaded ${new Date(dataset.loaded_at).toLocaleString()}` : ''}
          </span>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Step: mapping review                                                */}
      {/* ------------------------------------------------------------------ */}
      {step === 'mapping' && staged && (
        <div className="mb-6">
          <MappingReviewStep
            rawPath={staged.raw_path}
            filename={staged.filename}
            sourceColumns={staged.source_columns}
            suggestion={staged.mapping_suggestion}
            onConfirmed={handleMappingConfirmed}
            onCancel={handleMappingCancel}
          />
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Step: confirmed — show readiness report                             */}
      {/* ------------------------------------------------------------------ */}
      {step === 'confirmed' && readiness && (
        <div className="mb-6">
          <ReadinessReportCard report={readiness} />
          <button
            onClick={() => { setStep('idle'); setReadiness(null); }}
            className="mt-3 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
          >
            Upload a different file
          </button>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Idle state: CSV upload primary, demo datasets secondary             */}
      {/* ------------------------------------------------------------------ */}
      {step === 'idle' && (
        <>
          {/* Upload CSV — primary action */}
          <label className="block bg-white border border-dashed border-[var(--color-border)] rounded-2xl p-5 mb-3 text-center cursor-pointer hover:border-[var(--color-accent)] transition-colors shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
            <Upload size={24} className="mx-auto text-[var(--color-text-secondary)] mb-2" />
            <h3 className="font-semibold text-sm mb-1">Upload Your Own CSV</h3>
            <p className="text-xs text-[var(--color-text-secondary)] mb-3">
              Any customer / account dataset — PickPulse will detect and map your columns automatically.
            </p>
            <input
              type="file"
              accept=".csv"
              className="hidden"
              onChange={handleUpload}
              disabled={loading !== null}
            />
            <span className="inline-block px-4 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-xl text-xs">
              {loading === 'upload' ? 'Uploading...' : 'Choose File'}
            </span>
          </label>

          {/* Schema hint */}
          <div className="mb-6 px-4 py-3 bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-xl">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1.5">
              Key fields PickPulse recognizes
            </p>
            <div className="flex flex-wrap gap-1.5 mb-1.5">
              {['account_id / customer_id', 'snapshot_date / date', 'churned / canceled', 'arr / mrr', 'renewal_date', 'login_days_30d', 'seats_purchased'].map(col => (
                <code key={col} className="text-[11px] px-2 py-0.5 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded text-[var(--color-accent)]">
                  {col}
                </code>
              ))}
            </div>
            <p className="text-[10px] text-[var(--color-text-muted)]">
              Column names are matched automatically. You'll review and adjust the mapping before anything is processed.
            </p>
          </div>

          {/* Sample data — secondary, collapsed by default */}
          <div className="mb-6">
            <button
              onClick={() => setShowSampleData((v) => !v)}
              className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
            >
              {showSampleData ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              Use sample data instead
            </button>

            {showSampleData && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
                {DEMO_VARIANTS.map((variant) => {
                  const Icon = variant.icon;
                  const isLoading = loading === variant.key;
                  return (
                    <div
                      key={variant.key}
                      className="bg-white border border-[var(--color-border)] rounded-2xl p-5 flex flex-col items-center text-center shadow-[0_1px_3px_rgba(0,0,0,0.08)]"
                    >
                      <Icon size={24} style={{ color: variant.accent }} className="mb-3" />
                      <h3 className="font-semibold text-sm mb-1">{variant.label}</h3>
                      <p className="text-[10px] text-[var(--color-text-muted)] mb-1">{variant.accounts}</p>
                      <p className="text-xs text-[var(--color-text-secondary)] mb-4">{variant.description}</p>
                      <button
                        onClick={() => loadSample(variant.key)}
                        disabled={loading !== null}
                        className="px-4 py-2 bg-[var(--color-accent)] text-white rounded-xl text-xs font-medium hover:bg-[var(--color-accent-glow)] transition-colors disabled:opacity-50"
                      >
                        {isLoading ? 'Loading...' : 'Load'}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-4 mb-6 flex items-start gap-3">
          <AlertCircle size={18} className="text-[var(--color-danger)] mt-0.5 shrink-0" />
          <p className="text-sm text-[var(--color-danger)]">{error}</p>
        </div>
      )}

      {/* Sample data validation result (old flow) */}
      {v && step === 'idle' && (
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <div className="flex items-center gap-2 mb-2">
            {v.valid
              ? <span className="text-xs font-semibold text-[var(--color-success)]">Sample data loaded</span>
              : <span className="text-xs font-semibold text-[var(--color-warning)]">Loaded with warnings</span>
            }
            <span className="text-xs text-[var(--color-text-muted)] ml-auto">
              {v.n_rows.toLocaleString()} rows · {v.n_columns} columns
            </span>
          </div>
          {v.warnings.length > 0 && (
            <ul className="space-y-1 mt-1">
              {v.warnings.map((w, i) => (
                <li key={i} className="text-xs text-amber-700 flex items-start gap-1.5">
                  <span className="shrink-0 mt-0.5">•</span>{w}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
