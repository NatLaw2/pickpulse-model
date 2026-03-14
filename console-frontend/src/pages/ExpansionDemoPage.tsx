import { useEffect, useState } from 'react';
import {
  DollarSign, TrendingUp, Users, Clock, AlertTriangle, Shield,
} from 'lucide-react';
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts';
import { api, type ExpansionDemoResponse, type MatrixPoint } from '../lib/api';
import { StatCard } from '../components/StatCard';
import { formatCurrency } from '../lib/format';
import { riskColor } from '../lib/risk';

// ---------------------------------------------------------------------------
// Purely presentational helpers — no production churn state involved
// ---------------------------------------------------------------------------

function expansionColor(prob: number): string {
  if (prob >= 0.70) return '#10b981';
  if (prob >= 0.40) return '#7B61FF';
  return '#94a3b8';
}

function quadrantColor(expansionProb: number, churnRisk: number): string {
  const highExpansion = expansionProb >= 0.5;
  const highChurn = churnRisk >= 0.35;
  if (highExpansion && !highChurn) return '#10b981';  // Growth — green
  if (!highExpansion && !highChurn) return '#94a3b8'; // Stable — slate
  if (highExpansion && highChurn) return '#f59e0b';   // Critical — amber
  return '#ef4444';                                   // Save — red
}

const FEATURE_LABELS: Record<string, string> = {
  days_until_renewal: 'Renewal Proximity',
  monthly_logins: 'Monthly Usage',
  nps_score: 'NPS Score',
  support_tickets: 'Support Volume',
  days_since_last_login: 'Login Recency',
  contract_months_remaining: 'Contract Length',
  arr: 'Account Value',
  auto_renew_flag: 'Auto-Renew Status',
  seats: 'Seat Count',
  engagement_score: 'Engagement Score',
};

function featureLabel(raw: string): string {
  return FEATURE_LABELS[raw] || raw.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// Custom dot for the scatter plot — colors each point by quadrant
function MatrixDot(props: any) {
  const { cx, cy, payload } = props;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={4}
      fill={quadrantColor(payload.expansion_probability, payload.churn_risk)}
      fillOpacity={0.8}
      stroke="none"
    />
  );
}

