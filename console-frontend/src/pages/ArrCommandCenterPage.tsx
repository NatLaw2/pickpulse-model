/**
 * ARR Command Center — 90-Day Revenue Forecast & Exposure
 *
 * Executive-facing revenue forecasting page. Distinct purpose from Overview:
 *   Overview  = operational dashboard (what's happening now, who to call)
 *   This page = boardroom forecast (what will ARR be in 90 days, where is concentration risk)
 *
 * Sections:
 *   1. 90-Day Forecast Scenarios (best / expected / worst)
 *   2. Renewal Risk Timeline (ARR bucketed by renewal window)
 *   3. Portfolio Concentration Risk
 *   4. Revenue Impact Priority — accounts that change the quarter
 */
import { useEffect, useState, useMemo, useCallback } from 'react';
import {
  AlertTriangle, RefreshCw, Loader2, AlertCircle,
  ChevronUp, ChevronDown, ChevronsUpDown, Info,
  TrendingDown, Calendar, Target, BarChart3,
} from 'lucide-react';
import { api, type ArrCommandCenterResponse, type ArrRankedAccount } from '../lib/api';
import { ArrAccountDrawer } from '../components/ArrAccountDrawer';
import { formatCurrency } from '../lib/format';

// ─── Colour helpers ───────────────────────────────────────────────────────────
function riskColor(pct: number): string {
  if (pct >= 40) return 'var(--color-danger)';
  if (pct >= 25) return 'var(--color-warning)';
  return 'var(--color-success)';
}

function riskBg(pct: number): string {
  if (pct >= 40) return 'bg-red-500/10 border-red-500/20 text-red-400';
  if (pct >= 25) return 'bg-amber-500/10 border-amber-500/20 text-amber-400';
  return 'bg-green-500/10 border-green-500/20 text-green-400';
}

// ─── Sort helpers ─────────────────────────────────────────────────────────────
type SortKey = 'weighted_risk_value' | 'churn_risk_pct' | 'arr' | 'days_until_renewal';
type SortDir = 'asc' | 'desc';

function sortAccounts(accounts: ArrRankedAccount[], key: SortKey, dir: SortDir): ArrRankedAccount[] {
  return [...accounts].sort((a, b) => {
    const av = a[key] ?? (dir === 'desc' ? -Infinity : Infinity);
    const bv = b[key] ?? (dir === 'desc' ? -Infinity : Infinity);
    return dir === 'desc' ? (bv as number) - (av as number) : (av as number) - (bv as number);
  });
}

function SortIcon({ col, sortKey, sortDir }: { col: SortKey; sortKey: SortKey; sortDir: SortDir }) {
  if (col !== sortKey) return <ChevronsUpDown size={11} className="text-[var(--color-border)]" />;
  return sortDir === 'desc'
    ? <ChevronDown size={11} className="text-[var(--color-accent)]" />
    : <ChevronUp size={11} className="text-[var(--color-accent)]" />;
}

