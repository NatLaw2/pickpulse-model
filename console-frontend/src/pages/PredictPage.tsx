import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Crosshair, Database, Download, Loader2, Search, X, ChevronUp, ChevronDown, Mail, Calendar, BookOpen, PhoneForwarded } from 'lucide-react';
import { api, isNoDatasetError, isNoModelError, type PredictResponse, type ChurnPrediction, type ExplainResponse, type DraftEmailRequest } from '../lib/api';
import { useDataset } from '../lib/DatasetContext';
import { formatCurrency } from '../lib/format';

type SortKey = 'customer_id' | 'churn_risk_pct' | 'urgency_score' | 'renewal_window_label' | 'days_until_renewal' | 'arr' | 'arr_at_risk';
type SortDir = 'asc' | 'desc';
type Tone = 'friendly' | 'direct' | 'executive';

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

  // Sorting state — default by ARR at Risk DESC
  const [sortKey, setSortKey] = useState<SortKey>('arr_at_risk');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Drawer state
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [explainData, setExplainData] = useState<ExplainResponse | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  // Outreach overlay state (inside drawer)
  const [draftingAction, setDraftingAction] = useState<string | null>(null);
  const [emailPromptAction, setEmailPromptAction] = useState<string | null>(null);
  const [emailInput, setEmailInput] = useState('');
  const [selectedTone, setSelectedTone] = useState<Tone>('friendly');
  const [draftError, setDraftError] = useState<string | null>(null);
  const overlayRef = useRef<HTMLDivElement>(null);

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

  // Open drawer and fetch explain data
  const openDrawer = useCallback(async (customerId: string) => {
    setSelectedId(customerId);
    setExplainData(null);
    setExplainError(null);
    setExplainLoading(true);
    setDraftingAction(null);
    setEmailPromptAction(null);
    setDraftError(null);

    try {
      const data = await api.explainAccount(customerId);
      setExplainData(data);
    } catch (err: any) {
      setExplainError(err?.message || 'Failed to load account details');
    } finally {
      setExplainLoading(false);
    }
  }, []);

  const closeDrawer = () => {
    setSelectedId(null);
    setExplainData(null);
    setExplainError(null);
    setDraftingAction(null);
    setEmailPromptAction(null);
    setDraftError(null);
  };

  // Close drawer on outside click
  useEffect(() => {
    if (!selectedId) return;
    const handleClick = (e: MouseEvent) => {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
        closeDrawer();
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [selectedId]);

  // Close overlay on outside click
  useEffect(() => {
    if (!emailPromptAction) return;
    const handleClick = (e: MouseEvent) => {
      if (overlayRef.current && !overlayRef.current.contains(e.target as Node)) {
        setEmailPromptAction(null);
        setEmailInput('');
        setDraftError(null);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [emailPromptAction]);

  // Selected row data
  const selectedRow = selectedId ? (result?.predictions ?? []).find((p) => p.customer_id === selectedId) : null;

  // Playbook actions
  const handleDraftEmail = async (row: ChurnPrediction, contactEmail: string | null, actionType: string) => {
    setEmailPromptAction(null);
    setDraftingAction(actionType);
    setDraftError(null);

    try {
      const req: DraftEmailRequest = {
        customer_id: row.customer_id,
        customer_name: row.customer_id,
        contact_email: contactEmail || null,
        churn_risk_pct: row.churn_risk_pct,
        arr: row.arr,
        arr_at_risk: row.arr_at_risk,
        days_until_renewal: row.days_until_renewal,
        recommended_action: row.recommended_action,
        risk_driver_summary: explainData?.risk_driver_summary || null,
        tier: row.tier,
        tone: selectedTone,
      };

      const result = await api.draftOutreachEmail(req);

      console.log('[playbook] outreach_email_generated', {
        account_id: row.customer_id,
        action_type: actionType,
        tier: row.tier,
        arr: row.arr,
        tone: selectedTone,
        has_recipient: !!contactEmail,
      });

      await api.logPlaybookAction(row.customer_id, actionType);
      window.location.href = result.mailto_url;
    } catch (err: any) {
      console.error('[playbook] draft failed:', err);
      setDraftError(err?.message || 'Failed to generate email');
    } finally {
      setDraftingAction(null);
      setEmailInput('');
    }
  };

  const handleScheduleReview = async (row: ChurnPrediction) => {
    setDraftingAction('schedule_success_review');
    try {
      await api.logPlaybookAction(row.customer_id, 'schedule_success_review');
      window.location.href = api.downloadIcs(row.customer_id);
    } catch (err: any) {
      setDraftError(err?.message || 'Failed to download calendar invite');
    } finally {
      setDraftingAction(null);
    }
  };

  const handleEscalateToSales = async (row: ChurnPrediction) => {
    setDraftingAction('escalate_to_sales');
    try {
      await api.logPlaybookAction(row.customer_id, 'escalate_to_sales');
      const subject = encodeURIComponent(`Escalation: ${row.customer_id} — ${row.churn_risk_pct}% churn risk, ${formatCurrency(row.arr_at_risk)} ARR at risk`);
      const body = encodeURIComponent(
        `Account ${row.customer_id} has been flagged for sales escalation.\n\n` +
        `Churn Risk: ${row.churn_risk_pct}%\n` +
        `ARR: ${formatCurrency(row.arr)}\n` +
        `ARR at Risk: ${formatCurrency(row.arr_at_risk)}\n` +
        `Days Until Renewal: ${row.days_until_renewal}\n` +
        `Recommended Action: ${row.recommended_action}\n` +
        (explainData?.risk_driver_summary ? `\nRisk Drivers: ${explainData.risk_driver_summary}\n` : '') +
        `\nPlease review and take appropriate action.`
      );
      window.location.href = `mailto:?subject=${subject}&body=${body}`;
    } catch (err: any) {
      setDraftError(err?.message || 'Failed to log escalation');
    } finally {
      setDraftingAction(null);
    }
  };

  // Outreach overlay for drawer playbook actions
  const renderEmailOverlay = (row: ChurnPrediction, actionType: string) => (
    <div
      ref={overlayRef}
      className="mt-2 w-full bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-xl p-3"
    >
      <div className="mb-2">
        <label className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider block mb-1">
          Recipient Email
        </label>
        <input
          type="email"
          value={emailInput}
          onChange={(e) => setEmailInput(e.target.value)}
          placeholder="contact@company.com"
          className="w-full px-2.5 py-1.5 text-xs bg-white border border-[var(--color-border)] rounded-lg text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)]"
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleDraftEmail(row, emailInput.trim() || null, actionType);
          }}
          autoFocus
        />
      </div>
      <div className="mb-3">
        <label className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider block mb-1">
          Tone
        </label>
        <div className="flex gap-1">
          {(['friendly', 'direct', 'executive'] as Tone[]).map((t) => (
            <button
              key={t}
              onClick={() => setSelectedTone(t)}
              className={`flex-1 px-2 py-1 text-[10px] font-medium rounded-md transition-colors ${
                selectedTone === t
                  ? 'bg-[var(--color-accent)] text-white'
                  : 'bg-white border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-primary)]'
              }`}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </div>
      <div className="flex gap-2">
        <button
          onClick={() => handleDraftEmail(row, emailInput.trim() || null, actionType)}
          className="flex-1 px-3 py-1.5 text-[10px] font-semibold rounded-lg bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-glow)] transition-colors"
        >
          Generate
        </button>
        <button
          onClick={() => handleDraftEmail(row, null, actionType)}
          className="px-3 py-1.5 text-[10px] font-medium rounded-lg bg-white border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-primary)] transition-colors"
        >
          Skip Email
        </button>
      </div>
    </div>
  );

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
            className="px-5 py-2.5 bg-[var(--color-accent)] text-white rounded-xl text-sm font-medium hover:bg-[var(--color-accent-glow)] transition-all shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
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
              className="flex items-center gap-2 px-4 py-2.5 bg-white border border-[var(--color-border)] rounded-xl text-sm hover:bg-[var(--color-bg-primary)] transition-colors"
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
                        onClick={() => openDrawer(row.customer_id)}
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

      {/* Right-side Drawer */}
      {selectedId && selectedRow && (
        <div
          ref={drawerRef}
          className="fixed top-0 right-0 w-[400px] h-full bg-white border-l border-[var(--color-border)] shadow-[-10px_0_30px_rgba(0,0,0,0.1)] z-50 overflow-y-auto"
        >
          {/* Drawer header */}
          <div className="sticky top-0 bg-white border-b border-[var(--color-border)] px-5 py-4 flex items-center justify-between z-10">
            <div>
              <h3 className="text-sm font-bold">Why This Account Is At Risk</h3>
              <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{selectedRow.customer_id}</p>
            </div>
            <button
              onClick={closeDrawer}
              className="p-1.5 rounded-lg hover:bg-[var(--color-bg-primary)] transition-colors"
            >
              <X size={16} />
            </button>
          </div>

          <div className="px-5 py-5 space-y-6">
            {/* Account Summary */}
            <div>
              <h4 className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-3">Account Summary</h4>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-[var(--color-bg-primary)] rounded-xl p-3">
                  <div className="text-[10px] text-[var(--color-text-muted)] mb-1">Churn Risk</div>
                  <div className="text-lg font-bold" style={{ color: riskColor(selectedRow.churn_risk_pct) }}>
                    {selectedRow.churn_risk_pct}%
                  </div>
                  <div className="text-[10px]" style={{ color: riskColor(selectedRow.churn_risk_pct) }}>
                    {riskLabel(selectedRow.churn_risk_pct)} Risk
                  </div>
                </div>
                <div className="bg-[var(--color-bg-primary)] rounded-xl p-3">
                  <div className="text-[10px] text-[var(--color-text-muted)] mb-1">ARR at Risk</div>
                  <div className="text-lg font-bold text-[var(--color-danger)]">
                    {formatCurrency(selectedRow.arr_at_risk)}
                  </div>
                  <div className="text-[10px] text-[var(--color-text-muted)]">
                    of {formatCurrency(selectedRow.arr)} ARR
                  </div>
                </div>
                <div className="bg-[var(--color-bg-primary)] rounded-xl p-3">
                  <div className="text-[10px] text-[var(--color-text-muted)] mb-1">Renewal</div>
                  <div className="text-sm font-bold">{selectedRow.days_until_renewal} days</div>
                  <div className={`text-[10px] ${
                    selectedRow.renewal_window_label === '<30d' ? 'text-[var(--color-danger)]' :
                    selectedRow.renewal_window_label === '30-90d' ? 'text-[var(--color-warning)]' :
                    'text-[var(--color-text-muted)]'
                  }`}>
                    {selectedRow.renewal_window_label} window
                  </div>
                </div>
                <div className="bg-[var(--color-bg-primary)] rounded-xl p-3">
                  <div className="text-[10px] text-[var(--color-text-muted)] mb-1">Tier</div>
                  <div className="text-sm font-bold">{selectedRow.tier}</div>
                  <div className="text-[10px] text-[var(--color-text-muted)]">
                    Auto-renew: {selectedRow.auto_renew_flag ? 'On' : 'Off'}
                  </div>
                </div>
              </div>
            </div>

            {/* Risk Drivers */}
            <div>
              <h4 className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-3">Risk Drivers</h4>
              {explainLoading && (
                <div className="flex items-center gap-2 py-4 text-xs text-[var(--color-text-muted)]">
                  <Loader2 size={14} className="animate-spin" />
                  Loading risk analysis...
                </div>
              )}
              {explainError && (
                <div className="px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-xs text-[var(--color-danger)]">
                  {explainError}
                </div>
              )}
              {explainData && (
                <div className="space-y-2">
                  {explainData.risk_drivers.map((driver, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2 px-3 py-2.5 bg-[var(--color-bg-primary)] rounded-xl text-xs"
                    >
                      <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-[var(--color-danger)] flex-shrink-0" />
                      <span className="text-[var(--color-text-primary)]">{driver}</span>
                    </div>
                  ))}
                  {explainData.risk_driver_summary && (
                    <p className="text-[10px] text-[var(--color-text-muted)] mt-2 italic px-1">
                      {explainData.risk_driver_summary}
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Recommended Action */}
            {selectedRow.recommended_action && (
              <div>
                <h4 className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Recommended Action</h4>
                <div className="px-3 py-2.5 bg-[var(--color-accent)]/8 border border-[var(--color-accent)]/20 rounded-xl text-xs text-[var(--color-accent)]">
                  {selectedRow.recommended_action}
                </div>
              </div>
            )}

            {/* Customer Save Playbook */}
            <div>
              <h4 className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-3">Customer Save Playbook</h4>

              {draftError && (
                <div className="mb-3 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-xs text-[var(--color-danger)]">
                  {draftError}
                </div>
              )}

              <div className="space-y-2">
                {/* Generate Outreach Email */}
                <div>
                  <button
                    onClick={() => {
                      setEmailPromptAction(emailPromptAction === 'generate_outreach' ? null : 'generate_outreach');
                      setEmailInput('');
                      setDraftError(null);
                    }}
                    disabled={draftingAction !== null}
                    className="w-full flex items-center gap-3 px-3 py-2.5 bg-[var(--color-bg-primary)] rounded-xl text-xs hover:bg-[var(--color-border)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {draftingAction === 'generate_outreach' ? (
                      <Loader2 size={14} className="animate-spin text-[var(--color-accent)]" />
                    ) : (
                      <Mail size={14} className="text-[var(--color-accent)]" />
                    )}
                    <div className="text-left">
                      <div className="font-semibold">Generate Outreach Email</div>
                      <div className="text-[var(--color-text-muted)]">AI-drafted retention email via your email client</div>
                    </div>
                  </button>
                  {emailPromptAction === 'generate_outreach' && !draftingAction && (
                    renderEmailOverlay(selectedRow, 'generate_outreach')
                  )}
                </div>

                {/* Schedule Success Review */}
                <button
                  onClick={() => handleScheduleReview(selectedRow)}
                  disabled={draftingAction !== null}
                  className="w-full flex items-center gap-3 px-3 py-2.5 bg-[var(--color-bg-primary)] rounded-xl text-xs hover:bg-[var(--color-border)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {draftingAction === 'schedule_success_review' ? (
                    <Loader2 size={14} className="animate-spin text-[var(--color-success)]" />
                  ) : (
                    <Calendar size={14} className="text-[var(--color-success)]" />
                  )}
                  <div className="text-left">
                    <div className="font-semibold">Schedule Success Review</div>
                    <div className="text-[var(--color-text-muted)]">Download .ics calendar invite for next business day</div>
                  </div>
                </button>

                {/* Send Feature Training */}
                <div>
                  <button
                    onClick={() => {
                      setEmailPromptAction(emailPromptAction === 'send_feature_training' ? null : 'send_feature_training');
                      setEmailInput('');
                      setDraftError(null);
                    }}
                    disabled={draftingAction !== null}
                    className="w-full flex items-center gap-3 px-3 py-2.5 bg-[var(--color-bg-primary)] rounded-xl text-xs hover:bg-[var(--color-border)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {draftingAction === 'send_feature_training' ? (
                      <Loader2 size={14} className="animate-spin text-[var(--color-warning)]" />
                    ) : (
                      <BookOpen size={14} className="text-[var(--color-warning)]" />
                    )}
                    <div className="text-left">
                      <div className="font-semibold">Send Feature Training</div>
                      <div className="text-[var(--color-text-muted)]">AI email highlighting underused product features</div>
                    </div>
                  </button>
                  {emailPromptAction === 'send_feature_training' && !draftingAction && (
                    renderEmailOverlay(selectedRow, 'send_feature_training')
                  )}
                </div>

                {/* Escalate to Sales */}
                <button
                  onClick={() => handleEscalateToSales(selectedRow)}
                  disabled={draftingAction !== null}
                  className="w-full flex items-center gap-3 px-3 py-2.5 bg-[var(--color-bg-primary)] rounded-xl text-xs hover:bg-[var(--color-border)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {draftingAction === 'escalate_to_sales' ? (
                    <Loader2 size={14} className="animate-spin text-[var(--color-danger)]" />
                  ) : (
                    <PhoneForwarded size={14} className="text-[var(--color-danger)]" />
                  )}
                  <div className="text-left">
                    <div className="font-semibold">Escalate to Sales</div>
                    <div className="text-[var(--color-text-muted)]">Pre-filled internal escalation email with account context</div>
                  </div>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
