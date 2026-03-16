import { useEffect, useState } from 'react';
import { TrendingUp, Clock } from 'lucide-react';
import { api, type RevenueImpactResponse } from '../lib/api';
import { formatCurrency } from '../lib/format';

export function RevenueImpactCard() {
  const [data, setData] = useState<RevenueImpactResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.revenueImpact()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading || !data) return null;

  // Real tenant with predictions loaded but no confirmed history yet — show pending state.
  if (data.pending_history) {
    return (
      <div className="bg-white border border-[var(--color-border)] rounded-2xl px-6 py-4 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)] flex items-start gap-3">
        <Clock size={14} className="text-[var(--color-text-muted)] mt-0.5 shrink-0" />
        <div>
          <p className="text-xs font-medium text-[var(--color-text-secondary)]">Confirmed ARR Retained</p>
          <p className="text-[11px] text-[var(--color-text-muted)] mt-0.5">
            This metric populates once accounts marked as actioned are tracked through renewal.
            Mark at-risk accounts as renewed in the Accounts view to begin tracking.
          </p>
        </div>
      </div>
    );
  }

  // No data at all (no predictions loaded, real tenant) — show nothing.
  if (!data.illustrative && data.total_revenue_impact === 0) return null;

  // Sub-metric labels differ between illustrative (demo) and real-data modes.
  const savesLabel = data.illustrative ? 'Estimated Renewal Retention' : 'Confirmed Renewals';
  const reductionLabel = data.illustrative ? 'Estimated Risk Reduction' : 'Risk Reduction';

  return (
    <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover relative overflow-hidden">
      {/* Green accent bar */}
      <div
        className="absolute top-0 left-0 right-0 h-[3px]"
        style={{ background: 'linear-gradient(90deg, var(--color-success), var(--color-success)88 70%, transparent)' }}
      />

      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6">
        {/* Left: main metric */}
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp size={16} className="text-[var(--color-success)]" />
            <span className="text-xs text-[var(--color-text-muted)] uppercase tracking-wider font-medium">
              Revenue Impact
            </span>
            {data.illustrative && (
              <span className="px-2 py-0.5 bg-[var(--color-warning)]/10 border border-[var(--color-warning)]/25 rounded-md text-[10px] font-bold tracking-wide uppercase text-[var(--color-warning)]">
                Illustrative · Demo
              </span>
            )}
          </div>

          <div className="text-3xl font-bold tracking-tight text-[var(--color-success)]">
            {formatCurrency(data.total_revenue_impact)}
          </div>

          {/* Main label — always "Estimated ARR Protected" in illustrative mode */}
          <div className="text-xs text-[var(--color-text-secondary)] mt-2">
            {data.label}
          </div>

          <div className="text-[11px] text-[var(--color-text-muted)] mt-1 max-w-xs">
            {data.subtext}
          </div>
        </div>

        {/* Right: breakout rows */}
        <div className="flex flex-col gap-3 min-w-[240px]">
          <div className="flex items-center justify-between gap-8">
            <span className="text-xs text-[var(--color-text-secondary)]">{savesLabel}</span>
            <span className="text-sm font-bold text-[var(--color-success)]">
              {formatCurrency(data.confirmed_saves)}
            </span>
          </div>
          <div className="h-px bg-[var(--color-border)]" />
          <div className="flex items-center justify-between gap-8">
            <span className="text-xs text-[var(--color-text-secondary)]">{reductionLabel}</span>
            <span className="text-sm font-bold" style={{ color: 'var(--color-accent)' }}>
              {formatCurrency(data.risk_reduction)}
            </span>
          </div>
          <div className="h-px bg-[var(--color-border)]" />
          <div className="flex items-center justify-between gap-8">
            <span className="text-xs text-[var(--color-text-secondary)]">Accounts Impacted</span>
            <span className="text-sm font-bold text-[var(--color-text-primary)]">
              {data.accounts_impacted}
            </span>
          </div>
        </div>
      </div>

      {data.illustrative && (
        <div className="mt-5 pt-4 border-t border-[var(--color-border)]">
          <p className="text-[11px] text-[var(--color-text-muted)]">
            Based on synthetic data and model-driven assumptions. Upload production data to track confirmed financial impact.
          </p>
        </div>
      )}
    </div>
  );
}
