/**
 * ARR Command Center
 *
 * Executive-facing revenue risk intelligence page.
 * Shows:
 *   - Summary bar: ARR at Risk, Priority Accounts, Avg Risk, data coverage
 *   - Ranked table: "Accounts That Need Attention"
 *   - Account drawer: risk drivers + recommended actions per account
 *
 * Data is sourced from existing churn_scores_daily + accounts + account_signals_daily.
 * No speculative financial projections are shown.
 * Coverage gaps are surfaced explicitly when data is partial.
 */
import { useEffect, useState, useMemo, useCallback } from 'react';
import {
  AlertTriangle, RefreshCw, Loader2, AlertCircle,
  ChevronUp, ChevronDown, ChevronsUpDown, Info,
  DollarSign, BarChart2,
} from 'lucide-react';
import { api, type ArrCommandCenterResponse, type ArrRankedAccount } from '../lib/api';
import { ArrAccountDrawer } from '../components/ArrAccountDrawer';
import { formatCurrency } from '../lib/format';

// ─── Risk colour helpers (duplicated locally to avoid coupling) ──────────────
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

// ─── Sort helpers ────────────────────────────────────────────────────────────
type SortKey = 'weighted_risk_value' | 'churn_risk_pct' | 'arr' | 'days_until_renewal';
type SortDir = 'asc' | 'desc';

function sortAccounts(accounts: ArrRankedAccount[], key: SortKey, dir: SortDir): ArrRankedAccount[] {
  return [...accounts].sort((a, b) => {
    const av = a[key] ?? (dir === 'desc' ? -Infinity : Infinity);
    const bv = b[key] ?? (dir === 'desc' ? -Infinity : Infinity);
    return dir === 'desc' ? (bv as number) - (av as number) : (av as number) - (bv as number);
  });
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function SortIcon({ col, sortKey, sortDir }: { col: SortKey; sortKey: SortKey; sortDir: SortDir }) {
  if (col !== sortKey) return <ChevronsUpDown size={11} className="text-[var(--color-border)]" />;
  return sortDir === 'desc'
    ? <ChevronDown size={11} className="text-[var(--color-accent)]" />
    : <ChevronUp size={11} className="text-[var(--color-accent)]" />;
}

function ColHeader({
  label,
  col,
  sortKey,
  sortDir,
  onSort,
  right,
}: {
  label: string;
  col: SortKey;
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (col: SortKey) => void;
  right?: boolean;
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

// ─── Empty state ─────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="w-14 h-14 rounded-2xl bg-[var(--color-bg-secondary)] border border-[var(--color-border)] flex items-center justify-center mb-4">
        <BarChart2 size={24} className="text-[var(--color-text-muted)]" />
      </div>
      <h3 className="text-base font-semibold text-[var(--color-text)] mb-2">
        No predictions available yet
      </h3>
      <p className="text-sm text-[var(--color-text-muted)] max-w-sm">
        The ARR Command Center becomes available once your accounts have been scored.
        Complete Setup → sync your CRM → train the model → score accounts.
      </p>
    </div>
  );
}

// ─── Main page ───────────────────────────────────────────────────────────────

export function ArrCommandCenterPage() {
  const [data, setData] = useState<ArrCommandCenterResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  // Table sort state — default matches backend rank (weighted risk desc)
  const [sortKey, setSortKey] = useState<SortKey>('weighted_risk_value');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Drawer state
  const [selectedAccount, setSelectedAccount] = useState<ArrRankedAccount | null>(null);

  const load = useCallback(async (showRefreshing = false) => {
    if (showRefreshing) setRefreshing(true);
    else setLoading(true);
    setError('');
    try {
      const res = await api.arrCommandCenter();
      setData(res);
    } catch (e: any) {
      setError(e.message ?? 'Failed to load ARR Command Center.');
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

  // Always anchor the view to the top 20 accounts by ARR × risk.
  // The user can re-sort within this fixed set, but the composition never changes.
  const top20 = useMemo(() => {
    if (!data?.accounts) return [];
    return sortAccounts(data.accounts, 'weighted_risk_value', 'desc').slice(0, 20);
  }, [data?.accounts]);

  const sortedAccounts = useMemo(() => {
    return sortAccounts(top20, sortKey, sortDir);
  }, [top20, sortKey, sortDir]);

  // ── Render ──────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)] py-12">
        <Loader2 size={14} className="animate-spin" />
        Loading ARR Command Center…
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

  if (!data || !data.has_predictions) {
    return (
      <div>
        <PageHeader onRefresh={() => load(true)} refreshing={refreshing} />
        <EmptyState />
      </div>
    );
  }

  const s = data.summary!;

  return (
    <div className="space-y-7">
      <PageHeader onRefresh={() => load(true)} refreshing={refreshing} />

      {/* ── Coverage notes ── */}
      {s.coverage_notes.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {s.coverage_notes.map((note, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-amber-400 bg-amber-500/8 border border-amber-500/15 rounded-lg px-3 py-2">
              <AlertTriangle size={12} className="shrink-0 mt-0.5" />
              {note}
            </div>
          ))}
        </div>
      )}

      {/* ── ARR at risk context line ── */}
      <div className="flex items-center gap-3 px-5 py-3.5 rounded-2xl bg-[var(--color-bg-secondary)] border border-[var(--color-border)]">
        <DollarSign size={15} className="text-[var(--color-text-muted)] shrink-0" />
        <span className="text-sm font-semibold text-[var(--color-text)]">{formatCurrency(s.arr_at_risk)}</span>
        <span className="text-xs text-[var(--color-text-muted)]">total ARR at risk across top 20 accounts</span>
        {s.arr_at_risk_is_partial && (
          <span
            title={`Based on ${s.accounts_with_arr} of ${s.total_scored_accounts} accounts with ARR data`}
            className="text-[var(--color-warning)] cursor-help"
          >
            <Info size={12} />
          </span>
        )}
      </div>

      {/* ── Ranked table ── */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-[var(--color-text)]">
              Accounts That Need Attention
            </h2>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
              Top {sortedAccounts.length} by ARR × risk. Click any row to see why and what to do next.
            </p>
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--color-border)] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-[var(--color-bg-secondary)] border-b border-[var(--color-border)]">
                  <th className="py-3 pl-4 text-left text-[10px] font-semibold tracking-widest uppercase text-[var(--color-text-muted)] w-[220px]">
                    Account
                  </th>
                  <ColHeader label="Risk" col="churn_risk_pct" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} right />
                  <ColHeader label="ARR" col="arr" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} right />
                  <ColHeader label="At Risk" col="weighted_risk_value" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} right />
                  <ColHeader label="Renewal" col="days_until_renewal" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} right />
                  <th className="py-3 pl-4 text-left text-[10px] font-semibold tracking-widest uppercase text-[var(--color-text-muted)]">
                    Top Risk Signals
                  </th>
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
      </div>

      {/* ── Account drawer ── */}
      <ArrAccountDrawer
        account={selectedAccount}
        onClose={() => setSelectedAccount(null)}
      />
    </div>
  );
}

