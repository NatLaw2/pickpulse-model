import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Crosshair, Database, Download, Loader2, Search } from 'lucide-react';
import { api, isNoDatasetError, isNoModelError, type PredictResponse, type ChurnPrediction } from '../lib/api';
import { useDataset } from '../lib/DatasetContext';
import { formatCurrency } from '../lib/format';

export function PredictPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PredictResponse | null>(null);
  const [error, setError] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [search, setSearch] = useState('');
  const [riskFilter, setRiskFilter] = useState('all');
  const [windowFilter, setWindowFilter] = useState('all');
  const navigate = useNavigate();
  const { dataset } = useDataset();

  const handlePredict = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.predict(500, showArchived);
      setResult(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const riskColor = (pct: number) => {
    if (pct >= 70) return 'var(--color-danger)';
    if (pct >= 40) return 'var(--color-warning)';
    return 'var(--color-success)';
  };

  const riskLabel = (pct: number) => {
    if (pct >= 70) return 'High';
    if (pct >= 40) return 'Med';
    return 'Low';
  };

  // Determine empty states
  const noDataset = !dataset || (error && isNoDatasetError(error));
  const noModel = error && isNoModelError(error) && !noDataset;
  const realError = error && !isNoDatasetError(error) && !isNoModelError(error);

  // Apply client-side filters
  let filtered: ChurnPrediction[] = result?.predictions ?? [];
  if (search) {
    const q = search.toLowerCase();
    filtered = filtered.filter((r) => r.customer_id?.toLowerCase().includes(q));
  }
  if (riskFilter !== 'all') {
    filtered = filtered.filter((r) => {
      if (riskFilter === 'high') return r.churn_risk_pct >= 70;
      if (riskFilter === 'med') return r.churn_risk_pct >= 40 && r.churn_risk_pct < 70;
      if (riskFilter === 'low') return r.churn_risk_pct < 40;
      return true;
    });
  }
  if (windowFilter !== 'all') {
    filtered = filtered.filter((r) => r.renewal_window_label === windowFilter);
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Account Scoring</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">Score every account in the portfolio and surface prioritized churn risk predictions</p>
      </div>

      {/* No dataset — neutral guidance */}
      {noDataset && !result && (
        <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-8 mb-8 text-center shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
          <Database size={32} className="mx-auto mb-3 text-[var(--color-text-muted)]" />
          <h3 className="font-semibold mb-2">No dataset loaded</h3>
          <p className="text-sm text-[var(--color-text-secondary)] mb-5 max-w-md mx-auto">
            Load a sample dataset or upload your own account data before generating predictions.
          </p>
          <button
            onClick={() => navigate('/datasets')}
            className="px-5 py-2.5 bg-[var(--color-accent)] text-white rounded-xl text-sm font-medium hover:bg-[var(--color-accent-glow)] transition-all shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
          >
            Go to Datasets
          </button>
        </div>
      )}

      {/* No model — neutral guidance */}
      {noModel && !result && (
        <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-8 mb-8 text-center shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
          <Database size={32} className="mx-auto mb-3 text-[var(--color-text-muted)]" />
          <h3 className="font-semibold mb-2">No trained model</h3>
          <p className="text-sm text-[var(--color-text-secondary)] mb-5 max-w-md mx-auto">
            Train a churn model on your dataset before generating predictions.
          </p>
          <button
            onClick={() => navigate('/train')}
            className="px-5 py-2.5 bg-[var(--color-accent)] text-white rounded-xl text-sm font-medium hover:bg-[var(--color-accent-glow)] transition-all shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
          >
            Go to Train
          </button>
        </div>
      )}

      {/* Action bar — only show when we have a dataset */}
      {!noDataset && !noModel && (
        <div className="flex items-center gap-3 mb-6 flex-wrap">
          <button
            onClick={handlePredict}
            disabled={loading}
            className="flex items-center gap-2 px-5 py-2.5 bg-[var(--color-accent)] text-white rounded-xl font-medium hover:bg-[var(--color-accent-glow)] transition-all disabled:opacity-50 shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Crosshair size={16} />}
            {loading ? 'Scoring...' : 'Generate Predictions'}
          </button>

          {result && (
            <a
              href={api.exportPredictions()}
              className="flex items-center gap-2 px-4 py-2.5 bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-xl text-sm hover:bg-[var(--color-bg-card-hover)] transition-colors"
            >
              <Download size={14} />
              Export CSV
            </a>
          )}

          <label className="flex items-center gap-2 ml-auto text-sm text-[var(--color-text-secondary)] cursor-pointer">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => { setShowArchived(e.target.checked); if (result) handlePredict(); }}
              className="rounded"
            />
            Show archived accounts
          </label>
        </div>
      )}

      {/* Real errors only */}
      {realError && (
        <div className="bg-red-900/20 border border-red-800/40 rounded-2xl p-4 mb-6">
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      {result && (
        <>
          {/* Summary badges */}
          <div className="flex gap-3 mb-6 flex-wrap">
            {Object.entries(result.tier_counts).map(([tier, count]) => {
              const color = tier.includes('High') ? 'var(--color-danger)' : tier.includes('Medium') ? 'var(--color-warning)' : 'var(--color-success)';
              return (
                <div key={tier} className="px-4 py-2.5 bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-xl text-sm">
                  <span className="font-bold" style={{ color }}>{count}</span>
                  <span className="text-[var(--color-text-secondary)] ml-2">{tier}</span>
                </div>
              );
            })}
            <div className="px-4 py-2.5 bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-xl text-sm text-[var(--color-text-secondary)]">
              {result.active_count} active / {result.archived_count} archived
            </div>
            {result.summary.total_arr_at_risk != null && (
              <div className="px-4 py-2.5 bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-xl text-sm" title="ARR at Risk = ARR x churn probability">
                <span className="font-bold text-[var(--color-danger)]">{formatCurrency(result.summary.total_arr_at_risk)}</span>
                <span className="text-[var(--color-text-secondary)] ml-2">ARR at Risk</span>
              </div>
            )}
          </div>

          {/* Filters */}
          <div className="flex gap-3 mb-4 flex-wrap items-center">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
              <input
                type="text"
                placeholder="Search customer..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 pr-3 py-2 bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-xl text-sm w-48 focus:outline-none focus:border-[var(--color-accent)]"
              />
            </div>
            <select
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
              className="px-3 py-2 bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-xl text-sm"
            >
              <option value="all">All Risk</option>
              <option value="high">High (70%+)</option>
              <option value="med">Medium (40-69%)</option>
              <option value="low">Low (&lt;40%)</option>
            </select>
            <select
              value={windowFilter}
              onChange={(e) => setWindowFilter(e.target.value)}
              className="px-3 py-2 bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-xl text-sm"
            >
              <option value="all">All Windows</option>
              <option value="<30d">&lt;30 days</option>
              <option value="30-90d">30-90 days</option>
              <option value=">90d">&gt;90 days</option>
            </select>
            <span className="text-xs text-[var(--color-text-muted)] ml-auto">
              {filtered.length} of {result.predictions.length} shown
            </span>
          </div>

          {/* Predictions table */}
          <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl overflow-hidden shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 z-10">
                  <tr className="text-left text-xs text-[var(--color-text-muted)] uppercase tracking-wider bg-[var(--color-bg-secondary)]">
                    <th className="py-3 px-4 font-medium">Account</th>
                    <th className="py-3 px-4 font-medium text-right">Churn Risk</th>
                    <th className="py-3 px-4 font-medium text-right" title="Composite score combining churn probability and proximity to renewal date. Higher values indicate accounts needing immediate attention.">Urgency</th>
                    <th className="py-3 px-4 font-medium">Renewal</th>
                    <th className="py-3 px-4 font-medium text-right">Days</th>
                    <th className="py-3 px-4 font-medium text-center">Auto</th>
                    <th className="py-3 px-4 font-medium text-right">ARR</th>
                    <th className="py-3 px-4 font-medium text-right" title="Annual recurring revenue weighted by churn probability — the expected revenue exposure for this account.">ARR at Risk</th>
                    <th className="py-3 px-4 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row, i) => (
                    <tr key={row.customer_id} className={`border-t border-[var(--color-border)]/30 hover:bg-[rgba(123,97,255,0.08)] transition-colors ${i % 2 === 1 ? 'bg-[rgba(255,255,255,0.03)]' : ''}`}>
                      <td className="py-3 px-4 font-mono text-xs">{row.customer_id}</td>
                      <td className="py-3 px-4 text-right">
                        <span
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold"
                          style={{ background: `${riskColor(row.churn_risk_pct)}20`, color: riskColor(row.churn_risk_pct) }}
                        >
                          {riskLabel(row.churn_risk_pct)} {row.churn_risk_pct}%
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-xs">{row.urgency_score}</td>
                      <td className="py-3 px-4">
                        <span className={`text-xs px-2 py-0.5 rounded-lg ${
                          row.renewal_window_label === '<30d' ? 'bg-[var(--color-danger)]/15 text-[var(--color-danger)]' :
                          row.renewal_window_label === '30-90d' ? 'bg-[var(--color-warning)]/15 text-[var(--color-warning)]' :
                          'bg-[rgba(255,255,255,0.06)] text-[var(--color-text-secondary)]'
                        }`}>
                          {row.renewal_window_label}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-xs">{row.days_until_renewal}</td>
                      <td className="py-3 px-4 text-center text-xs">{row.auto_renew_flag ? 'Yes' : 'No'}</td>
                      <td className="py-3 px-4 text-right font-mono text-xs">{formatCurrency(row.arr)}</td>
                      <td className="py-3 px-4 text-right font-mono text-xs font-bold" style={{ color: riskColor(row.churn_risk_pct) }}>
                        {formatCurrency(row.arr_at_risk)}
                      </td>
                      <td className="py-3 px-4 text-xs text-[var(--color-text-secondary)] max-w-56 truncate">{row.recommended_action}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {result.showing < result.total && (
              <div className="px-4 py-3 text-xs text-[var(--color-text-muted)] border-t border-[var(--color-border)]">
                Showing {result.showing} of {result.total.toLocaleString()} rows
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
