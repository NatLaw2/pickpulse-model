import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { DollarSign, Clock, AlertTriangle, Shield, TrendingUp, ChevronRight, FileText, X, Mail, Copy, Loader2, ExternalLink } from 'lucide-react';
import { api, type DashboardResponse, type ModelPerformance, type ProductionAccuracy, type ArrForecast, type ArrCalendarMonth, type ModelInsights } from '../lib/api';
import { StatCard } from '../components/StatCard';
import { RevenueImpactCard } from '../components/RevenueImpactCard';
import { AccountDetailDrawer } from '../components/AccountDetailDrawer';
import { useDataset } from '../lib/DatasetContext';
import { usePredictions } from '../lib/PredictionContext';
import { useExecutiveSummary } from '../lib/ExecutiveSummaryContext';
import { riskColor } from '../lib/risk';
import { formatCurrency } from '../lib/format';

const FEATURE_LABELS: Record<string, string> = {
  days_since_last_login: 'Engagement Recency',
  days_since_last_activity: 'Engagement Recency',
  monthly_logins: 'Monthly Engagement',
  support_tickets: 'Support Volume',
  nps_score: 'Customer Satisfaction',
  contract_months_remaining: 'Contract Length',
  days_until_renewal: 'Renewal Proximity',
  auto_renew_flag: 'Auto-Renew Status',
  seats: 'Seat Utilization',
  arr: 'Account Value',
  company_size: 'Company Size',
  contact_count: 'Stakeholder Coverage',
  deal_count: 'Deal Engagement',
};

