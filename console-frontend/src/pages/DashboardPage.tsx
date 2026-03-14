import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { DollarSign, Clock, AlertTriangle, Shield, TrendingUp, ChevronRight, FileText, X, Mail, Copy, Loader2 } from 'lucide-react';
import { api, type DashboardResponse } from '../lib/api';
import { StatCard } from '../components/StatCard';
import { RevenueImpactCard } from '../components/RevenueImpactCard';
import { AccountDetailDrawer } from '../components/AccountDetailDrawer';
import { useDataset } from '../lib/DatasetContext';
import { usePredictions } from '../lib/PredictionContext';
import { useExecutiveSummary } from '../lib/ExecutiveSummaryContext';
import { riskColor } from '../lib/risk';
import { formatCurrency } from '../lib/format';

const FEATURE_LABELS: Record<string, string> = {
  days_since_last_login: 'Login Recency',
  monthly_logins: 'Monthly Usage',
  support_tickets: 'Support Volume',
  nps_score: 'NPS Score',
  contract_months_remaining: 'Contract Length',
  days_until_renewal: 'Renewal Proximity',
  auto_renew_flag: 'Auto-Renew Status',
  seats: 'Seat Count',
  arr: 'Account Value',
  company_size: 'Company Size',
};

function featureLabel(raw: string): string {
  return FEATURE_LABELS[raw] || raw.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function DashboardPage() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [saveRate, setSaveRate] = useState(0.35);
  const navigate = useNavigate();
  const { dataset } = useDataset();
  const { predictions } = usePredictions();

  // Drawer state
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Executive summary (shared context, persisted via sessionStorage)
  const { summaryData, setSummaryData, showModal: showSummaryModal, setShowModal: setShowSummaryModal, buildMailtoUrl, getPlainText } = useExecutiveSummary();
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const fetchDashboard = useCallback((rate: number) => {
    api.dashboard(rate).then(setData).catch(console.error);
  }, []);

  useEffect(() => {
    fetchDashboard(saveRate);
  }, [fetchDashboard, saveRate]);

  // Auto-generate executive summary when dashboard data loads with predictions
  useEffect(() => {
    if (!data || !data.kpis || data.kpis.total_arr_at_risk === 0 || summaryData) return;
    generateExecutiveSummary(data);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const generateExecutiveSummary = async (dashData: DashboardResponse) => {
    setSummaryLoading(true);
    try {
      let recipients: string[] = [];
      try {
        const settings = await api.getNotificationSettings();
        recipients = settings.recipients;
      } catch { /* no settings configured */ }

      const topAccounts = (dashData.top_at_risk ?? []).slice(0, 5).map((p) => ({
        account_id: p.account_id,
        churn_risk_pct: p.churn_risk_pct,
        arr: p.arr,
        arr_at_risk: p.arr_at_risk,
        days_until_renewal: p.days_until_renewal,
        tier: p.tier,
      }));

      const riskDriverNames = (dashData.top_risk_drivers ?? []).map(
        (d) => featureLabel(d.feature)
      );

      const tierCountLabels: string[] = [];
      const tc = dashData.tier_counts ?? {};
      if (tc['High Risk']) tierCountLabels.push(`${tc['High Risk']} accounts at High Risk`);
      if (tc['Medium Risk']) tierCountLabels.push(`${tc['Medium Risk']} accounts at Medium Risk`);
      const driverSummary = [...riskDriverNames.slice(0, 3), ...tierCountLabels];

      const res = await api.sendExecutiveSummary({
        recipients,
        total_arr_at_risk: dashData.kpis.total_arr_at_risk,
        projected_recoverable_arr: dashData.kpis.projected_recoverable_arr,
        save_rate: dashData.kpis.assumed_save_rate,
        high_risk_in_window: dashData.kpis.high_risk_in_window,
        renewing_90d: dashData.kpis.renewing_90d,
        top_accounts: topAccounts,
        tier_counts: dashData.tier_counts ?? {},
        risk_drivers: driverSummary,
      });

      setSummaryData(res);
    } catch (err) {
      console.error('[executive-summary] failed:', err);
    } finally {
      setSummaryLoading(false);
    }
  };

  const mod = data?.module;
  const kpis = data?.kpis;
  const buckets = data?.recovery_buckets;
  const topRisk = data?.top_at_risk ?? [];
  const tierCounts = data?.tier_counts ?? {};
  const riskDrivers = data?.top_risk_drivers ?? [];

  // Risk distribution bar data
  const totalTierArr = (buckets?.high_confidence_saves ?? 0) + (buckets?.medium_confidence_saves ?? 0) + (buckets?.low_confidence_saves ?? 0);
  const highPct = totalTierArr > 0 ? (buckets!.high_confidence_saves / totalTierArr) * 100 : 0;
  const medPct = totalTierArr > 0 ? (buckets!.medium_confidence_saves / totalTierArr) * 100 : 0;
  const lowPct = totalTierArr > 0 ? (buckets!.low_confidence_saves / totalTierArr) * 100 : 0;

  // Find the selected prediction row — look in dashboard top_at_risk first, then predictions context
  const selectedRow = selectedId
    ? topRisk.find((r) => r.account_id === selectedId)
      ?? predictions?.predictions?.find((p) => p.account_id === selectedId)
      ?? null
    : null;

  return (
    <div>
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold">Overview</h1>
              {dataset?.is_demo && (
                <span
                  className="px-2.5 py-1 bg-[var(--color-warning)]/10 border border-[var(--color-warning)]/25 rounded-lg text-[10px] font-bold tracking-widest uppercase text-[var(--color-warning)]"
                  title="Illustrative metrics generated from a sample dataset. Upload your own data for production-grade insights."
                >
                  Sample Data
                </span>
              )}
            </div>
            <p className="text-sm text-[var(--color-text-secondary)] mt-1">
              ARR protection status and renewal pipeline health
            </p>
          </div>
          {summaryData ? (
            <button
              onClick={() => setShowSummaryModal(true)}
              className="btn-primary flex items-center gap-2 px-5 py-2.5 text-white rounded-xl text-sm font-medium"
            >
              <FileText size={14} />
              View Executive Brief
            </button>
          ) : kpis && kpis.total_arr_at_risk > 0 && (
            <button
              onClick={() => data && generateExecutiveSummary(data)}
              disabled={summaryLoading}
              className="btn-primary flex items-center gap-2 px-5 py-2.5 text-white rounded-xl text-sm font-medium disabled:opacity-50"
            >
              {summaryLoading ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}
              {summaryLoading ? 'Generating...' : 'Generate Executive Brief'}
            </button>
          )}
        </div>
      </div>

      {mod && (
        <>
          {/* Section 1: Hero KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8">
            <StatCard
              label="ARR at Risk"
              value={kpis ? formatCurrency(kpis.total_arr_at_risk) : '—'}
              sub="Probability-weighted exposure"
              icon={<DollarSign size={16} />}
              accent="var(--color-danger)"
              tooltip="Each account's ARR multiplied by its churn probability, summed across the portfolio."
              onClick={() => navigate('/predict')}
            />
            <StatCard
              label="Accounts Requiring Action"
              value={kpis?.high_risk_in_window ?? '—'}
              sub="High risk and renewing soon"
              icon={<AlertTriangle size={16} />}
              accent="var(--color-danger)"
              tooltip="Accounts with ≥70% churn probability that also renew within 90 days. These need immediate outreach."
              onClick={() => navigate('/predict')}
            />
            <StatCard
              label="Potential ARR Protected"
              value={kpis ? formatCurrency(kpis.projected_recoverable_arr) : '—'}
              sub={kpis ? `At ${Math.round(kpis.assumed_save_rate * 100)}% save rate` : undefined}
              icon={<Shield size={16} />}
              accent="var(--color-success)"
              tooltip="Estimated ARR that could be retained through proactive intervention, based on your assumed save rate."
              onClick={() => navigate('/predict')}
            />
            <StatCard
              label="High-Risk Renewals"
              value={kpis?.renewing_90d ?? '—'}
              sub="Renewing within 90 days"
              icon={<Clock size={16} />}
              accent="var(--color-warning)"
              tooltip="Total accounts with a contract renewal in the next 90 days — the highest-leverage intervention window."
              onClick={() => navigate('/predict')}
            />
          </div>

          {/* Revenue Impact Tracker — hero-level platform metric */}
          <RevenueImpactCard />

          {/* Section 2: Risk Distribution Strip */}
          {totalTierArr > 0 && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
              <h3 className="text-sm font-semibold mb-4">ARR at Risk by Tier</h3>

              {/* Stacked bar */}
              <div className="flex h-8 rounded-xl overflow-hidden mb-4">
                {highPct > 0 && (
                  <div
                    className="flex items-center justify-center text-white text-[10px] font-bold transition-all"
                    style={{ width: `${highPct}%`, background: 'var(--color-danger)' }}
                    title={`High Risk: ${formatCurrency(buckets!.high_confidence_saves)}`}
                  >
                    {highPct >= 10 && formatCurrency(buckets!.high_confidence_saves)}
                  </div>
                )}
                {medPct > 0 && (
                  <div
                    className="flex items-center justify-center text-white text-[10px] font-bold transition-all"
                    style={{ width: `${medPct}%`, background: 'var(--color-warning)' }}
                    title={`Medium Risk: ${formatCurrency(buckets!.medium_confidence_saves)}`}
                  >
                    {medPct >= 10 && formatCurrency(buckets!.medium_confidence_saves)}
                  </div>
                )}
                {lowPct > 0 && (
                  <div
                    className="flex items-center justify-center text-white text-[10px] font-bold transition-all"
                    style={{ width: `${lowPct}%`, background: 'var(--color-success)' }}
                    title={`Low Risk: ${formatCurrency(buckets!.low_confidence_saves)}`}
                  >
                    {lowPct >= 10 && formatCurrency(buckets!.low_confidence_saves)}
                  </div>
                )}
              </div>

              {/* Legend */}
              <div className="flex flex-wrap gap-6 text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-sm" style={{ background: 'var(--color-danger)' }} />
                  <span className="text-[var(--color-text-secondary)]">High Risk</span>
                  <span className="font-bold">{formatCurrency(buckets!.high_confidence_saves)}</span>
                  <span className="text-xs text-[var(--color-text-muted)]">({tierCounts['High Risk'] ?? 0} accounts)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-sm" style={{ background: 'var(--color-warning)' }} />
                  <span className="text-[var(--color-text-secondary)]">Medium Risk</span>
                  <span className="font-bold">{formatCurrency(buckets!.medium_confidence_saves)}</span>
                  <span className="text-xs text-[var(--color-text-muted)]">({tierCounts['Medium Risk'] ?? 0} accounts)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-sm" style={{ background: 'var(--color-success)' }} />
                  <span className="text-[var(--color-text-secondary)]">Low Risk</span>
                  <span className="font-bold">{formatCurrency(buckets!.low_confidence_saves)}</span>
                  <span className="text-xs text-[var(--color-text-muted)]">({tierCounts['Low Risk'] ?? 0} accounts)</span>
                </div>
              </div>
            </div>
          )}

          {/* Section 3: Top 10 Accounts To Save Now */}
          <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
            <h3 className="text-sm font-semibold mb-4">Top 10 Accounts To Save Now</h3>

            {topRisk.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-[var(--color-text-muted)] uppercase tracking-wider border-b border-[var(--color-border)]">
                      <th className="py-2 pr-3">Account</th>
                      <th className="py-2 pr-3 text-right">Risk</th>
                      <th className="py-2 pr-3 text-right">ARR</th>
                      <th className="py-2 pr-3 text-right">ARR at Risk</th>
                      <th className="py-2 pr-3">Renewal</th>
                      <th className="py-2 w-8"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {topRisk.map((row, i) => (
                      <tr
                        key={row.account_id}
                        onClick={() => setSelectedId(row.account_id)}
                        className={`border-b border-[var(--color-border)]/50 hover:bg-[var(--color-accent-light)] transition-colors cursor-pointer ${
                          i % 2 === 1 ? 'bg-[var(--color-bg-primary)]' : ''
                        } ${selectedId === row.account_id ? 'bg-[var(--color-accent)]/10' : ''}`}
                      >
                        <td className="py-2.5 pr-3 font-medium text-xs">{row.account_id}</td>
                        <td className="py-2.5 pr-3 text-right">
                          <span
                            className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold"
                            style={{ background: `${riskColor(row.churn_risk_pct)}18`, color: riskColor(row.churn_risk_pct) }}
                          >
                            {row.churn_risk_pct}%
                          </span>
                        </td>
                        <td className="py-2.5 pr-3 text-right text-xs">{formatCurrency(row.arr)}</td>
                        <td className="py-2.5 pr-3 text-right text-xs font-bold text-[var(--color-danger)]">{formatCurrency(row.arr_at_risk)}</td>
                        <td className="py-2.5 pr-3 text-xs">
                          {row.days_until_renewal != null && (
                            <span className={`px-2 py-0.5 rounded-lg text-[10px] font-medium ${
                              row.days_until_renewal <= 30 ? 'bg-red-50 text-[var(--color-danger)]' :
                              row.days_until_renewal <= 90 ? 'bg-amber-50 text-[var(--color-warning)]' :
                              'bg-[var(--color-bg-primary)] text-[var(--color-text-secondary)]'
                            }`}>
                              {row.days_until_renewal}d
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 text-right">
                          <ChevronRight size={14} className="text-[var(--color-text-muted)]" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-[var(--color-text-muted)] py-6 text-center">
                No predictions generated yet. Load a dataset, train the model, then generate predictions to see at-risk accounts here.
              </p>
            )}
          </div>

          {/* Section 4: Revenue Recovery Simulation */}
          {kpis && kpis.total_arr_at_risk > 0 && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp size={16} className="text-[var(--color-success)]" />
                <h3 className="text-sm font-semibold">Revenue Recovery Simulation</h3>
              </div>
              <p className="text-xs text-[var(--color-text-secondary)] mb-5">
                Estimate recoverable ARR by adjusting the assumed save rate — the percentage of at-risk accounts successfully retained through proactive intervention.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
                <div>
                  <label className="text-xs text-[var(--color-text-muted)] block mb-2">
                    Assumed Save Rate: <span className="font-bold text-[var(--color-text-primary)]">{Math.round(saveRate * 100)}%</span>
                  </label>
                  <input
                    type="range"
                    min={20}
                    max={60}
                    step={5}
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
                    {formatCurrency(kpis.projected_recoverable_arr)}
                  </div>
                  <div className="text-[10px] text-[var(--color-text-muted)] mt-1">
                    at {Math.round(kpis.assumed_save_rate * 100)}% save rate
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Section 5: Portfolio Risk Drivers */}
          {riskDrivers.length > 0 && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
              <h3 className="text-sm font-semibold mb-4">Portfolio Risk Drivers</h3>
              <p className="text-xs text-[var(--color-text-secondary)] mb-4">
                The features most influencing churn predictions across your portfolio
              </p>
              <div className="space-y-3">
                {riskDrivers.map((d, i) => {
                  const maxImp = Math.max(...riskDrivers.map((r) => Math.abs(r.importance)), 0.01);
                  const pct = (Math.abs(d.importance) / maxImp) * 100;
                  return (
                    <div key={d.feature} className="flex items-center gap-3">
                      <span className="text-xs text-[var(--color-text-secondary)] w-36 shrink-0">{featureLabel(d.feature)}</span>
                      <div className="flex-1 h-2.5 bg-[var(--color-bg-primary)] rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${pct}%`,
                            background: i === 0 ? 'var(--color-danger)' : i === 1 ? 'var(--color-warning)' : 'var(--color-accent)',
                          }}
                        />
                      </div>
                      <span className="text-xs text-[var(--color-text-muted)] w-14 text-right font-mono">
                        {d.importance > 0 ? '+' : ''}{d.importance.toFixed(3)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}

      {!mod && (
        <div className="text-center text-[var(--color-text-secondary)] py-20">
          Loading...
        </div>
      )}

      {/* Account Detail Drawer */}
      {selectedId && selectedRow && (
        <AccountDetailDrawer
          customerId={selectedId}
          prediction={selectedRow}
          onClose={() => setSelectedId(null)}
        />
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
            <div className="flex-1 overflow-y-auto p-6 bg-[var(--color-bg-primary)]">
              <div
                className="bg-white rounded-xl shadow-[0_1px_4px_rgba(0,0,0,0.08)] overflow-hidden"
                dangerouslySetInnerHTML={{ __html: summaryData.html_body }}
              />
            </div>
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
