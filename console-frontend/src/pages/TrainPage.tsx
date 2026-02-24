import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Brain, CheckCircle2, Database, Loader2 } from 'lucide-react';
import { api, isNoDatasetError, type TrainResponse } from '../lib/api';
import { useDataset } from '../lib/DatasetContext';

export function TrainPage() {
  const [valFrac, setValFrac] = useState(0.2);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TrainResponse | null>(null);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const { dataset } = useDataset();

  const handleTrain = async () => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await api.train(valFrac);
      setResult(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const noDataset = !dataset || (error && isNoDatasetError(error));
  const realError = error && !isNoDatasetError(error);
  const meta = result?.metadata;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Train Model</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">Build a calibrated churn prediction model from your account data</p>
      </div>

      {/* No dataset guidance — neutral, not an error */}
      {noDataset && (
        <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-8 mb-8 text-center shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
          <Database size={32} className="mx-auto mb-3 text-[var(--color-text-muted)]" />
          <h3 className="font-semibold mb-2">No dataset loaded</h3>
          <p className="text-sm text-[var(--color-text-secondary)] mb-5 max-w-md mx-auto">
            Load a sample dataset or upload your own account data before training the model.
          </p>
          <button
            onClick={() => navigate('/datasets')}
            className="px-5 py-2.5 bg-[var(--color-accent)] text-white rounded-xl text-sm font-medium hover:bg-[var(--color-accent-glow)] transition-all shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
          >
            Go to Datasets
          </button>
        </div>
      )}

      {!noDataset && (
        <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
          <div className="flex items-center gap-6 mb-5">
            <div>
              <label className="text-xs text-[var(--color-text-secondary)] block mb-1" title="Percentage of data held out for unbiased performance evaluation after training.">Validation Holdout</label>
              <select
                value={valFrac}
                onChange={(e) => setValFrac(Number(e.target.value))}
                className="bg-[rgba(255,255,255,0.06)] border border-[var(--color-border)] rounded-xl px-3 py-2 text-sm"
              >
                <option value={0.1}>10%</option>
                <option value={0.2}>20% (Recommended)</option>
                <option value={0.3}>30%</option>
              </select>
            </div>
          </div>

          <button
            onClick={handleTrain}
            disabled={loading}
            className="flex items-center gap-2 px-6 py-2.5 bg-[var(--color-accent)] text-white rounded-xl font-medium hover:bg-[var(--color-accent-glow)] transition-all disabled:opacity-50 shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
          >
            {loading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Training...
              </>
            ) : (
              <>
                <Brain size={16} />
                Train Churn Model
              </>
            )}
          </button>
        </div>
      )}

      {realError && (
        <div className="bg-red-900/20 border border-red-800/40 rounded-2xl p-4 mb-6">
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      {meta && (
        <div className="space-y-6">
          <div className="bg-[var(--color-bg-card)] border border-[var(--color-success)]/30 rounded-2xl p-6 shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
            <div className="flex items-center gap-2 mb-4">
              <CheckCircle2 size={18} className="text-[var(--color-success)]" />
              <h3 className="font-semibold">Training Complete</h3>
            </div>
            <dl className="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm">
              <div>
                <dt className="text-[var(--color-text-muted)] text-xs mb-1">Version</dt>
                <dd className="font-mono text-lg font-bold text-[var(--color-accent-glow)]">{meta.version}</dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)] text-xs mb-1">Model Type</dt>
                <dd className="text-lg">{meta.model_type}</dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)] text-xs mb-1">Train Rows</dt>
                <dd className="text-lg">{meta.n_train?.toLocaleString()}</dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)] text-xs mb-1">Val Rows</dt>
                <dd className="text-lg">{meta.n_val?.toLocaleString()}</dd>
              </div>
            </dl>
          </div>

          {meta.val_metrics && (
            <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
              <h3 className="font-semibold mb-4 text-sm">Validation Metrics</h3>
              <dl className="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm">
                <div>
                  <dt className="text-[var(--color-text-muted)] text-xs mb-1">AUC</dt>
                  <dd className="text-2xl font-bold text-[var(--color-success)]">{meta.val_metrics.auc}</dd>
                </div>
                <div>
                  <dt className="text-[var(--color-text-muted)] text-xs mb-1">PR-AUC</dt>
                  <dd className="text-2xl font-bold">{meta.val_metrics.pr_auc}</dd>
                </div>
                <div>
                  <dt className="text-[var(--color-text-muted)] text-xs mb-1">Brier Score</dt>
                  <dd className="text-2xl font-bold">{meta.val_metrics.brier}</dd>
                </div>
                <div>
                  <dt className="text-[var(--color-text-muted)] text-xs mb-1">Log Loss</dt>
                  <dd className="text-2xl font-bold">{meta.val_metrics.logloss}</dd>
                </div>
              </dl>
            </div>
          )}

          {meta.feature_importance && (
            <details className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
              <summary className="font-semibold text-sm cursor-pointer">
                Feature Importance ({meta.feature_importance.length} features)
              </summary>
              <div className="mt-4 space-y-2">
                {meta.feature_importance.slice(0, 15).map((f: any) => (
                  <div key={f.feature} className="flex items-center gap-3 text-sm">
                    <span className="font-mono w-48 truncate text-[var(--color-text-secondary)] text-xs">{f.feature}</span>
                    <div className="flex-1 h-2.5 bg-[rgba(255,255,255,0.06)] rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.min(100, Math.abs(f.importance) * 100 / Math.max(...meta.feature_importance.map((x: any) => Math.abs(x.importance)), 0.01))}%`,
                          background: 'var(--color-accent)',
                        }}
                      />
                    </div>
                    <span className="w-16 text-right font-mono text-xs">{f.importance > 0 ? '+' : ''}{f.importance.toFixed(3)}</span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