function ColHeader({
  label, col, sortKey, sortDir, onSort, right,
}: {
  label: string; col: SortKey; sortKey: SortKey; sortDir: SortDir;
  onSort: (c: SortKey) => void; right?: boolean;
}) {
  return (
    <th
      className={`py-3 text-[10px] font-semibold tracking-widest uppercase text-[var(--color-text-muted)] cursor-pointer select-none hover:text-[var(--color-text)] transition-colors ${right ? 'text-right pr-4' : 'text-left pl-4'}`}
      onClick={() => onSort(col)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <SortIcon col={col} sortKey={sortKey} sortDir={sortDir} />
      </span>
    </th>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────
function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="w-14 h-14 rounded-2xl bg-[var(--color-bg-secondary)] border border-[var(--color-border)] flex items-center justify-center mb-4">
        <BarChart3 size={24} className="text-[var(--color-text-muted)]" />
      </div>
      <h3 className="text-base font-semibold text-[var(--color-text)] mb-2">No forecast data yet</h3>
      <p className="text-sm text-[var(--color-text-muted)] max-w-sm">
        Score accounts to generate the 90-day revenue forecast.
        Complete Setup → sync your CRM → train → score accounts.
      </p>
    </div>
  );
}

// ─── Scenario card ────────────────────────────────────────────────────────────
function ScenarioCard({
  label, arr, arrLost, currentArr, variant, assumption,
}: {
  label: string;
  arr: number;
  arrLost: number;
  currentArr: number;
  variant: 'best' | 'expected' | 'worst';
  assumption?: string;
}) {
  const pctChange = currentArr > 0 ? ((arr - currentArr) / currentArr) * 100 : 0;
  const colors = {
    best:     { border: 'border-green-500/20',  bg: 'bg-green-500/5',  badge: 'bg-green-500/10 text-green-400' },
    expected: { border: 'border-[var(--color-border)]', bg: 'bg-[var(--color-bg-secondary)]', badge: 'bg-[var(--color-accent)]/10 text-[var(--color-accent)]' },
    worst:    { border: 'border-red-500/20',    bg: 'bg-red-500/5',    badge: 'bg-red-500/10 text-red-400' },
  }[variant];

  return (
    <div className={`rounded-2xl border ${colors.border} ${colors.bg} p-5 flex flex-col gap-3`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">{label}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colors.badge}`}>
          {pctChange >= 0 ? '+' : ''}{pctChange.toFixed(1)}%
        </span>
      </div>
      <div>
        <p className="text-2xl font-bold text-[var(--color-text)]">{formatCurrency(arr)}</p>
        <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
          <span className="text-[var(--color-danger)]">{formatCurrency(arrLost)}</span> projected loss
        </p>
      </div>
      {assumption && (
        <p className="text-[11px] text-[var(--color-text-muted)] italic leading-relaxed">{assumption}</p>
      )}
    </div>
  );
}

// ─── Renewal timeline bar ─────────────────────────────────────────────────────
function RenewalBar({
  label, accounts, arrTotal, arrAtRisk, highRisk, maxArr,
}: {
  label: string; accounts: number; arrTotal: number; arrAtRisk: number; highRisk: number; maxArr: number;
}) {
  const pct = maxArr > 0 ? Math.min(100, (arrTotal / maxArr) * 100) : 0;
  const riskPct = arrTotal > 0 ? (arrAtRisk / arrTotal) * 100 : 0;

  return (
    <div className="flex items-center gap-4">
      <div className="w-20 shrink-0 text-xs text-[var(--color-text-muted)] text-right">{label}</div>
      <div className="flex-1">
        <div className="h-5 rounded-md bg-[var(--color-bg-primary)] border border-[var(--color-border)] overflow-hidden relative">
          <div
            className="absolute inset-y-0 left-0 bg-[var(--color-accent)]/15 rounded-md"
            style={{ width: `${pct}%` }}
          />
          <div
            className="absolute inset-y-0 left-0 bg-[var(--color-danger)]/25 rounded-md"
            style={{ width: `${pct * riskPct / 100}%` }}
          />
        </div>
      </div>
      <div className="w-28 shrink-0 text-right">
        <p className="text-xs font-medium text-[var(--color-text)]">{formatCurrency(arrTotal)}</p>
        <p className="text-[10px] text-[var(--color-text-muted)]">{accounts} account{accounts !== 1 ? 's' : ''}</p>
      </div>
      <div className="w-24 shrink-0 text-right">
        <p className="text-xs font-medium text-[var(--color-danger)]">{formatCurrency(arrAtRisk)}</p>
        <p className="text-[10px] text-[var(--color-text-muted)]">{highRisk} high risk</p>
      </div>
    </div>
  );
}

// ─── Account row ──────────────────────────────────────────────────────────────
function AccountRow({
  account, isLast, onClick,
}: {
  account: ArrRankedAccount; isLast: boolean; onClick: () => void;
}) {
  return (
    <tr
      onClick={onClick}
      className={`group cursor-pointer transition-colors hover:bg-[var(--color-bg-secondary)] ${!isLast ? 'border-b border-[var(--color-border)]' : ''}`}
    >
      <td className="py-3 pl-4 pr-2">
        <div className="min-w-0">
          <p className="font-medium text-[var(--color-text)] truncate max-w-[200px] group-hover:text-[var(--color-accent)] transition-colors text-sm">
            {account.name}
          </p>
          <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
            {account.missing_fields.includes('arr') && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full border border-[var(--color-border)] text-[var(--color-text-muted)]">No ARR</span>
            )}
            {account.confidence_level && (
              <span className="text-[9px] text-[var(--color-text-muted)] capitalize">{account.confidence_level} conf.</span>
            )}
          </div>
        </div>
      </td>
      <td className="py-3 pr-4 text-right">
        <span className={`inline-flex items-center justify-center px-2 py-0.5 rounded-full text-xs font-semibold border ${riskBg(account.churn_risk_pct)}`}>
          {account.churn_risk_pct.toFixed(0)}%
        </span>
      </td>
      <td className="py-3 pr-4 text-right text-sm text-[var(--color-text)]">
        {account.arr != null ? formatCurrency(account.arr) : <span className="text-[var(--color-text-muted)] text-xs">—</span>}
      </td>
      <td className="py-3 pr-4 text-right">
        {account.weighted_risk_value != null ? (
          <span className="text-sm font-medium" style={{ color: riskColor(account.churn_risk_pct) }}>
            {formatCurrency(account.weighted_risk_value)}
          </span>
        ) : (
          <span className="text-[var(--color-text-muted)] text-xs">—</span>
        )}
      </td>
      <td className="py-3 pr-4 text-right text-sm text-[var(--color-text)]">
        {account.days_until_renewal != null ? (
          <span className={account.days_until_renewal <= 30 ? 'text-[var(--color-danger)] font-medium' : ''}>
            {Math.round(account.days_until_renewal)}d
          </span>
        ) : (
          <span className="text-[var(--color-text-muted)] text-xs">—</span>
        )}
      </td>
      <td className="py-3 pl-4 pr-4">
        <div className="flex flex-wrap gap-1">
          {account.top_drivers.length > 0 ? (
            account.top_drivers.slice(0, 2).map((d, i) => (
              <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-red-500/8 border border-red-500/15 text-red-400 max-w-[150px] truncate" title={d.label}>
                {d.label}
              </span>
            ))
          ) : (
            <span className="text-[10px] text-[var(--color-text-muted)]">No signals</span>
          )}
        </div>
      </td>
    </tr>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export function ArrCommandCenterPage() {
  const [data, setData] = useState<ArrCommandCenterResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const [sortKey, setSortKey] = useState<SortKey>('weighted_risk_value');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [selectedAccount, setSelectedAccount] = useState<ArrRankedAccount | null>(null);

  const load = useCallback(async (showRefreshing = false) => {
    if (showRefreshing) setRefreshing(true);
    else setLoading(true);
    setError('');
    try {
      const res = await api.arrCommandCenter();
      setData(res);
    } catch (e: any) {
      setError(e.message ?? 'Failed to load forecast.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSort = useCallback((col: SortKey) => {
    setSortKey((prev) => {
      if (prev === col) {
        setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'));
        return col;
      }
      setSortDir('desc');
      return col;
    });
  }, []);

  const top20 = useMemo(() => {
    if (!data?.accounts) return [];
    return sortAccounts(data.accounts, 'weighted_risk_value', 'desc').slice(0, 20);
  }, [data?.accounts]);

  const sortedAccounts = useMemo(() => sortAccounts(top20, sortKey, sortDir), [top20, sortKey, sortDir]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)] py-12">
        <Loader2 size={14} className="animate-spin" />
        Building revenue forecast…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-start gap-3 p-4 rounded-xl bg-red-500/8 border border-red-500/20 text-sm text-red-400 max-w-lg">
        <AlertCircle size={16} className="shrink-0 mt-0.5" />
        <div>
          <p className="font-medium">Failed to load</p>
          <p className="text-xs mt-0.5 opacity-80">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* ── Page header ────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-[var(--color-text)]">90-Day Revenue Forecast</h1>
          <p className="text-sm text-[var(--color-text-muted)] mt-1">
            Portfolio-level ARR outlook, renewal exposure, and concentration risk.
          </p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-xl border border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-text-muted)] disabled:opacity-40 transition-colors"
        >
          {refreshing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          Refresh
        </button>
      </div>

      {(!data || !data.has_predictions) ? (
        <EmptyState />
      ) : (
        <>
          {/* ── Coverage notes ─────────────────────────────────────────────── */}
          {(data.summary?.coverage_notes ?? []).length > 0 && (
            <div className="flex flex-col gap-1.5">
              {data.summary!.coverage_notes.map((note, i) => (
                <div key={i} className="flex items-start gap-2 text-xs text-amber-400 bg-amber-500/8 border border-amber-500/15 rounded-lg px-3 py-2">
                  <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                  {note}
                </div>
              ))}
            </div>
          )}

          {/* ── Section 1: 90-Day Forecast Scenarios ───────────────────────── */}
          {data.forecast && (
            <section>
              <div className="flex items-center gap-2 mb-4">
                <TrendingDown size={15} className="text-[var(--color-text-muted)]" />
                <h2 className="text-sm font-semibold text-[var(--color-text)]">90-Day ARR Scenarios</h2>
                <span className="text-[11px] text-[var(--color-text-muted)] ml-1">
                  {data.forecast.accounts_in_window} account{data.forecast.accounts_in_window !== 1 ? 's' : ''} renewing within 90 days
                  {' · '}current ARR {formatCurrency(data.forecast.current_arr)}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <ScenarioCard
                  label="Best Case"
                  arr={data.forecast.best_case.arr}
                  arrLost={data.forecast.best_case.arr_lost}
                  currentArr={data.forecast.current_arr}
                  variant="best"
                  assumption={data.forecast.best_case.assumption}
                />
                <ScenarioCard
                  label="Expected"
                  arr={data.forecast.expected.arr}
                  arrLost={data.forecast.expected.arr_lost}
                  currentArr={data.forecast.current_arr}
                  variant="expected"
                />
                <ScenarioCard
                  label="Worst Case"
                  arr={data.forecast.worst_case.arr}
                  arrLost={data.forecast.worst_case.arr_lost}
                  currentArr={data.forecast.current_arr}
                  variant="worst"
                  assumption={data.forecast.worst_case.assumption}
                />
              </div>
            </section>
          )}

          {/* ── Section 2: Renewal Risk Timeline + Concentration ────────────── */}
          <div className="grid grid-cols-2 gap-6">
            {/* Renewal timeline */}
            {data.renewal_timeline && (
              <section className="rounded-2xl border border-[var(--color-border)] bg-white p-5">
                <div className="flex items-center gap-2 mb-5">
                  <Calendar size={14} className="text-[var(--color-text-muted)]" />
                  <h2 className="text-sm font-semibold text-[var(--color-text)]">Renewal Risk by Window</h2>
                </div>
                <div className="space-y-3.5">
                  {(() => {
                    const tl = data.renewal_timeline!;
                    const maxArr = Math.max(
                      tl.next_30d.arr_total, tl.next_60d.arr_total,
                      tl.next_90d.arr_total, tl.next_180d.arr_total, 1,
                    );
                    return (
                      <>
                        <RenewalBar label="≤ 30 days" {...tl.next_30d} maxArr={maxArr} />
                        <RenewalBar label="31–60 days" {...tl.next_60d} maxArr={maxArr} />
                        <RenewalBar label="61–90 days" {...tl.next_90d} maxArr={maxArr} />
                        <RenewalBar label="91–180 days" {...tl.next_180d} maxArr={maxArr} />
                      </>
                    );
                  })()}
                </div>
                <div className="flex items-center gap-4 mt-4 pt-3 border-t border-[var(--color-border)]">
                  <div className="flex items-center gap-1.5 text-[10px] text-[var(--color-text-muted)]">
                    <div className="w-3 h-2 rounded-sm bg-[var(--color-accent)]/20" />
                    Total ARR renewing
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px] text-[var(--color-text-muted)]">
                    <div className="w-3 h-2 rounded-sm bg-[var(--color-danger)]/25" />
                    Weighted ARR at risk
                  </div>
                </div>
              </section>
            )}

            {/* Concentration risk */}
            {data.concentration && (
              <section className="rounded-2xl border border-[var(--color-border)] bg-white p-5">
                <div className="flex items-center gap-2 mb-5">
                  <Target size={14} className="text-[var(--color-text-muted)]" />
                  <h2 className="text-sm font-semibold text-[var(--color-text)]">Portfolio Concentration</h2>
                </div>
                <div className="space-y-4">
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-1">Top 10 Accounts</p>
                    <p className="text-3xl font-bold text-[var(--color-text)]">
                      {data.concentration.top10_pct_of_total.toFixed(0)}
                      <span className="text-lg font-medium text-[var(--color-text-muted)] ml-1">% of ARR</span>
                    </p>
                    <p className="text-xs text-[var(--color-text-muted)] mt-1">
                      {formatCurrency(data.concentration.top10_arr)} concentrated in your 10 largest accounts
                    </p>
                  </div>
                  <div className="pt-3 border-t border-[var(--color-border)]">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-[var(--color-text-muted)]">Top-10 ARR at risk</span>
                      <span className="font-medium text-[var(--color-danger)]">
                        {formatCurrency(data.concentration.top10_arr_at_risk)}
                      </span>
                    </div>
                    {data.concentration.top10_pct_of_total > 60 && (
                      <div className="flex items-start gap-2 mt-3 text-xs text-amber-400 bg-amber-500/8 border border-amber-500/15 rounded-lg px-3 py-2">
                        <Info size={11} className="shrink-0 mt-0.5" />
                        High concentration — more than 60% of ARR in top 10 accounts elevates churn exposure.
                      </div>
                    )}
                  </div>
                  {data.summary && (
                    <div className="pt-3 border-t border-[var(--color-border)] grid grid-cols-2 gap-3">
                      <div>
                        <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-1">Avg Portfolio Risk</p>
                        <p className="text-xl font-bold" style={{ color: riskColor(data.summary.avg_risk_pct) }}>
                          {data.summary.avg_risk_pct.toFixed(1)}%
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-1">Priority Accounts</p>
                        <p className="text-xl font-bold text-[var(--color-text)]">
                          {data.summary.priority_account_count}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </section>
            )}
          </div>

          {/* ── Section 3: Accounts That Change The Quarter ─────────────────── */}
          <section>
            <div className="mb-4">
              <h2 className="text-base font-semibold text-[var(--color-text)]">Accounts That Change The Quarter</h2>
              <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                Top {sortedAccounts.length} by ARR × churn probability — these accounts determine whether you hit or miss forecast.
              </p>
            </div>
            <div className="rounded-2xl border border-[var(--color-border)] overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="bg-[var(--color-bg-secondary)] border-b border-[var(--color-border)]">
                      <th className="py-3 pl-4 text-left text-[10px] font-semibold tracking-widest uppercase text-[var(--color-text-muted)] w-[220px]">Account</th>
                      <ColHeader label="Risk" col="churn_risk_pct" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} right />
                      <ColHeader label="ARR" col="arr" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} right />
                      <ColHeader label="Exposure" col="weighted_risk_value" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} right />
                      <ColHeader label="Renewal" col="days_until_renewal" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} right />
                      <th className="py-3 pl-4 text-left text-[10px] font-semibold tracking-widest uppercase text-[var(--color-text-muted)]">Risk Signals</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedAccounts.map((acct, idx) => (
                      <AccountRow
                        key={acct.account_id}
                        account={acct}
                        isLast={idx === sortedAccounts.length - 1}
                        onClick={() => setSelectedAccount(acct)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </>
      )}

      <ArrAccountDrawer account={selectedAccount} onClose={() => setSelectedAccount(null)} />
    </div>
  );
}