// Custom tooltip for the scatter plot
function MatrixTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d: MatrixPoint = payload[0].payload;
  return (
    <div className="bg-white border border-[var(--color-border)] rounded-xl p-3 shadow-lg text-xs">
      <div className="font-semibold mb-1.5">{d.account_name}</div>
      <div className="text-[var(--color-text-muted)]">
        Expansion: {Math.round(d.expansion_probability * 100)}%
      </div>
      <div className="text-[var(--color-text-muted)]">
        Churn Risk: {Math.round(d.churn_risk * 100)}%
      </div>
      <div className="text-[var(--color-text-muted)]">
        Potential: {formatCurrency(d.potential_expansion_arr)}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export function ExpansionDemoPage() {
  const [data, setData] = useState<ExpansionDemoResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'arr_risk' | 'expansion'>('arr_risk');
  const [saveRate, setSaveRate] = useState(0.35);

  useEffect(() => {
    api.expansionDemo()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-sm text-[var(--color-text-muted)]">
        Loading sandbox...
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center py-20 text-sm text-[var(--color-text-muted)]">
        Failed to load sandbox data.
      </div>
    );
  }

  // ── ARR Risk tab derived values ──
  const arrRisk = data.arr_risk;
  const kpis = arrRisk.kpis;
  const buckets = arrRisk.recovery_buckets;
  const riskDrivers = arrRisk.top_risk_drivers;
  const tierCounts = arrRisk.tier_counts;
  const totalTierArr = buckets.high_confidence_saves + buckets.medium_confidence_saves + buckets.low_confidence_saves;
  const highPct = totalTierArr > 0 ? (buckets.high_confidence_saves / totalTierArr) * 100 : 0;
  const medPct  = totalTierArr > 0 ? (buckets.medium_confidence_saves / totalTierArr) * 100 : 0;
  const lowPct  = totalTierArr > 0 ? (buckets.low_confidence_saves / totalTierArr) * 100 : 0;
  const projectedRecoverable = kpis.total_arr_at_risk * saveRate;

  // ── Expansion tab derived values ──
  const expansion = data.expansion;
  const expKpis = expansion.kpis;
  const expTierArr = expansion.tier_arr;
  const totalExpTierArr = Object.values(expTierArr).reduce((a, b) => a + b, 0);
  const expHighPct = totalExpTierArr > 0 ? ((expTierArr['High'] ?? 0) / totalExpTierArr) * 100 : 0;
  const expMedPct  = totalExpTierArr > 0 ? ((expTierArr['Medium'] ?? 0) / totalExpTierArr) * 100 : 0;
  const expLowPct  = totalExpTierArr > 0 ? ((expTierArr['Low'] ?? 0) / totalExpTierArr) * 100 : 0;

  return (
    <div>
      {/* ── Persistent sandbox banner ── */}
      <div className="mb-6 px-4 py-2.5 bg-[var(--color-warning)]/10 border border-[var(--color-warning)]/25 rounded-xl flex items-center gap-3">
        <span className="text-[10px] font-bold tracking-widest uppercase text-[var(--color-warning)]">
          Sandbox · Prototype
        </span>
        <span className="text-xs text-[var(--color-text-muted)]">
          This page is an isolated prototype. No production data or churn module is connected.
        </span>
      </div>

      {/* ── Page header ── */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Overview — Sandbox</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">
          Prototype: future multi-module Overview experience
        </p>
      </div>

      {/* ── Segmented toggle ── */}
      <div className="mb-8 inline-flex bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-xl p-1">
        <button
          onClick={() => setActiveTab('arr_risk')}
          className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'arr_risk'
              ? 'bg-white text-[var(--color-text-primary)] shadow-[0_1px_3px_rgba(0,0,0,0.1)]'
              : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]'
          }`}
        >
          ARR Risk
        </button>
        <button
          onClick={() => setActiveTab('expansion')}
          className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'expansion'
              ? 'bg-white text-[var(--color-text-primary)] shadow-[0_1px_3px_rgba(0,0,0,0.1)]'
              : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]'
          }`}
        >
          Expansion Opportunities
        </button>
      </div>

      {/* ═══════════════════════════════════════════════════
          ARR RISK TAB
          Mirrors the production Overview structure exactly,
          using sandbox synthetic data only.
      ═══════════════════════════════════════════════════ */}
      {activeTab === 'arr_risk' && (
        <>
          {/* Section 1: KPI cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8">
            <StatCard
              label="ARR at Risk"
              value={formatCurrency(kpis.total_arr_at_risk)}
              sub="Probability-weighted exposure"
              icon={<DollarSign size={16} />}
              accent="var(--color-danger)"
              tooltip="Sandbox — synthetic data only."
            />
            <StatCard
              label="Accounts Requiring Action"
              value={kpis.high_risk_in_window}
              sub="High risk and renewing soon"
              icon={<AlertTriangle size={16} />}
              accent="var(--color-danger)"
              tooltip="Sandbox — synthetic data only."
            />
            <StatCard
              label="Potential ARR Protected"
              value={formatCurrency(projectedRecoverable)}
              sub={`At ${Math.round(saveRate * 100)}% save rate`}
              icon={<Shield size={16} />}
              accent="var(--color-success)"
              tooltip="Sandbox — synthetic data only."
            />
            <StatCard
              label="High-Risk Renewals"
              value={kpis.renewing_90d}
              sub="Renewing within 90 days"
              icon={<Clock size={16} />}
              accent="var(--color-warning)"
              tooltip="Sandbox — synthetic data only."
            />
          </div>

          {/* Section 2: ARR at Risk by Tier */}
          {totalTierArr > 0 && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
              <h3 className="text-sm font-semibold mb-4">ARR at Risk by Tier</h3>
              <div className="flex h-8 rounded-xl overflow-hidden mb-4">
                {highPct > 0 && (
                  <div
                    className="flex items-center justify-center text-white text-[10px] font-bold transition-all"
                    style={{ width: `${highPct}%`, background: 'var(--color-danger)' }}
                    title={`High Risk: ${formatCurrency(buckets.high_confidence_saves)}`}
                  >
                    {highPct >= 10 && formatCurrency(buckets.high_confidence_saves)}
                  </div>
                )}
                {medPct > 0 && (
                  <div
                    className="flex items-center justify-center text-white text-[10px] font-bold transition-all"
                    style={{ width: `${medPct}%`, background: 'var(--color-warning)' }}
                    title={`Medium Risk: ${formatCurrency(buckets.medium_confidence_saves)}`}
                  >
                    {medPct >= 10 && formatCurrency(buckets.medium_confidence_saves)}
                  </div>
                )}
                {lowPct > 0 && (
                  <div
                    className="flex items-center justify-center text-white text-[10px] font-bold transition-all"
                    style={{ width: `${lowPct}%`, background: 'var(--color-success)' }}
                    title={`Low Risk: ${formatCurrency(buckets.low_confidence_saves)}`}
                  >
                    {lowPct >= 10 && formatCurrency(buckets.low_confidence_saves)}
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-6 text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-sm" style={{ background: 'var(--color-danger)' }} />
                  <span className="text-[var(--color-text-secondary)]">High Risk</span>
                  <span className="font-bold">{formatCurrency(buckets.high_confidence_saves)}</span>
                  <span className="text-xs text-[var(--color-text-muted)]">({tierCounts['High Risk'] ?? 0} accounts)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-sm" style={{ background: 'var(--color-warning)' }} />
                  <span className="text-[var(--color-text-secondary)]">Medium Risk</span>
                  <span className="font-bold">{formatCurrency(buckets.medium_confidence_saves)}</span>
                  <span className="text-xs text-[var(--color-text-muted)]">({tierCounts['Medium Risk'] ?? 0} accounts)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-sm" style={{ background: 'var(--color-success)' }} />
                  <span className="text-[var(--color-text-secondary)]">Low Risk</span>
                  <span className="font-bold">{formatCurrency(buckets.low_confidence_saves)}</span>
                  <span className="text-xs text-[var(--color-text-muted)]">({tierCounts['Low Risk'] ?? 0} accounts)</span>
                </div>
              </div>
            </div>
          )}

          {/* Section 3: Top 10 Accounts to Save Now */}
          <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
            <h3 className="text-sm font-semibold mb-4">Top 10 Accounts To Save Now</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-[var(--color-text-muted)] uppercase tracking-wider border-b border-[var(--color-border)]">
                    <th className="py-2 pr-3">Account</th>
                    <th className="py-2 pr-3 text-right">Risk</th>
                    <th className="py-2 pr-3 text-right">ARR</th>
                    <th className="py-2 pr-3 text-right">ARR at Risk</th>
                    <th className="py-2 pr-3">Renewal</th>
                  </tr>
                </thead>
                <tbody>
                  {arrRisk.top_at_risk.map((row, i) => (
                    <tr
                      key={row.account_id}
                      className={`border-b border-[var(--color-border)]/50 ${i % 2 === 1 ? 'bg-[var(--color-bg-primary)]' : ''}`}
                    >
                      <td className="py-2.5 pr-3 font-medium text-xs">{row.account_name}</td>
                      <td className="py-2.5 pr-3 text-right">
                        <span
                          className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold"
                          style={{ background: `${riskColor(row.churn_risk_pct)}18`, color: riskColor(row.churn_risk_pct) }}
                        >
                          {row.churn_risk_pct}%
                        </span>
                      </td>
                      <td className="py-2.5 pr-3 text-right text-xs">{formatCurrency(row.arr)}</td>
                      <td className="py-2.5 pr-3 text-right text-xs font-bold text-[var(--color-danger)]">
                        {formatCurrency(row.arr_at_risk)}
                      </td>
                      <td className="py-2.5 pr-3 text-xs">
                        <span className={`px-2 py-0.5 rounded-lg text-[10px] font-medium ${
                          row.days_until_renewal <= 30
                            ? 'bg-red-50 text-[var(--color-danger)]'
                            : row.days_until_renewal <= 90
                            ? 'bg-amber-50 text-[var(--color-warning)]'
                            : 'bg-[var(--color-bg-primary)] text-[var(--color-text-secondary)]'
                        }`}>
                          {row.days_until_renewal}d
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Section 4: Revenue Recovery Simulation */}
          <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp size={16} className="text-[var(--color-success)]" />
              <h3 className="text-sm font-semibold">Revenue Recovery Simulation</h3>
            </div>
            <p className="text-xs text-[var(--color-text-secondary)] mb-5">
              Estimate recoverable ARR by adjusting the assumed save rate.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
              <div>
                <label className="text-xs text-[var(--color-text-muted)] block mb-2">
                  Assumed Save Rate:{' '}
                  <span className="font-bold text-[var(--color-text-primary)]">
                    {Math.round(saveRate * 100)}%
                  </span>
                </label>
                <input
                  type="range" min={20} max={60} step={5}
                  value={Math.round(saveRate * 100)}
                  onChange={(e) => setSaveRate(Number(e.target.value) / 100)}
                  className="w-full accent-[var(--color-success)]"
                />
                <div className="flex justify-between text-[10px] text-[var(--color-text-muted)] mt-1">
                  <span>Conservative (20%)</span>
                  <span>Aggressive (60%)</span>
                </div>
              </div>
              <div className="text-center">
                <div className="text-xs text-[var(--color-text-muted)] mb-1">Total ARR at Risk</div>
                <div className="text-2xl font-bold text-[var(--color-danger)]">
                  {formatCurrency(kpis.total_arr_at_risk)}
                </div>
              </div>
              <div className="text-center">
                <div className="text-xs text-[var(--color-text-muted)] mb-1">Projected Recoverable ARR</div>
                <div className="text-2xl font-bold text-[var(--color-success)]">
                  {formatCurrency(projectedRecoverable)}
                </div>
                <div className="text-[10px] text-[var(--color-text-muted)] mt-1">
                  at {Math.round(saveRate * 100)}% save rate
                </div>
              </div>
            </div>
          </div>

          {/* Section 5: Portfolio Risk Drivers */}
          {riskDrivers.length > 0 && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
              <h3 className="text-sm font-semibold mb-4">Portfolio Risk Drivers</h3>
              <p className="text-xs text-[var(--color-text-secondary)] mb-4">
                The features most influencing churn predictions across the portfolio
              </p>
              <div className="space-y-3">
                {riskDrivers.map((d, i) => {
                  const maxImp = Math.max(...riskDrivers.map(r => Math.abs(r.importance)), 0.01);
                  const pct = (Math.abs(d.importance) / maxImp) * 100;
                  return (
                    <div key={d.feature} className="flex items-center gap-3">
                      <span className="text-xs text-[var(--color-text-secondary)] w-36 shrink-0">
                        {featureLabel(d.feature)}
                      </span>
                      <div className="flex-1 h-2.5 bg-[var(--color-bg-primary)] rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${pct}%`,
                            background: i === 0
                              ? 'var(--color-danger)'
                              : i === 1
                              ? 'var(--color-warning)'
                              : 'var(--color-accent)',
                          }}
                        />
                      </div>
                      <span className="text-xs text-[var(--color-text-muted)] w-14 text-right font-mono">
                        +{d.importance.toFixed(3)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}

      {/* ═══════════════════════════════════════════════════
          EXPANSION OPPORTUNITIES TAB
          Same layout structure as ARR Risk, expansion metrics.
      ═══════════════════════════════════════════════════ */}
      {activeTab === 'expansion' && (
        <>
          {/* Section 1: KPI cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8">
            <StatCard
              label="Expansion ARR Potential"
              value={formatCurrency(expKpis.total_expansion_potential)}
              sub="Across all expansion signals"
              icon={<TrendingUp size={16} />}
              accent="var(--color-success)"
            />
            <StatCard
              label="High Expansion Accounts"
              value={expKpis.high_expansion_accounts}
              sub="Expansion probability ≥ 70%"
              icon={<Users size={16} />}
              accent="var(--color-success)"
            />
            <StatCard
              label="Avg Expansion Probability"
              value={`${Math.round(expKpis.avg_expansion_probability * 100)}%`}
              sub="Portfolio average"
              icon={<DollarSign size={16} />}
              accent="var(--color-accent)"
            />
            <StatCard
              label="Expansion Likely ≤ 90 Days"
              value={expKpis.expansion_likely_90d}
              sub="Expansion probability ≥ 60%"
              icon={<Clock size={16} />}
              accent="var(--color-warning)"
            />
          </div>

          {/* Section 2: Expansion Opportunity by Tier */}
          {totalExpTierArr > 0 && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
              <h3 className="text-sm font-semibold mb-4">Expansion Opportunity by Tier</h3>
              <div className="flex h-8 rounded-xl overflow-hidden mb-4">
                {expHighPct > 0 && (
                  <div
                    className="flex items-center justify-center text-white text-[10px] font-bold transition-all"
                    style={{ width: `${expHighPct}%`, background: '#10b981' }}
                    title={`High: ${formatCurrency(expTierArr['High'] ?? 0)}`}
                  >
                    {expHighPct >= 10 && formatCurrency(expTierArr['High'] ?? 0)}
                  </div>
                )}
                {expMedPct > 0 && (
                  <div
                    className="flex items-center justify-center text-white text-[10px] font-bold transition-all"
                    style={{ width: `${expMedPct}%`, background: 'var(--color-accent)' }}
                    title={`Medium: ${formatCurrency(expTierArr['Medium'] ?? 0)}`}
                  >
                    {expMedPct >= 10 && formatCurrency(expTierArr['Medium'] ?? 0)}
                  </div>
                )}
                {expLowPct > 0 && (
                  <div
                    className="flex items-center justify-center text-white text-[10px] font-bold transition-all"
                    style={{ width: `${expLowPct}%`, background: '#94a3b8' }}
                    title={`Low: ${formatCurrency(expTierArr['Low'] ?? 0)}`}
                  >
                    {expLowPct >= 10 && formatCurrency(expTierArr['Low'] ?? 0)}
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-6 text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-sm" style={{ background: '#10b981' }} />
                  <span className="text-[var(--color-text-secondary)]">High</span>
                  <span className="font-bold">{formatCurrency(expTierArr['High'] ?? 0)}</span>
                  <span className="text-xs text-[var(--color-text-muted)]">({expansion.tier_counts['High'] ?? 0} accounts)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-sm" style={{ background: 'var(--color-accent)' }} />
                  <span className="text-[var(--color-text-secondary)]">Medium</span>
                  <span className="font-bold">{formatCurrency(expTierArr['Medium'] ?? 0)}</span>
                  <span className="text-xs text-[var(--color-text-muted)]">({expansion.tier_counts['Medium'] ?? 0} accounts)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-sm" style={{ background: '#94a3b8' }} />
                  <span className="text-[var(--color-text-secondary)]">Low</span>
                  <span className="font-bold">{formatCurrency(expTierArr['Low'] ?? 0)}</span>
                  <span className="text-xs text-[var(--color-text-muted)]">({expansion.tier_counts['Low'] ?? 0} accounts)</span>
                </div>
              </div>
            </div>
          )}

          {/* Section 3: Top Expansion Opportunities */}
          <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
            <h3 className="text-sm font-semibold mb-4">Top Expansion Opportunities</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-[var(--color-text-muted)] uppercase tracking-wider border-b border-[var(--color-border)]">
                    <th className="py-2 pr-3">Account</th>
                    <th className="py-2 pr-3 text-right">Expansion Prob.</th>
                    <th className="py-2 pr-3 text-right">Current ARR</th>
                    <th className="py-2 pr-3 text-right">Potential Expansion</th>
                    <th className="py-2 pr-3">Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {expansion.top_opportunities.map((row, i) => (
                    <tr
                      key={`${row.account_name}-${i}`}
                      className={`border-b border-[var(--color-border)]/50 ${i % 2 === 1 ? 'bg-[var(--color-bg-primary)]' : ''}`}
                    >
                      <td className="py-2.5 pr-3 font-medium text-xs">{row.account_name}</td>
                      <td className="py-2.5 pr-3 text-right">
                        <span
                          className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold"
                          style={{
                            background: `${expansionColor(row.expansion_probability)}18`,
                            color: expansionColor(row.expansion_probability),
                          }}
                        >
                          {Math.round(row.expansion_probability * 100)}%
                        </span>
                      </td>
                      <td className="py-2.5 pr-3 text-right text-xs">{formatCurrency(row.current_arr)}</td>
                      <td className="py-2.5 pr-3 text-right text-xs font-bold" style={{ color: '#10b981' }}>
                        {formatCurrency(row.potential_expansion_arr)}
                      </td>
                      <td className="py-2.5 pr-3 text-xs text-[var(--color-text-secondary)]">
                        {row.expansion_signal}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Section 4: Account Opportunity Matrix */}
          <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
            <h3 className="text-sm font-semibold mb-1">Account Opportunity Matrix</h3>
            <p className="text-xs text-[var(--color-text-secondary)] mb-5">
              Each dot is an account. Quadrants help prioritize which accounts to expand vs. save vs. monitor.
            </p>

            {/* Quadrant legend */}
            <div className="flex flex-wrap gap-2 mb-6">
              {[
                { color: '#10b981', label: 'Growth Accounts',   desc: 'Low churn · High expansion' },
                { color: '#f59e0b', label: 'Critical Accounts', desc: 'High churn · High expansion' },
                { color: '#ef4444', label: 'Save Accounts',     desc: 'High churn · Low expansion' },
                { color: '#94a3b8', label: 'Stable Accounts',   desc: 'Low churn · Low expansion' },
              ].map(({ color, label, desc }) => (
                <div
                  key={label}
                  className="flex items-center gap-2 px-3 py-1.5 bg-[var(--color-bg-primary)] rounded-lg"
                >
                  <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color }} />
                  <div>
                    <div className="text-[11px] font-medium text-[var(--color-text-primary)]">{label}</div>
                    <div className="text-[10px] text-[var(--color-text-muted)]">{desc}</div>
                  </div>
                </div>
              ))}
            </div>

            <ResponsiveContainer width="100%" height={380}>
              <ScatterChart margin={{ top: 10, right: 20, bottom: 36, left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis
                  type="number"
                  dataKey="expansion_probability"
                  domain={[0, 1]}
                  name="Expansion Probability"
                  tickFormatter={(v) => `${Math.round(v * 100)}%`}
                  tick={{ fontSize: 10 }}
                  label={{
                    value: 'Expansion Probability →',
                    position: 'insideBottom',
                    offset: -20,
                    style: { fontSize: 11, fill: '#94a3b8' },
                  }}
                />
                <YAxis
                  type="number"
                  dataKey="churn_risk"
                  domain={[0, 1]}
                  name="Churn Risk"
                  tickFormatter={(v) => `${Math.round(v * 100)}%`}
                  tick={{ fontSize: 10 }}
                  label={{
                    value: 'Churn Risk →',
                    angle: -90,
                    position: 'insideLeft',
                    offset: 15,
                    style: { fontSize: 11, fill: '#94a3b8' },
                  }}
                />
                <RechartsTooltip content={<MatrixTooltip />} cursor={{ strokeDasharray: '3 3' }} />
                {/* Quadrant dividers */}
                <ReferenceLine x={0.5}  stroke="#e2e8f0" strokeDasharray="4 4" strokeWidth={1.5} />
                <ReferenceLine y={0.35} stroke="#e2e8f0" strokeDasharray="4 4" strokeWidth={1.5} />
                <Scatter data={expansion.matrix_points} shape={<MatrixDot />} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}
