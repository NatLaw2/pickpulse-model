import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Crosshair, Database, Download, Loader2, Search, X, ChevronUp, ChevronDown, FileText, Mail, Copy } from 'lucide-react';
import { api, isNoDatasetError, isNoModelError, type ChurnPrediction } from '../lib/api';
import { useDataset } from '../lib/DatasetContext';
import { usePredictions } from '../lib/PredictionContext';
import { useExecutiveSummary } from '../lib/ExecutiveSummaryContext';
import { AccountDetailDrawer } from '../components/AccountDetailDrawer';
import { riskColor, riskLabel } from '../lib/risk';
import { formatCurrency } from '../lib/format';

type SortKey = 'customer_id' | 'churn_risk_pct' | 'urgency_score' | 'renewal_window_label' | 'days_until_renewal' | 'arr' | 'arr_at_risk';
type SortDir = 'asc' | 'desc';

export function PredictPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [search, setSearch] = useState('');
  const [riskFilter, setRiskFilter] = useState('all');
  const [windowFilter, setWindowFilter] = useState('all');
  const navigate = useNavigate();
  const { dataset } = useDataset();
  const { predictions: result, setPredictions, loadCached } = usePredictions();

  // Sorting state — default by ARR at Risk DESC
  const [sortKey, setSortKey] = useState<SortKey>('arr_at_risk');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Drawer state
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Executive summary (shared context, persisted via sessionStorage)
  const { summaryData, setSummaryData, showModal: showSummaryModal, setShowModal: setShowSummaryModal, buildMailtoUrl, getPlainText } = useExecutiveSummary();
  const [summaryToast, setSummaryToast] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Auto-restore cached predictions on mount
  useEffect(() => {
    loadCached();
  }, [loadCached]);

  const handlePredict = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.predict(500, showArchived);
      setPredictions(res);

      // Auto-trigger executive summary (non-blocking)
      triggerExecutiveSummary(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const triggerExecutiveSummary = async (res: typeof result) => {
    if (!res) return;
    try {
      // Get notification settings for recipients
      let recipients: string[] = [];
      try {
        const settings = await api.getNotificationSettings();
        recipients = settings.recipients;
      } catch { /* no settings configured */ }

      const topAccounts = [...res.predictions]
        .sort((a, b) => (b.arr_at_risk || 0) - (a.arr_at_risk || 0))
        .slice(0, 5)
        .map((p) => ({
          customer_id: p.customer_id,
          churn_risk_pct: p.churn_risk_pct,
          arr: p.arr,
          arr_at_risk: p.arr_at_risk,
          days_until_renewal: p.days_until_renewal,
          tier: p.tier,
        }));

      // Extract risk driver names from tier counts (we don't have feature importance here,
      // so we use high-level summary)
      const riskDrivers: string[] = [];
      const highCount = res.tier_counts['High Risk'] ?? 0;
      const medCount = res.tier_counts['Medium Risk'] ?? 0;
      if (highCount > 0) riskDrivers.push(`${highCount} accounts at High Risk`);
      if (medCount > 0) riskDrivers.push(`${medCount} accounts at Medium Risk`);
      if (res.summary.renewing_90d) riskDrivers.push(`${res.summary.renewing_90d} renewals within 90 days`);

      const summaryRes = await api.sendExecutiveSummary({
        recipients,
        total_arr_at_risk: res.summary.total_arr_at_risk ?? 0,
        projected_recoverable_arr: (res.summary.total_arr_at_risk ?? 0) * 0.35,
        save_rate: 0.35,
        high_risk_in_window: res.summary.high_risk_in_window ?? 0,
        renewing_90d: res.summary.renewing_90d ?? 0,
        top_accounts: topAccounts,
        tier_counts: res.tier_counts,
        risk_drivers: riskDrivers,
      });

      setSummaryData(summaryRes);

      // Show toast
      const recipientText = summaryRes.recipients.length > 0
        ? `Executive ARR Risk Brief sent to ${summaryRes.recipients.join(', ')}`
        : 'Executive ARR Risk Brief generated';
      setSummaryToast(recipientText);
      setTimeout(() => setSummaryToast(null), 8000);
    } catch (err) {
      console.error('[executive-summary] failed:', err);
    }
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

  // Sort
  const sorted = [...filtered].sort((a, b) => {
    const aVal = a[sortKey] ?? 0;
    const bVal = b[sortKey] ?? 0;
    if (typeof aVal === 'string' && typeof bVal === 'string') {
      return sortDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    }
    const diff = (aVal as number) - (bVal as number);
    return sortDir === 'asc' ? diff : -diff;
  });

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir(key === 'customer_id' ? 'asc' : 'desc');
    }
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <span className="ml-1 opacity-0 group-hover:opacity-30 inline-block w-3"><ChevronDown size={10} /></span>;
    return sortDir === 'asc'
      ? <ChevronUp size={10} className="ml-1 inline-block text-[var(--color-accent)]" />
      : <ChevronDown size={10} className="ml-1 inline-block text-[var(--color-accent)]" />;
  };

  // Selected row data
  const selectedRow = selectedId ? (result?.predictions ?? []).find((p) => p.customer_id === selectedId) : null;

  return (
    <div className="relative">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Accounts</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">Score every account in the portfolio and surface prioritized churn risk predictions</p>
      </div>

      {/* No dataset — neutral guidance */}
      {noDataset && !result && (
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-8 mb-8 text-center shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <Database size={32} className="mx-auto mb-3 text-[var(--color-text-muted)]" />
          <h3 className="font-semibold mb-2">No dataset loaded</h3>
          <p className="text-sm text-[var(--color-text-secondary)] mb-5 max-w-md mx-auto">
            Load a sample dataset or upload your own account data before generating predictions.
          </p>
          <button
            onClick={() => navigate('/data-sources')}
            className="btn-primary px-5 py-2.5 text-white rounded-xl text-sm font-medium"
          >
            Go to Datasets
          </button>
        </div>
      )}

      {/* No model — neutral guidance */}
      {noModel && !result && (
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-8 mb-8 text-center shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <Database size={32} className="mx-auto mb-3 text-[var(--color-text-muted)]" />
          <h3 className="font-semibold mb-2">No trained model</h3>
          <p className="text-sm text-[var(--color-text-secondary)] mb-5 max-w-md mx-auto">
            Train a churn model on your dataset before generating predictions.
          </p>
          <button
            onClick={() => navigate('/model')}
            className="btn-primary px-5 py-2.5 text-white rounded-xl text-sm font-medium"
          >
            Go to Train
          </button>
        </div>
      )}

      {/* Executive Brief — always visible when summaryData exists */}
      {summaryData && (
        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={() => setShowSummaryModal(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/25 rounded-xl text-sm text-[var(--color-accent)] font-medium hover:bg-[var(--color-accent)]/15 transition-colors"
          >
            <FileText size={14} />
            View Executive Brief
          </button>
        </div>
      )}

      {/* Action bar — only show when we have a dataset */}
      {!noDataset && !noModel && (
        <div className="flex items-center gap-3 mb-6 flex-wrap">
          <button
            onClick={handlePredict}
            disabled={loading}
            className="btn-primary flex items-center gap-2 px-5 py-2.5 text-white rounded-xl font-medium disabled:opacity-50"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Crosshair size={16} />}
            {loading ? 'Scoring...' : 'Generate Predictions'}
          </button>

          {result && (
            <button
              onClick={() => api.exportPredictions().catch((e: any) => alert(e.message))}
              className="flex items-center gap-2 px-4 py-2.5 bg-white border border-[var(--color-border)] rounded-xl text-sm hover:bg-[var(--color-bg-primary)] transition-colors"
            >
              <Download size={14} />
              Export CSV
            </button>
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
        <div className="bg-red-50 border border-red-200 rounded-2xl p-4 mb-6">
          <p className="text-sm text-[var(--color-danger)]">{error}</p>
        </div>
      )}

      {result && (
        <>
          {/* Summary badges */}
          <div className="flex gap-3 mb-6 flex-wrap">
            {Object.entries(result.tier_counts).map(([tier, count]) => {
              const color = tier.includes('High') ? 'var(--color-danger)' : tier.includes('Medium') ? 'var(--color-warning)' : 'var(--color-success)';
              return (
                <div key={tier} className="px-4 py-2.5 bg-white border border-[var(--color-border)] rounded-xl text-sm">
                  <span className="font-bold" style={{ color }}>{count}</span>
                  <span className="text-[var(--color-text-secondary)] ml-2">{tier}</span>
                </div>
              );
            })}
            <div className="px-4 py-2.5 bg-white border border-[var(--color-border)] rounded-xl text-sm text-[var(--color-text-secondary)]">
              {result.active_count} active / {result.archived_count} archived
            </div>
            {result.summary.total_arr_at_risk != null && (
              <div className="px-4 py-2.5 bg-white border border-[var(--color-border)] rounded-xl text-sm" title="ARR at Risk = ARR x churn probability">
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
                className="pl-9 pr-3 py-2 bg-white border border-[var(--color-border)] rounded-xl text-sm w-48 focus:outline-none focus:border-[var(--color-accent)]"
              />
            </div>
            <select
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
              className="px-3 py-2 bg-white border border-[var(--color-border)] rounded-xl text-sm"
            >
              <option value="all">All Risk</option>
              <option value="high">High (70%+)</option>
              <option value="med">Medium (40-69%)</option>
              <option value="low">Low (&lt;40%)</option>
            </select>
            <select
              value={windowFilter}
              onChange={(e) => setWindowFilter(e.target.value)}
              className="px-3 py-2 bg-white border border-[var(--color-border)] rounded-xl text-sm"
            >
              <option value="all">All Windows</option>
              <option value="<30d">&lt;30 days</option>
              <option value="30-90d">30-90 days</option>
              <option value=">90d">&gt;90 days</option>
            </select>
            <span className="text-xs text-[var(--color-text-muted)] ml-auto">
              {sorted.length} of {result.predictions.length} shown
              {sortKey !== 'arr_at_risk' || sortDir !== 'desc' ? (
                <button
                  onClick={() => { setSortKey('arr_at_risk'); setSortDir('desc'); }}
                  className="ml-2 text-[var(--color-accent)] hover:underline"
                >
                  Reset sort
                </button>
              ) : null}
            </span>
          </div>

          {/* Predictions table */}
          <div className={`transition-all ${selectedId ? 'mr-[400px]' : ''}`}>
            <div className="bg-white border border-[var(--color-border)] rounded-2xl overflow-hidden shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 z-10">
                    <tr className="text-left text-xs text-[var(--color-text-muted)] uppercase tracking-wider bg-[var(--color-bg-primary)]">
                      <th className="py-3 px-4 font-medium cursor-pointer group select-none" onClick={() => handleSort('customer_id')}>
                        Account <SortIcon col="customer_id" />
                      </th>
                      <th className="py-3 px-4 font-medium text-right cursor-pointer group select-none" onClick={() => handleSort('churn_risk_pct')}>
                        Churn Risk <SortIcon col="churn_risk_pct" />
                      </th>
                      <th className="py-3 px-4 font-medium text-right cursor-pointer group select-none" onClick={() => handleSort('urgency_score')} title="Composite score combining churn probability and proximity to renewal date.">
                        Urgency <SortIcon col="urgency_score" />
                      </th>
                      <th className="py-3 px-4 font-medium cursor-pointer group select-none" onClick={() => handleSort('renewal_window_label')}>
                        Renewal <SortIcon col="renewal_window_label" />
                      </th>
                      <th className="py-3 px-4 font-medium text-right cursor-pointer group select-none" onClick={() => handleSort('days_until_renewal')}>
                        Days <SortIcon col="days_until_renewal" />
                      </th>
                      <th className="py-3 px-4 font-medium text-center">Auto</th>
                      <th className="py-3 px-4 font-medium text-right cursor-pointer group select-none" onClick={() => handleSort('arr')}>
                        ARR <SortIcon col="arr" />
                      </th>
                      <th className="py-3 px-4 font-medium text-right cursor-pointer group select-none" onClick={() => handleSort('arr_at_risk')} title="Annual recurring revenue weighted by churn probability.">
                        ARR at Risk <SortIcon col="arr_at_risk" />
                      </th>
                      <th className="py-3 px-4 font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((row, i) => (
                      <tr
                        key={row.customer_id}
                        onClick={() => setSelectedId(row.customer_id)}
                        className={`border-t border-[var(--color-border)] hover:bg-[var(--color-accent-light)] transition-colors cursor-pointer ${
                          i % 2 === 1 ? 'bg-[var(--color-bg-primary)]' : ''
                        } ${selectedId === row.customer_id ? 'bg-[var(--color-accent)]/10' : ''}`}
                      >
                        <td className="py-3 px-4 font-medium text-xs">{row.customer_id}</td>
                        <td className="py-3 px-4 text-right">
                          <span
                            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold"
                            style={{ background: `${riskColor(row.churn_risk_pct)}18`, color: riskColor(row.churn_risk_pct) }}
                          >
                            {riskLabel(row.churn_risk_pct)} {row.churn_risk_pct}%
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-xs">{row.urgency_score}</td>
                        <td className="py-3 px-4">
                          <span className={`text-xs px-2 py-0.5 rounded-lg ${
                            row.renewal_window_label === '<30d' ? 'bg-red-50 text-[var(--color-danger)]' :
                            row.renewal_window_label === '30-90d' ? 'bg-amber-50 text-[var(--color-warning)]' :
                            'bg-[var(--color-bg-primary)] text-[var(--color-text-secondary)]'
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
          </div>
        </>
      )}

      {/* Account Detail Drawer */}
      {selectedId && selectedRow && (
        <AccountDetailDrawer
          customerId={selectedId}
          prediction={selectedRow}
          onClose={() => setSelectedId(null)}
        />
      )}

      {/* Executive Summary Toast */}
      {summaryToast && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3 bg-white border border-[var(--color-border)] rounded-xl shadow-[0_4px_20px_rgba(0,0,0,0.12)] animate-[slideUp_0.3s_ease-out]">
          <FileText size={16} className="text-[var(--color-accent)]" />
          <span className="text-sm text-[var(--color-text-primary)]">{summaryToast}</span>
          <button
            onClick={() => { setSummaryToast(null); setShowSummaryModal(true); }}
            className="text-sm font-semibold text-[var(--color-accent)] hover:underline ml-2"
          >
            View Brief
          </button>
          <button
            onClick={() => setSummaryToast(null)}
            className="p-1 rounded hover:bg-[var(--color-bg-primary)] ml-1"
          >
            <X size={14} className="text-[var(--color-text-muted)]" />
          </button>
        </div>
      )}

      {/* Executive Summary Preview Modal */}
      {showSummaryModal && summaryData && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40"
          onClick={() => setShowSummaryModal(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-[0_8px_40px_rgba(0,0,0,0.2)] max-w-[700px] w-full max-h-[85vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
              <div>
                <h2 className="text-sm font-bold">Executive ARR Risk Brief</h2>
                <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{summaryData.generated_at}</p>
              </div>
              <button
                onClick={() => setShowSummaryModal(false)}
                className="p-1.5 rounded-lg hover:bg-[var(--color-bg-primary)] transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            {/* Email preview */}
            <div className="flex-1 overflow-y-auto p-6 bg-[var(--color-bg-primary)]">
              <div
                className="bg-white rounded-xl shadow-[0_1px_4px_rgba(0,0,0,0.08)] overflow-hidden"
                dangerouslySetInnerHTML={{ __html: summaryData.html_body }}
              />
            </div>
            {/* Modal footer */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-[var(--color-border)] bg-white">
              <div className="text-xs text-[var(--color-text-muted)]">
                {summaryData.recipients.length > 0
                  ? `Recipients: ${summaryData.recipients.join(', ')}`
                  : 'No recipients configured — configure in API settings'}
              </div>
              <div className="flex items-center gap-2">
                <a
                  href={buildMailtoUrl()}
                  className="btn-primary flex items-center gap-2 px-5 py-2.5 text-white rounded-xl text-sm font-medium"
                >
                  <Mail size={14} />
                  Send Executive Brief
                </a>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(getPlainText());
                    setCopied(true);
                    setTimeout(() => setCopied(false), 2000);
                  }}
                  className="flex items-center gap-1.5 px-4 py-2.5 bg-white border border-[var(--color-border)] rounded-xl text-sm hover:bg-[var(--color-bg-primary)] transition-colors"
                >
                  <Copy size={14} />
                  {copied ? 'Copied!' : 'Copy Summary'}
                </button>
                <button
                  onClick={() => setShowSummaryModal(false)}
                  className="px-4 py-2.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
