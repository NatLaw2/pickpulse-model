/**
 * ArrAccountDrawer
 *
 * Slides in from the right when the user clicks an account row in the
 * ARR Command Center. Shows:
 *   1. Account identity + risk badge
 *   2. Why this account needs attention (translated risk drivers)
 *   3. Recommended actions (rule-based, tied to real signals)
 *   4. Data quality / missing information notes
 */
import { useEffect, useState } from 'react';
import {
  X, Loader2, AlertCircle, ChevronRight,
  Users, Shield, Activity, Info,
} from 'lucide-react';
import { api, type ArrAccountDetails, type ArrRankedAccount } from '../lib/api';
import { formatCurrency } from '../lib/format';

const OWNER_ROLE_COLORS: Record<string, string> = {
  CSM: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  AE: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  Exec: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  Support: 'bg-red-500/10 text-red-400 border-red-500/20',
};

function ownerBadge(role: string) {
  const cls = OWNER_ROLE_COLORS[role] ?? 'bg-gray-500/10 text-gray-400 border-gray-500/20';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${cls}`}>
      {role}
    </span>
  );
}

function riskBadgeStyle(pct: number): string {
  if (pct >= 40) return 'bg-red-500/15 text-red-400 border-red-500/25';
  if (pct >= 25) return 'bg-amber-500/15 text-amber-400 border-amber-500/25';
  return 'bg-green-500/15 text-green-400 border-green-500/25';
}

function DirectionIcon({ direction }: { direction: string }) {
  if (direction === 'increases_risk') {
    return <span className="text-[var(--color-danger)] text-xs font-bold">↑</span>;
  }
  return <span className="text-[var(--color-success)] text-xs font-bold">↓</span>;
}

interface Props {
  account: ArrRankedAccount | null;
  onClose: () => void;
}

export function ArrAccountDrawer({ account, onClose }: Props) {
  const [details, setDetails] = useState<ArrAccountDetails | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const isOpen = account !== null;

  useEffect(() => {
    if (!account) {
      setDetails(null);
      setError('');
      return;
    }
    let cancelled = false;
    setLoading(true);
    setDetails(null);
    setError('');
    api.accountCommandCenterDetails(account.account_id)
      .then((d) => { if (!cancelled) setDetails(d); })
      .catch((e: any) => { if (!cancelled) setError(e.message ?? 'Failed to load account details.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [account?.account_id]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, onClose]);

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 bg-black/40 z-40 transition-opacity duration-200 ${isOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div
        className={`fixed top-0 right-0 h-screen w-[480px] max-w-full bg-[var(--color-bg-primary)] border-l border-[var(--color-border)] z-50 flex flex-col shadow-2xl transition-transform duration-200 ease-out ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-[var(--color-border)] shrink-0">
          <div className="flex-1 min-w-0 pr-3">
            {account ? (
              <>
                <h2 className="text-base font-semibold text-[var(--color-text)] truncate">
                  {account.name}
                </h2>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border ${riskBadgeStyle(account.churn_risk_pct)}`}>
                    {account.churn_risk_pct.toFixed(0)}% risk
                  </span>
                  {account.arr != null && (
                    <span className="text-xs text-[var(--color-text-muted)]">
                      {formatCurrency(account.arr)} ARR
                    </span>
                  )}
                  {account.has_arr && account.weighted_risk_value != null && (
                    <span className="text-xs text-[var(--color-danger)] font-medium">
                      {formatCurrency(account.weighted_risk_value)} at risk
                    </span>
                  )}
                </div>
              </>
            ) : (
              <div className="h-5 w-40 bg-[var(--color-bg-secondary)] rounded animate-pulse" />
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)] transition-colors shrink-0"
          >
            <X size={16} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
              <Loader2 size={14} className="animate-spin" />
              Loading account details…
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-red-500/8 border border-red-500/20 text-xs text-red-400">
              <AlertCircle size={13} className="shrink-0 mt-0.5" />
              {error}
            </div>
          )}

          {details && (
            <>
              {/* ── Section 1: Why this account needs attention ── */}
              <section>
                <SectionHeader icon={<Activity size={13} />} title="Why this account needs attention" />
                {details.drivers.length > 0 ? (
                  <div className="space-y-3 mt-3">
                    {details.drivers
                      .filter((d) => d.direction === 'increases_risk')
                      .slice(0, 5)
                      .map((driver, i) => (
                        <div key={i} className="p-3 rounded-xl bg-[var(--color-bg-secondary)] border border-[var(--color-border)]">
                          <div className="flex items-start gap-2">
                            <DirectionIcon direction={driver.direction} />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-[var(--color-text)]">
                                {driver.label}
                              </p>
                              <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                                {driver.description}
                              </p>
                              {/* Signal value vs benchmark */}
                              {driver.value != null && driver.retained_mean != null && (
                                <div className="mt-1.5 flex items-center gap-3 text-[10px] text-[var(--color-text-muted)]">
                                  <span>
                                    This account: <span className="font-semibold text-[var(--color-text)]">{formatSignalValue(driver.feature, driver.value)}</span>
                                  </span>
                                  <span className="text-[var(--color-border)]">·</span>
                                  <span>
                                    Healthy avg: <span className="font-semibold text-[var(--color-success)]">{formatSignalValue(driver.feature, driver.retained_mean)}</span>
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    {details.drivers.filter((d) => d.direction === 'increases_risk').length === 0 && (
                      <p className="text-sm text-[var(--color-text-muted)]">
                        No risk-increasing drivers identified for this account.
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="mt-3 text-sm text-[var(--color-text-muted)]">
                    Detailed risk driver data is not available for this account. The model may not have SHAP attribution for this prediction.
                  </p>
                )}
              </section>

              {/* ── Section 2: Recommended actions ── */}
              <section>
                <SectionHeader icon={<ChevronRight size={13} />} title="Recommended actions" />
                {details.interventions.length > 0 ? (
                  <div className="space-y-3 mt-3">
                    {details.interventions.map((intervention, i) => (
                      <div key={i} className="p-3 rounded-xl bg-[var(--color-bg-secondary)] border border-[var(--color-border)]">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-medium text-[var(--color-text)] flex-1">
                            {intervention.title}
                          </p>
                          {ownerBadge(intervention.owner_role)}
                        </div>
                        <p className="text-xs text-[var(--color-text-muted)] mt-1.5">
                          {intervention.description}
                        </p>
                        {intervention.signals.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1">
                            {intervention.signals.map((sig, si) => (
                              <span
                                key={si}
                                className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-border)]/40 text-[var(--color-text-muted)] font-mono"
                              >
                                {sig}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-sm text-[var(--color-text-muted)]">
                    No specific actions recommended — insufficient signal data for this account.
                  </p>
                )}
              </section>

              {/* ── Section 3: Data quality notes ── */}
              {details.data_quality_notes.length > 0 && (
                <section>
                  <SectionHeader icon={<Info size={13} />} title="Missing information" />
                  <div className="mt-3 space-y-1.5">
                    {details.data_quality_notes.map((note, i) => (
                      <div key={i} className="flex items-start gap-2 text-xs text-[var(--color-text-muted)]">
                        <span className="shrink-0 mt-0.5 text-[var(--color-border)]">—</span>
                        {note}
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SectionHeader({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[var(--color-text-muted)]">{icon}</span>
      <h3 className="text-xs font-semibold tracking-wide uppercase text-[var(--color-text-muted)]">
        {title}
      </h3>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatSignalValue(feature: string, value: number): string {
  if (feature.includes('days')) return `${Math.round(value)}d`;
  if (feature === 'nps_score') return `${value.toFixed(1)}/10`;
  if (feature === 'auto_renew_flag') return value === 1 ? 'On' : 'Off';
  if (feature.includes('tickets')) return Math.round(value).toString();
  if (feature.includes('logins')) return Math.round(value).toString();
  if (feature === 'arr') return formatCurrency(value);
  return value.toFixed(1);
}
