import { useCallback, useState } from 'react';
import { Upload, Database, CheckCircle2, AlertCircle, Info } from 'lucide-react';
import { api, type UploadResponse } from '../lib/api';
import { useDataset } from '../lib/DatasetContext';

export function DatasetsPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState('');
  const { dataset, refresh } = useDataset();

  const loadSample = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.loadSample();
      setResult(res);
      refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [refresh]);

  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setError('');
    try {
      const res = await api.uploadDataset(file);
      setResult(res);
      refresh();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [refresh]);

  const v = result?.validation;

  return (
    <div>
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Datasets</h1>
          {dataset?.is_demo && (
            <span
              className="px-2.5 py-1 bg-[var(--color-warning)]/10 border border-[var(--color-warning)]/25 rounded-lg text-[10px] font-bold tracking-widest uppercase text-[var(--color-warning)]"
              title="Illustrative metrics from a sample dataset. Upload your own data for production-grade insights."
            >
              Sample Data
            </span>
          )}
        </div>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">Connect your account data or explore with our pre-built sample dataset</p>
      </div>

      {/* Current dataset indicator */}
      {dataset && (
        <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-4 mb-6 flex items-center gap-4 shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
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

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-6 flex flex-col items-center justify-center text-center shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
          <Database size={32} className="text-[var(--color-accent)] mb-3" />
          <h3 className="font-semibold mb-2">Load Sample Dataset</h3>
          <p className="text-xs text-[var(--color-text-secondary)] mb-4">
            2,000 synthetic customer accounts with renewal data
          </p>
          <button
            onClick={loadSample}
            disabled={loading}
            className="px-5 py-2.5 bg-[var(--color-accent)] text-white rounded-xl text-sm font-medium hover:bg-[var(--color-accent-glow)] transition-colors disabled:opacity-50 shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
          >
            {loading ? 'Loading...' : 'Load Sample'}
          </button>
        </div>

        <label className="bg-[var(--color-bg-card)] border border-dashed border-[var(--color-border-bright)] rounded-2xl p-6 flex flex-col items-center justify-center text-center cursor-pointer hover:border-[var(--color-accent)] transition-colors shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
          <Upload size={32} className="text-[var(--color-text-secondary)] mb-3" />
          <h3 className="font-semibold mb-2">Upload CSV</h3>
          <p className="text-xs text-[var(--color-text-secondary)] mb-4">
            Your customer churn data with renewal fields
          </p>
          <input type="file" accept=".csv" className="hidden" onChange={handleUpload} />
          <span className="px-5 py-2.5 bg-[rgba(255,255,255,0.06)] border border-[var(--color-border)] rounded-xl text-sm">
            Choose File
          </span>
        </label>
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-800/40 rounded-2xl p-4 mb-6 flex items-start gap-3">
          <AlertCircle size={18} className="text-[var(--color-danger)] mt-0.5 shrink-0" />
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      {v && (
        <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
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
                    <tr key={c.name} className={`border-b border-[var(--color-border)]/30 ${i % 2 === 1 ? 'bg-[rgba(255,255,255,0.03)]' : ''}`}>
                      <td className="py-2 pr-4 font-mono text-xs">{c.name}</td>
                      <td className="py-2 pr-4">
                        <span className="px-2 py-0.5 bg-[rgba(255,255,255,0.06)] rounded-lg text-xs">{c.dtype}</span>
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
                <span key={k} className="px-2 py-1 bg-[rgba(255,255,255,0.06)] rounded-lg font-mono text-xs">
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
