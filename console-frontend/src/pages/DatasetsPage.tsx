import { useCallback, useState } from 'react';
import { Upload, Database, CheckCircle2, AlertCircle, Info, Briefcase, AlertTriangle, Building2 } from 'lucide-react';
import { api, type UploadResponse } from '../lib/api';
import { useDataset } from '../lib/DatasetContext';

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

export function DatasetsPage({ embedded }: { embedded?: boolean } = {}) {
  const [loading, setLoading] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState('');
  const { dataset, refresh } = useDataset();

  const loadSample = useCallback(async (variant: string) => {
    setLoading(variant);
    setError('');
    try {
      const res = await api.loadSample(variant);
      setResult(res);
      refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(null);
    }
  }, [refresh]);

  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading('upload');
    setError('');
    try {
      const res = await api.uploadDataset(file);
      setResult(res);
      refresh();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(null);
    }
  }, [refresh]);

  const v = result?.validation;

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
          <p className="text-sm text-[var(--color-text-secondary)] mt-1">Connect your account data or explore with our pre-built demo datasets</p>
        </div>
      )}

      {/* Current dataset indicator */}
      {dataset && (
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-4 mb-6 flex items-center gap-4 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <Database size={18} className="text-[var(--color-success)] shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium truncate">{dataset.name}</div>
            <div className="text-xs text-[var(--color-text-muted)]">
              {dataset.rows.toLocaleString()} rows, {dataset.columns} columns
              {dataset.is_demo && ' — sample data'}
            </div>
          </div>
          <span className="text-xs text-[var(--color-text-muted)] shrink-0">
            Loaded {new Date(dataset.loaded_at).toLocaleString()}
          </span>
        </div>
      )}

      {/* Demo Dataset Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
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
                className="px-4 py-2 bg-[var(--color-accent)] text-white rounded-xl text-xs font-medium hover:bg-[var(--color-accent-glow)] transition-colors disabled:opacity-50 shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
              >
                {isLoading ? 'Loading...' : 'Load'}
              </button>
            </div>
          );
        })}
      </div>

      {/* Upload CSV */}
      <label className="block bg-white border border-dashed border-[var(--color-border)] rounded-2xl p-5 mb-8 text-center cursor-pointer hover:border-[var(--color-accent)] transition-colors shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
        <Upload size={24} className="mx-auto text-[var(--color-text-secondary)] mb-2" />
        <h3 className="font-semibold text-sm mb-1">Upload Your Own CSV</h3>
        <p className="text-xs text-[var(--color-text-secondary)] mb-3">
          Customer churn data with renewal fields
        </p>
        <input type="file" accept=".csv" className="hidden" onChange={handleUpload} disabled={loading !== null} />
        <span className="inline-block px-4 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-xl text-xs">
          {loading === 'upload' ? 'Uploading...' : 'Choose File'}
        </span>
      </label>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-4 mb-6 flex items-start gap-3">
          <AlertCircle size={18} className="text-[var(--color-danger)] mt-0.5 shrink-0" />
          <p className="text-sm text-[var(--color-danger)]">{error}</p>
        </div>
      )}

      {v && (
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <div className="flex items-center gap-2 mb-4">
            {v.valid ? (
              <CheckCircle2 size={18} className="text-[var(--color-success)]" />
            ) : (
              <AlertCircle size={18} className="text-[var(--color-danger)]" />
            )}
            <h3 className="font-semibold">
              {v.valid ? 'Validation Passed' : 'Validation Issues'}
            </h3>
            <span className="text-xs text-[var(--color-text-muted)] ml-auto">
              {v.n_rows.toLocaleString()} rows, {v.n_columns} columns
            </span>
          </div>

          {v.errors.length > 0 && (
            <div className="mb-3 space-y-1">
              {v.errors.map((e, i) => (
                <div key={i} className="text-sm text-[var(--color-danger)] flex items-center gap-2">
                  <AlertCircle size={14} /> {e}
                </div>
              ))}
            </div>
          )}

          {v.warnings.length > 0 && (
            <div className="mb-3 space-y-1">
              {v.warnings.map((w, i) => (
                <div key={i} className="text-sm text-[var(--color-warning)] flex items-center gap-2">
                  <Info size={14} /> {w}
                </div>
              ))}
            </div>
          )}

          <details className="mt-3">
            <summary className="text-xs text-[var(--color-text-secondary)] cursor-pointer hover:text-[var(--color-text-primary)]">
              Column Details ({v.columns.length})
            </summary>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-[var(--color-text-muted)] uppercase tracking-wider border-b border-[var(--color-border)]">
                    <th className="py-2 pr-4">Column</th>
                    <th className="py-2 pr-4">Type</th>
                    <th className="py-2 pr-4 text-right">Missing</th>
                    <th className="py-2 pr-4 text-right">Unique</th>
                    <th className="py-2">Samples</th>
                  </tr>
                </thead>
                <tbody>
                  {v.columns.map((c, i) => (
                    <tr key={c.name} className={`border-b border-[var(--color-border)]/50 ${i % 2 === 1 ? 'bg-[var(--color-bg-primary)]' : ''}`}>
                      <td className="py-2 pr-4 font-mono text-xs">{c.name}</td>
                      <td className="py-2 pr-4">
                        <span className="px-2 py-0.5 bg-[var(--color-bg-primary)] rounded-lg text-xs">{c.dtype}</span>
                      </td>
                      <td className="py-2 pr-4 text-right">
                        {c.missing_count > 0 ? (
                          <span className="text-[var(--color-warning)]">{c.missing_pct}%</span>
                        ) : (
                          <span className="text-[var(--color-text-muted)]">0</span>
                        )}
                      </td>
                      <td className="py-2 pr-4 text-right">{c.n_unique}</td>
                      <td className="py-2 text-[var(--color-text-muted)] truncate max-w-40 text-xs">
                        {c.sample_values.join(', ')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          {Object.keys(v.label_distribution).length > 0 && (
            <div className="mt-4 flex items-center gap-4 text-sm">
              <span className="text-[var(--color-text-secondary)]">Label Distribution:</span>
              {Object.entries(v.label_distribution).map(([k, n]) => (
                <span key={k} className="px-2 py-1 bg-[var(--color-bg-primary)] rounded-lg font-mono text-xs">
                  {k === '0' ? 'Retained' : 'Churned'}: {n}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