function featureLabel(raw: string): string {
  return FEATURE_LABELS[raw] || raw.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function DashboardPage() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [saveRate, setSaveRate] = useState(0.35);
  const [performance, setPerformance] = useState<ModelPerformance | null>(null);
  const [productionAccuracy, setProductionAccuracy] = useState<ProductionAccuracy | null>(null);
  const [prodAccRefreshing, setProdAccRefreshing] = useState(false);
  const [arrForecast, setArrForecast] = useState<ArrForecast | null>(null);
  const [expansionRate, setExpansionRate] = useState(0.0);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [showModelHealth, setShowModelHealth] = useState(false);
  const [modelInsights, setModelInsights] = useState<ModelInsights | null>(null);
  const navigate = useNavigate();
  const { dataset } = useDataset();
  const { predictions, loadCached } = usePredictions();

  // Drawer state
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Executive summary (shared context, persisted via sessionStorage)
  const { summaryData, setSummaryData, showModal: showSummaryModal, setShowModal: setShowSummaryModal, getPlainText } = useExecutiveSummary();
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [emailCopied, setEmailCopied] = useState(false);

  const fetchDashboard = useCallback((rate: number) => {
    api.dashboard(rate).then(setData).catch(console.error);
  }, []);

  // Restore predictions from backend/sessionStorage on mount (same as PredictPage)
  useEffect(() => {
    loadCached();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Only fetch dashboard data if predictions have been explicitly set this session.
  // Prevents Overview from auto-populating from the DB on fresh login in CRM mode.
  useEffect(() => {
    if (!predictions) return;
    fetchDashboard(saveRate);
  }, [fetchDashboard, saveRate, predictions]);

  // Fetch model performance once per session (404 = no model yet, silently ignored)
  useEffect(() => {
    api.modelPerformance().then(setPerformance).catch(() => {/* no model yet */});
  }, []);

  // Fetch production accuracy (real outcome-matched metrics); 404/empty = no pairs yet
  useEffect(() => {
    api.productionAccuracy().then(setProductionAccuracy).catch(() => {});
  }, []);

  // Fetch model insights (plain-language feature importance); 404 = no model yet
  useEffect(() => {
    api.modelInsights().then(setModelInsights).catch(() => {});
  }, []);

  // Fetch ARR forecast only when predictions are loaded (prevents pre-population)
  useEffect(() => {
    if (!predictions) return;
    setForecastLoading(true);
    api.arrForecast(90, expansionRate)
      .then(setArrForecast)
      .catch(() => {})
      .finally(() => setForecastLoading(false));
  }, [expansionRate, predictions]);

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
        name: p.name || p.account_id,
        churn_risk_pct: p.churn_risk_pct,
        arr: p.arr,
        arr_at_risk: p.arr_at_risk,
        days_until_renewal: p.days_until_renewal,
        tier: p.tier,
      }));

      const riskDriverNames = (dashData.top_risk_drivers ?? []).map(
        (d) => featureLabel(d.feature)
      );

      const tc = dashData.tier_counts ?? {};
      const driverSummary: string[] = [...riskDriverNames.slice(0, 3)];
      if (tc['High Risk']) {
        const n = tc['High Risk'];
        driverSummary.push(`${n} account${n === 1 ? '' : 's'} classified as High Risk`);
      }
      if (tc['Medium Risk']) {
        const n = tc['Medium Risk'];
        driverSummary.push(`${n} account${n === 1 ? '' : 's'} at Medium Risk`);
      }
      const urgentCount = dashData.kpis?.high_risk_in_window ?? 0;
      if (urgentCount > 0) {
        driverSummary.push(`${urgentCount} high-risk account${urgentCount === 1 ? '' : 's'} renewing within 30 days`);
      }

      const priorityAccounts = (dashData.top_priority_accounts ?? []).slice(0, 3).map((p) => ({
        account_id: p.account_id,
        name: p.name || p.account_id,
        churn_risk_pct: p.churn_risk_pct,
        arr_at_risk: p.arr_at_risk,
        days_until_renewal: p.days_until_renewal,
      }));

      const res = await api.sendExecutiveSummary({
        recipients,
        total_arr_at_risk: dashData.kpis.total_arr_at_risk,
        projected_recoverable_arr: dashData.kpis.projected_recoverable_arr,
        save_rate: dashData.kpis.assumed_save_rate,
        high_risk_in_window: dashData.kpis.high_risk_in_window,
        renewing_90d: dashData.kpis.renewing_90d,
        top_accounts: topAccounts,
        top_priority_accounts: priorityAccounts,
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

  // Empty state: no predictions generated yet this session
  if (!predictions) {
    return (
      <div className="min-h-[80vh] flex flex-col items-center justify-center px-4 relative overflow-hidden">
        {/* Background glow */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] bg-[var(--color-accent)]/6 rounded-full blur-3xl" />
        </div>

        <div className="relative max-w-2xl w-full text-center">
          {/* Wordmark / badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/20 mb-8">
            <div className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)]" />
            <span className="text-xs font-semibold text-[var(--color-accent)] tracking-wide uppercase">PickPulse Intelligence</span>
          </div>

          <h1 className="text-3xl sm:text-4xl font-bold text-[var(--color-text-primary)] mb-4 leading-tight">
            Identify at-risk accounts.<br />
            <span className="text-[var(--color-accent)]">Protect your revenue.</span>
          </h1>
          <p className="text-base text-[var(--color-text-secondary)] mb-10 leading-relaxed max-w-lg mx-auto">
            Surface churn signals, prioritize renewals, and quantify ARR at risk — from your CRM or your own data.
          </p>

          {/* Workflow indicator */}
          <div className="flex items-center justify-center gap-2 mb-10 text-xs text-[var(--color-text-muted)]">
            <span className="px-2.5 py-1 rounded-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] font-medium">Connect Data</span>
            <ChevronRight size={12} className="opacity-40" />
            <span className="px-2.5 py-1 rounded-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] font-medium">Score Accounts</span>
            <ChevronRight size={12} className="opacity-40" />
            <span className="px-2.5 py-1 rounded-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] font-medium">Protect Revenue</span>
          </div>

          {/* Action cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Primary: Connect HubSpot */}
            <button
              onClick={() => navigate('/data-sources?tab=integrations')}
              className="group flex flex-col items-start gap-4 p-6 rounded-2xl text-left transition-all duration-200 border border-[#FF7A59]/30 bg-gradient-to-br from-[#FF7A59]/10 to-[#FF7A59]/5 hover:from-[#FF7A59]/18 hover:to-[#FF7A59]/10 hover:border-[#FF7A59]/50 hover:shadow-lg hover:shadow-[#FF7A59]/10"
            >
              {/* HubSpot sprocket-style icon */}
              <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: '#FF7A59' }}>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <circle cx="10" cy="10" r="3.5" fill="white" />
                  <circle cx="10" cy="3" r="1.5" fill="white" />
                  <circle cx="10" cy="17" r="1.5" fill="white" />
                  <circle cx="3" cy="10" r="1.5" fill="white" />
                  <circle cx="17" cy="10" r="1.5" fill="white" />
                  <circle cx="5.05" cy="5.05" r="1.5" fill="white" />
                  <circle cx="14.95" cy="14.95" r="1.5" fill="white" />
                  <circle cx="14.95" cy="5.05" r="1.5" fill="white" />
                  <circle cx="5.05" cy="14.95" r="1.5" fill="white" />
                </svg>
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="font-semibold text-sm text-[var(--color-text-primary)]">Connect HubSpot</span>
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded" style={{ background: '#FF7A59', color: 'white' }}>CRM</span>
                </div>
                <div className="text-xs text-[var(--color-text-muted)] leading-relaxed">
                  Sync your accounts and generate live churn risk scores directly from your CRM data.
                </div>
              </div>
              <div className="flex items-center gap-1 text-xs font-medium" style={{ color: '#FF7A59' }}>
                <span>Connect now</span>
                <ChevronRight size={12} className="group-hover:translate-x-0.5 transition-transform" />
              </div>
            </button>

            {/* Secondary: Upload Your Data */}
            <button
              onClick={() => navigate('/data-sources')}
              className="group flex flex-col items-start gap-4 p-6 rounded-2xl text-left transition-all duration-200 border border-[var(--color-border)] bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-primary)] hover:border-[var(--color-accent)]/30 hover:shadow-lg hover:shadow-[var(--color-accent)]/5"
            >
              <div className="w-10 h-10 rounded-xl bg-[var(--color-accent)]/10 flex items-center justify-center flex-shrink-0">
                <FileText size={18} className="text-[var(--color-accent)]" />
              </div>
              <div className="flex-1">
                <div className="font-semibold text-sm text-[var(--color-text-primary)] mb-1.5">Upload Your Data</div>
                <div className="text-xs text-[var(--color-text-muted)] leading-relaxed">
                  Bring your own CSV or explore a sample dataset to see predictions in minutes.
                </div>
              </div>
              <div className="flex items-center gap-1 text-xs font-medium text-[var(--color-accent)]">
                <span>Get started</span>
                <ChevronRight size={12} className="group-hover:translate-x-0.5 transition-transform" />
              </div>
            </button>
          </div>
        </div>
      </div>
    );
  }

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
                  title="Estimated from current model outputs on sample data. Connect your CRM or upload customer data for production-grade insights."
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
              icon={<DollarSign size={16} />}
              accent="var(--color-danger)"
              tooltip="Each account's ARR multiplied by its churn probability, summed across the portfolio."
              onClick={() => navigate('/predict')}
            />
            <StatCard
              label="Accounts Requiring Action"
              value={kpis?.high_risk_in_window ?? '—'}
              sub="High risk · renewing within 30 days"
              icon={<AlertTriangle size={16} />}
              accent="var(--color-danger)"
              tooltip="Accounts with ≥25% churn probability that also renew within 30 days. These need immediate outreach."
              onClick={() => navigate('/predict')}
            />
            <StatCard
              label="Potential ARR Protected"
              value={kpis ? formatCurrency(kpis.projected_recoverable_arr) : '—'}
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
                      <th className="py-2 pr-3">Tier</th>
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
                        <td className="py-2.5 pr-3 font-medium text-xs">{row.name || row.account_id}</td>
                        <td className="py-2.5 pr-3 text-right">
                          <span
                            className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold"
                            style={{ background: `${riskColor(row.churn_risk_pct)}18`, color: riskColor(row.churn_risk_pct) }}
                          >
                            {row.churn_risk_pct}%
                          </span>
                        </td>
                        <td className="py-2.5 pr-3">
                          {row.tier && (
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold ${
                              row.tier === 'High Risk' ? 'bg-red-50 text-red-600' :
                              row.tier === 'Medium Risk' ? 'bg-amber-50 text-amber-600' :
                              'bg-emerald-50 text-emerald-600'
                            }`}>
                              {row.tier}
                            </span>
                          )}
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
                </div>
              </div>
            </div>
          )}

          {/* Section 5: Portfolio Risk Drivers */}
          {riskDrivers.length > 0 && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
              <h3 className="text-sm font-semibold mb-4">Portfolio Risk Drivers</h3>
              <p className="text-xs text-[var(--color-text-secondary)] mb-4">
                Signals with the strongest predictive influence on churn across your portfolio
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
          {/* Section 5b: ARR Trajectory Engine */}
          {(arrForecast || forecastLoading) && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
              <div className="flex items-start justify-between mb-5">
                <div>
                  <h3 className="text-sm font-semibold">ARR Forecast · Next 90 Days</h3>
                  <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                    Expected revenue based on renewal timing and current risk scores
                  </p>
                </div>
                {arrForecast && (
                  <div className="flex items-center gap-4">
                    {/* Expansion rate control */}
                    <label className="flex items-center gap-1.5 text-[10px] text-[var(--color-text-muted)]">
                      Expansion
                      <select
                        value={expansionRate}
                        onChange={(e) => setExpansionRate(parseFloat(e.target.value))}
                        className="border border-[var(--color-border)] rounded px-1.5 py-0.5 text-[10px] bg-white"
                      >
                        <option value={0.0}>0% (none)</option>
                        <option value={0.05}>5%</option>
                        <option value={0.10}>10%</option>
                        <option value={0.15}>15%</option>
                        <option value={0.20}>20%</option>
                      </select>
                    </label>
                  </div>
                )}
              </div>

              {forecastLoading && !arrForecast && (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-5 h-5 animate-spin text-[var(--color-text-muted)]" />
                </div>
              )}

              {arrForecast && arrForecast.coverage.accounts_in_forecast === 0 && (
                <div className="py-8 text-center text-sm text-[var(--color-text-muted)]">
                  No accounts with renewal dates found in the next {arrForecast.horizon_days} days.
                  <br />
                  <span className="text-xs">
                    Add renewal dates via HubSpot sync or CSV to enable the ARR forecast.
                    {arrForecast.coverage.accounts_scored_no_renewal_date > 0 && (
                      ` (${arrForecast.coverage.accounts_scored_no_renewal_date} scored accounts have no renewal date signal.)`
                    )}
                  </span>
                </div>
              )}

              {arrForecast && arrForecast.coverage.accounts_in_forecast > 0 && (
                <>
                  {/* Low-coverage amber warning — shown prominently when < 50% of ARR is forecastable */}
                  {arrForecast.arr_coverage_pct < 50 && (
                    <div className="mb-4 px-3 py-2 rounded-lg text-xs text-[var(--color-warning)] border border-[var(--color-warning)] bg-[var(--color-warning)]/5">
                      Low coverage: this forecast reflects only {arrForecast.arr_coverage_pct.toFixed(0)}% of your ARR.
                      {' '}{formatCurrency(arrForecast.coverage.arr_excluded)} ARR has no renewal date and is excluded.
                      Treat this as directional only.
                    </div>
                  )}

                  {/* Headline numbers */}
                  <div className="flex items-end gap-8 mb-5">
                    <div>
                      <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wide mb-1">
                        Expected ARR · {arrForecast.horizon_date}
                      </div>
                      <div className="text-3xl font-bold tracking-tight">
                        {formatCurrency(arrForecast.forecast.base)}
                      </div>
                      {/* Fix: "Estimated" qualifier prevents reading delta as confirmed loss */}
                      <div className="text-xs text-[var(--color-text-muted)] mt-1">
                        Estimated {arrForecast.forecast.base >= arrForecast.current_arr ? '+' : ''}
                        {formatCurrency(arrForecast.forecast.base - arrForecast.current_arr)}
                        {' '}from renewing cohort · current {formatCurrency(arrForecast.current_arr)}
                      </div>
                    </div>
                    <div className="flex-1 mb-1">
                      {/* Model uncertainty range: line + dot */}
                      {arrForecast.forecast.std_dev > 0 && (() => {
                        const lo = arrForecast.forecast.lower_1sd;
                        const hi = arrForecast.forecast.upper_1sd;
                        const base = arrForecast.forecast.base;
                        const range = hi - lo || 1;
                        const basePct = ((base - lo) / range) * 100;
                        return (
                          <div>
                            <div className="text-[10px] text-[var(--color-text-muted)] mb-2 uppercase tracking-wide">
                              Model uncertainty range
                            </div>
                            {/* Track: horizontal line with end ticks and a dot at base */}
                            <div className="relative h-4 flex items-center mx-1">
                              <div className="absolute inset-x-0 h-px bg-[var(--color-border)]" />
                              <div className="absolute left-0 w-px h-2.5 bg-[var(--color-text-muted)]" style={{ transform: 'translateX(-50%)' }} />
                              <div className="absolute right-0 w-px h-2.5 bg-[var(--color-text-muted)]" style={{ transform: 'translateX(50%)' }} />
                              <div
                                className="absolute w-2.5 h-2.5 rounded-full bg-[var(--color-accent)] border-2 border-white shadow-sm"
                                style={{ left: `${basePct}%`, transform: 'translateX(-50%)' }}
                                title={`Base: ${formatCurrency(base)}`}
                              />
                            </div>
                            <div className="flex justify-between text-[10px] text-[var(--color-text-muted)] mt-1.5">
                              <span>{formatCurrency(lo)}</span>
                              <span>{formatCurrency(hi)}</span>
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  </div>

                  {/* Renewal calendar */}
                  {arrForecast.renewal_calendar.length > 0 && (
                    <div className="mb-4">
                      <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wide mb-2">
                        Renewal calendar
                      </div>
                      <div className="flex items-end gap-2 h-20">
                        {arrForecast.renewal_calendar.map((month: ArrCalendarMonth, i: number) => {
                          const maxArr = Math.max(
                            ...arrForecast.renewal_calendar.map((m) => m.arr_renewing),
                            1
                          );
                          const totalH = (month.arr_renewing / maxArr) * 100;
                          const lostH = (month.expected_arr_lost / maxArr) * 100;
                          const retainedH = totalH - lostH;
                          return (
                            <div key={i} className="flex-1 flex flex-col items-stretch gap-0">
                              <div className="flex flex-col justify-end h-16">
                                <div
                                  className="rounded-t-sm transition-all"
                                  style={{ height: `${lostH}%`, background: 'var(--color-danger)', opacity: 0.75 }}
                                  title={`Expected lost: ${formatCurrency(month.expected_arr_lost)}`}
                                />
                                <div
                                  className="rounded-b-sm transition-all"
                                  style={{ height: `${retainedH}%`, background: 'var(--color-success)', opacity: 0.6 }}
                                  title={`Expected retained: ${formatCurrency(month.expected_arr_retained)}`}
                                />
                              </div>
                              <div className="text-[9px] text-[var(--color-text-muted)] text-center mt-1">
                                {month.has_month_estimates ? '~' : ''}{month.month.slice(5)}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      <div className="flex items-center gap-4 text-[10px] mt-2">
                        <div className="flex items-center gap-1.5">
                          <div className="w-2.5 h-2.5 rounded-sm" style={{ background: 'var(--color-success)', opacity: 0.6 }} />
                          <span className="text-[var(--color-text-muted)]">Expected retained</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <div className="w-2.5 h-2.5 rounded-sm" style={{ background: 'var(--color-danger)', opacity: 0.75 }} />
                          <span className="text-[var(--color-text-muted)]">Expected at risk</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Top at-risk accounts */}
                  {arrForecast.top_at_risk.length > 0 && (
                    <div className="mb-4">
                      <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wide mb-2">
                        Highest expected ARR impact
                      </div>
                      <div className="divide-y divide-[var(--color-border)]">
                        {arrForecast.top_at_risk.slice(0, 5).map((acct, i) => (
                          <div key={i} className="flex items-center justify-between py-1.5 text-xs">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="truncate font-medium">{acct.name || acct.account_id}</span>
                              {acct.renewal_date_precision === 'month_estimate' && (
                                <span className="text-[10px] text-[var(--color-text-muted)] shrink-0">~month</span>
                              )}
                            </div>
                            <div className="flex items-center gap-4 shrink-0 text-right">
                              <span className="text-[var(--color-text-muted)]">{Math.round(acct.churn_probability * 100)}% risk</span>
                              <span className="font-medium text-[var(--color-danger)]">{formatCurrency(acct.expected_arr_at_risk)}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Coverage footer — only shows excluded ARR warning if < 50% (already shown as amber banner above) */}
                  <div className="pt-3 border-t border-[var(--color-border)] space-y-1 text-[10px] text-[var(--color-text-muted)]">
                    <div>
                      Forecast covers {formatCurrency(arrForecast.coverage.arr_in_forecast)} of {formatCurrency(arrForecast.current_arr)} total ARR
                      {' '}({arrForecast.arr_coverage_pct.toFixed(0)}% · {arrForecast.coverage.accounts_in_forecast} of {arrForecast.coverage.total_active_accounts} accounts)
                    </div>
                    {arrForecast.arr_coverage_pct >= 50 && arrForecast.coverage.arr_excluded > 0 && (
                      <div>
                        {formatCurrency(arrForecast.coverage.arr_excluded)} ARR excluded — renewal date unknown
                      </div>
                    )}
                    {arrForecast.expansion_arr > 0 && (
                      <div>
                        Includes {formatCurrency(arrForecast.expansion_arr)} estimated expansion ({(arrForecast.expansion_rate * 100).toFixed(0)}% on low-risk accounts)
                      </div>
                    )}
                    <div className="italic">
                      Statistical forecast range assumes independent account churn. Correlated events are not modeled.
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Model Health toggle — collapses model insights + accuracy panels */}
          {(performance || productionAccuracy !== null || modelInsights !== null) && (
            <button
              onClick={() => setShowModelHealth(v => !v)}
              className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors py-1 self-start"
            >
              <ChevronRight className={`w-3.5 h-3.5 transition-transform duration-150 ${showModelHealth ? 'rotate-90' : ''}`} />
              Model Health
            </button>
          )}

          {showModelHealth && (
            <>
          {/* Stale model notice — shown when shap_directions absent (pre-Phase 3 artifact) */}
          {modelInsights && modelInsights.has_shap_directions === false && (
            <div className="flex items-center gap-2 px-4 py-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800">
              <AlertTriangle size={13} className="shrink-0 text-amber-500" />
              <span>
                <strong>Retrain recommended:</strong> this model predates dynamic signal analysis. Retrain to enable per-account SHAP explanations and confidence scoring.
              </span>
            </div>
          )}

          {/* Model Insights — plain-language explainability */}
          {modelInsights && (modelInsights.churn_drivers.length > 0 || modelInsights.health_signals.length > 0) && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
              <div className="mb-4">
                <h3 className="text-sm font-semibold">What the Model Learned</h3>
                <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                  Derived from feature importance — translated for business readability
                </p>
              </div>

              {/* Top insight sentence */}
              {modelInsights.top_insight && (
                <p className="text-sm text-[var(--color-text)] mb-4 italic border-l-2 pl-3"
                   style={{ borderColor: 'var(--color-accent)' }}>
                  {modelInsights.top_insight}
                </p>
              )}

              <div className="grid grid-cols-2 gap-6">
                {/* Churn drivers */}
                {modelInsights.churn_drivers.length > 0 && (
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-danger)] mb-3">
                      Top Churn Risk Drivers
                    </div>
                    <div className="space-y-3">
                      {modelInsights.churn_drivers.map((driver) => (
                        <div key={driver.rank} className="flex gap-2.5">
                          <div className="w-5 h-5 rounded-full bg-red-50 border border-red-200 flex items-center justify-center shrink-0 mt-0.5">
                            <span className="text-[9px] font-bold text-red-500">{driver.rank}</span>
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-semibold text-[var(--color-text)]">{driver.label}</span>
                              <span className="text-[9px] text-[var(--color-text-muted)] border border-[var(--color-border)] rounded px-1 py-px shrink-0">{driver.group}</span>
                            </div>
                            <p className="text-[11px] text-[var(--color-text-muted)] mt-0.5 leading-relaxed">{driver.description}</p>
                            {/* Importance bar */}
                            <div className="mt-1.5 h-1 rounded-full bg-red-100 overflow-hidden">
                              <div
                                className="h-full rounded-full bg-red-400"
                                style={{ width: `${driver.importance_normalized * 100}%` }}
                              />
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Health signals */}
                {modelInsights.health_signals.length > 0 && (
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-success)] mb-3">
                      Retention & Health Signals
                    </div>
                    <div className="space-y-3">
                      {modelInsights.health_signals.map((signal) => (
                        <div key={signal.rank} className="flex gap-2.5">
                          <div className="w-5 h-5 rounded-full bg-green-50 border border-green-200 flex items-center justify-center shrink-0 mt-0.5">
                            <span className="text-[9px] font-bold text-green-600">{signal.rank}</span>
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-semibold text-[var(--color-text)]">{signal.label}</span>
                              <span className="text-[9px] text-[var(--color-text-muted)] border border-[var(--color-border)] rounded px-1 py-px shrink-0">{signal.group}</span>
                            </div>
                            <p className="text-[11px] text-[var(--color-text-muted)] mt-0.5 leading-relaxed">{signal.description}</p>
                            <div className="mt-1.5 h-1 rounded-full bg-green-100 overflow-hidden">
                              <div
                                className="h-full rounded-full bg-green-400"
                                style={{ width: `${signal.importance_normalized * 100}%` }}
                              />
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Lift statement */}
              {modelInsights.lift_statement && (
                <p className="mt-4 pt-3 border-t border-[var(--color-border)] text-[11px] text-[var(--color-text-muted)]">
                  {modelInsights.lift_statement}
                </p>
              )}
            </div>
          )}

          {/* Section 6: Model Accuracy Trust Panel (training-time) */}
          {performance && performance.calibration_bins.length > 0 && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
              <div className="flex items-start justify-between mb-5">
                <div>
                  <h3 className="text-sm font-semibold">Model Accuracy</h3>
                  <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                    Calibration curve — when the model predicts X% risk, does that match reality?
                  </p>
                </div>
                <div className="flex items-center gap-5">
                  {performance.auc != null && (
                    <div className="text-center">
                      <div className="text-xl font-bold" style={{ color: 'var(--color-accent)' }}>{performance.auc.toFixed(2)}</div>
                      <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wide">AUC</div>
                    </div>
                  )}
                  {performance.lift_at_top10 != null && (
                    <div className="text-center">
                      <div className="text-xl font-bold text-[var(--color-success)]">{performance.lift_at_top10.toFixed(1)}x</div>
                      <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wide">Lift@Top10%</div>
                    </div>
                  )}
                  {performance.calibration_error != null && (
                    <div className="text-center">
                      <div
                        className="text-xl font-bold"
                        style={{ color: performance.calibration_error < 0.05 ? 'var(--color-success)' : 'var(--color-warning)' }}
                      >
                        {(performance.calibration_error * 100).toFixed(1)}%
                      </div>
                      <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wide">Cal. Error</div>
                    </div>
                  )}
                </div>
              </div>

              {/* Calibration bars: predicted (teal) vs actual (red) per bin */}
              <div className="flex items-end gap-1 h-28">
                {performance.calibration_bins.map((bin, i) => {
                  const maxVal = Math.max(
                    ...performance.calibration_bins.map((b) => Math.max(b.predicted_avg, b.actual_rate)),
                    0.01
                  );
                  return (
                    <div
                      key={i}
                      className="flex-1 flex items-end gap-px"
                      title={`Bin ${Math.round(bin.bin_lo * 100)}–${Math.round(bin.bin_hi * 100)}%  |  Predicted: ${Math.round(bin.predicted_avg * 100)}%  |  Actual: ${Math.round(bin.actual_rate * 100)}%  |  n=${bin.n}`}
                    >
                      <div
                        className="flex-1 rounded-t-sm opacity-60 transition-all"
                        style={{ height: `${(bin.predicted_avg / maxVal) * 100}%`, background: 'var(--color-accent)' }}
                      />
                      <div
                        className="flex-1 rounded-t-sm transition-all"
                        style={{ height: `${(bin.actual_rate / maxVal) * 100}%`, background: 'var(--color-danger)' }}
                      />
                    </div>
                  );
                })}
              </div>
              <div className="flex justify-between text-[10px] text-[var(--color-text-muted)] mt-1 mb-3">
                <span>Low predicted risk</span>
                <span>High predicted risk</span>
              </div>
              <div className="flex items-center gap-5 text-[10px]">
                <div className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-sm opacity-60" style={{ background: 'var(--color-accent)' }} />
                  <span className="text-[var(--color-text-muted)]">Predicted probability</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-sm" style={{ background: 'var(--color-danger)' }} />
                  <span className="text-[var(--color-text-muted)]">Actual churn rate</span>
                </div>
                {performance.n != null && (
                  <span className="text-[var(--color-text-muted)] ml-auto">
                    {performance.n.toLocaleString()} validation accounts
                  </span>
                )}
              </div>
            </div>
          )}
          {/* Section 7: Production Prediction Accuracy */}
          {productionAccuracy !== null && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)] card-hover">
              <div className="flex items-start justify-between mb-5">
                <div>
                  <h3 className="text-sm font-semibold">Production Prediction Accuracy</h3>
                  <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                    Calibration verified against real churn &amp; renewal outcomes
                  </p>
                </div>
                <div className="flex items-center gap-5">
                  {productionAccuracy.lift_top_10 != null && (
                    <div className="text-center">
                      <div className="text-xl font-bold text-[var(--color-success)]">
                        {productionAccuracy.lift_top_10.toFixed(1)}x
                      </div>
                      <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wide">Lift@Top10%</div>
                    </div>
                  )}
                  {productionAccuracy.precision != null && (
                    <div className="text-center">
                      <div className="text-xl font-bold" style={{ color: 'var(--color-accent)' }}>
                        {Math.round(productionAccuracy.precision * 100)}%
                      </div>
                      <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wide">Precision</div>
                    </div>
                  )}
                  {productionAccuracy.recall != null && (
                    <div className="text-center">
                      <div className="text-xl font-bold" style={{ color: 'var(--color-accent)' }}>
                        {Math.round(productionAccuracy.recall * 100)}%
                      </div>
                      <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wide">Recall</div>
                    </div>
                  )}
                  <button
                    onClick={async () => {
                      setProdAccRefreshing(true);
                      try {
                        const result = await api.refreshProductionAccuracy();
                        setProductionAccuracy(result);
                      } catch { /* non-fatal */ }
                      setProdAccRefreshing(false);
                    }}
                    disabled={prodAccRefreshing}
                    className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] border border-[var(--color-border)] rounded-lg px-2.5 py-1 transition-colors disabled:opacity-50"
                  >
                    {prodAccRefreshing ? 'Refreshing…' : 'Refresh'}
                  </button>
                </div>
              </div>

              {productionAccuracy.n_pairs === 0 ? (
                <div className="text-center py-8 text-sm text-[var(--color-text-muted)]">
                  No matched prediction-outcome pairs yet.
                  <br />
                  <span className="text-xs">Mark accounts as churned or renewed on the Accounts page to begin building production accuracy data.</span>
                </div>
              ) : (
                <>
                  {/* Calibration chart */}
                  {productionAccuracy.calibration.length > 0 && (
                    <>
                      <div className="flex items-end gap-1 h-28">
                        {productionAccuracy.calibration.map((bin, i) => {
                          const maxVal = Math.max(
                            ...productionAccuracy.calibration.map((b) => Math.max(b.predicted_avg, b.actual_rate)),
                            0.01
                          );
                          return (
                            <div
                              key={i}
                              className="flex-1 flex items-end gap-px"
                              title={`${Math.round(bin.bin_lo * 100)}–${Math.round(bin.bin_hi * 100)}%  |  Predicted: ${Math.round(bin.predicted_avg * 100)}%  |  Actual: ${Math.round(bin.actual_rate * 100)}%  |  n=${bin.n}`}
                            >
                              <div
                                className="flex-1 rounded-t-sm opacity-60 transition-all"
                                style={{ height: `${(bin.predicted_avg / maxVal) * 100}%`, background: 'var(--color-accent)' }}
                              />
                              <div
                                className="flex-1 rounded-t-sm transition-all"
                                style={{ height: `${(bin.actual_rate / maxVal) * 100}%`, background: 'var(--color-danger)' }}
                              />
                            </div>
                          );
                        })}
                      </div>
                      <div className="flex justify-between text-[10px] text-[var(--color-text-muted)] mt-1 mb-3">
                        <span>Low predicted risk</span>
                        <span>High predicted risk</span>
                      </div>
                    </>
                  )}

                  {/* Legend + coverage stats */}
                  <div className="flex items-center gap-5 text-[10px]">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2.5 h-2.5 rounded-sm opacity-60" style={{ background: 'var(--color-accent)' }} />
                      <span className="text-[var(--color-text-muted)]">Predicted probability</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-2.5 h-2.5 rounded-sm" style={{ background: 'var(--color-danger)' }} />
                      <span className="text-[var(--color-text-muted)]">Actual churn rate</span>
                    </div>
                    <span className="text-[var(--color-text-muted)] ml-auto">
                      {productionAccuracy.n_pairs}/{productionAccuracy.n_eligible_outcomes} outcomes matched
                      {productionAccuracy.n_unmatched > 0 && (
                        <span title="Outcomes excluded because no prediction was found in the prior 90 days">
                          {' · '}{productionAccuracy.n_unmatched} unmatched
                        </span>
                      )}
                      {' · '}
                      {productionAccuracy.n_churned} churned · {productionAccuracy.n_renewed} renewed
                    </span>
                  </div>

                  {/* Time lag insight */}
                  {productionAccuracy.time_lag_stats && (
                    <div className="mt-3 pt-3 border-t border-[var(--color-border)] text-[10px] text-[var(--color-text-muted)]">
                      Prediction horizon: median {productionAccuracy.time_lag_stats.median} days before outcome
                      {' '}(p25: {productionAccuracy.time_lag_stats.p25}d · p75: {productionAccuracy.time_lag_stats.p75}d)
                    </div>
                  )}
                </>
              )}
            </div>
          )}
            </>
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
                <button
                  onClick={() => {
                    // Open mailto with plain-text body so the email compose window
                    // has content immediately. Also copy the rich HTML to clipboard
                    // so the user can paste it for a formatted version.
                    navigator.clipboard.writeText(summaryData.html_body).catch(() => {});
                    const subject = encodeURIComponent(summaryData.subject);
                    const to = summaryData.recipients.join(',');
                    const body = encodeURIComponent(summaryData.text_body);
                    window.location.href = `mailto:${to}?subject=${subject}&body=${body}`;
                    setEmailCopied(true);
                    setTimeout(() => setEmailCopied(false), 4000);
                  }}
                  className="btn-primary flex items-center gap-2 px-5 py-2.5 text-white rounded-xl text-sm font-medium"
                >
                  <Mail size={14} />
                  {emailCopied ? 'HTML copied to clipboard' : 'Send Executive Brief'}
                </button>
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
                  onClick={() => {
                    const blob = new Blob([summaryData.html_body], { type: 'text/html' });
                    const url = URL.createObjectURL(blob);
                    window.open(url, '_blank', 'noopener');
                  }}
                  className="flex items-center gap-1.5 px-4 py-2.5 bg-white border border-[var(--color-border)] rounded-xl text-sm hover:bg-[var(--color-bg-primary)] transition-colors"
                >
                  <ExternalLink size={14} />
                  Open in Browser
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