// ─── Account row ──────────────────────────────────────────────────────────────

function AccountRow({
  account,
  isLast,
  onClick,
}: {
  account: ArrRankedAccount;
  isLast: boolean;
  onClick: () => void;
}) {
  return (
    <tr
      onClick={onClick}
      className={`group cursor-pointer transition-colors hover:bg-[var(--color-bg-secondary)] ${!isLast ? 'border-b border-[var(--color-border)]' : ''}`}
    >
      {/* Account name + badges */}
      <td className="py-3 pl-4 pr-2">
        <div className="flex items-center gap-2">
          <div className="min-w-0">
            <p className="font-medium text-[var(--color-text)] truncate max-w-[190px] group-hover:text-[var(--color-accent)] transition-colors">
              {account.name}
            </p>
            <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
              {account.missing_fields.includes('arr') && (
                <span className="text-[9px] px-1.5 py-0.5 rounded-full border border-[var(--color-border)] text-[var(--color-text-muted)]">
                  No ARR
                </span>
              )}
              {account.missing_fields.includes('renewal_timing') && (
                <span className="text-[9px] px-1.5 py-0.5 rounded-full border border-[var(--color-border)] text-[var(--color-text-muted)]">
                  No renewal date
                </span>
              )}
              {account.confidence_level && (
                <span className="text-[9px] text-[var(--color-text-muted)] capitalize">
                  {account.confidence_level} confidence
                </span>
              )}
            </div>
          </div>
        </div>
      </td>

      {/* Churn risk % */}
      <td className="py-3 pr-4 text-right">
        <span
          className={`inline-flex items-center justify-center px-2 py-0.5 rounded-full text-xs font-semibold border ${riskBg(account.churn_risk_pct)}`}
        >
          {account.churn_risk_pct.toFixed(0)}%
        </span>
      </td>

      {/* ARR */}
      <td className="py-3 pr-4 text-right text-sm text-[var(--color-text)]">
        {account.arr != null
          ? formatCurrency(account.arr)
          : <span className="text-[var(--color-text-muted)] text-xs">—</span>
        }
      </td>

      {/* Weighted at-risk value */}
      <td className="py-3 pr-4 text-right">
        {account.weighted_risk_value != null ? (
          <span className="text-sm font-medium" style={{ color: riskColor(account.churn_risk_pct) }}>
            {formatCurrency(account.weighted_risk_value)}
          </span>
        ) : (
          <span className="text-[var(--color-text-muted)] text-xs">—</span>
        )}
      </td>

      {/* Days until renewal */}
      <td className="py-3 pr-4 text-right text-sm text-[var(--color-text)]">
        {account.days_until_renewal != null ? (
          <span className={account.days_until_renewal <= 30 ? 'text-[var(--color-danger)] font-medium' : ''}>
            {Math.round(account.days_until_renewal)}d
          </span>
        ) : (
          <span className="text-[var(--color-text-muted)] text-xs">—</span>
        )}
      </td>

      {/* Top risk drivers */}
      <td className="py-3 pl-4 pr-4">
        <div className="flex flex-wrap gap-1">
          {account.top_drivers.length > 0 ? (
            account.top_drivers.slice(0, 3).map((d, i) => (
              <span
                key={i}
                className="text-[10px] px-2 py-0.5 rounded-full bg-red-500/8 border border-red-500/15 text-red-400 max-w-[160px] truncate"
                title={d.label}
              >
                {d.label}
              </span>
            ))
          ) : (
            <span className="text-[10px] text-[var(--color-text-muted)]">No driver data</span>
          )}
        </div>
      </td>
    </tr>
  );
}

// ─── Page header ──────────────────────────────────────────────────────────────

function PageHeader({ onRefresh, refreshing }: { onRefresh: () => void; refreshing: boolean }) {
  return (
    <div className="flex items-start justify-between">
      <div>
        <h1 className="text-xl font-bold text-[var(--color-text)]">ARR Command Center</h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Your 20 highest-risk accounts by ARR impact — focus here first.
        </p>
      </div>
      <button
        onClick={onRefresh}
        disabled={refreshing}
        className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-xl border border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-text-muted)] disabled:opacity-40 transition-colors"
      >
        {refreshing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
        Refresh
      </button>
    </div>
  );
}
