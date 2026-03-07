import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { DollarSign, Clock, AlertTriangle, Shield, TrendingUp, Mail, Loader2 } from 'lucide-react';
import { api, type DashboardResponse, type ChurnPrediction, type DraftEmailRequest } from '../lib/api';
import { StatCard } from '../components/StatCard';
import { useDataset } from '../lib/DatasetContext';
import { formatCurrency } from '../lib/format';

type Tone = 'friendly' | 'direct' | 'executive';

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

  // AI Outreach state
  const [draftingId, setDraftingId] = useState<string | null>(null);
  const [emailPromptId, setEmailPromptId] = useState<string | null>(null);
  const [emailInput, setEmailInput] = useState('');
  const [selectedTone, setSelectedTone] = useState<Tone>('friendly');
  const [draftError, setDraftError] = useState<string | null>(null);
  const overlayRef = useRef<HTMLDivElement>(null);

  const fetchDashboard = useCallback((rate: number) => {
    api.dashboard(rate).then(setData).catch(console.error);
  }, []);

  useEffect(() => {
    fetchDashboard(saveRate);
  }, [fetchDashboard, saveRate]);

  // Close overlay on outside click
  useEffect(() => {
    if (!emailPromptId) return;
    const handleClick = (e: MouseEvent) => {
      if (overlayRef.current && !overlayRef.current.contains(e.target as Node)) {
        setEmailPromptId(null);
        setEmailInput('');
        setDraftError(null);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [emailPromptId]);

  const handleDraftEmail = async (row: ChurnPrediction, contactEmail: string | null) => {
    setEmailPromptId(null);
    setDraftingId(row.customer_id);
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
        risk_driver_summary: null,
        tier: row.tier,
        tone: selectedTone,
      };

      const result = await api.draftOutreachEmail(req);

      console.log('[outreach] outreach_email_generated', {
        account_id: row.customer_id,
        tier: row.tier,
        arr: row.arr,
        tone: selectedTone,
        has_recipient: !!contactEmail,
      });

      window.location.href = result.mailto_url;
    } catch (err: any) {
      console.error('[outreach] draft failed:', err);
      setDraftError(err?.message || 'Failed to generate email');
    } finally {
      setDraftingId(null);
      setEmailInput('');
    }
  };

  // Reusable outreach overlay component
  const renderOutreachOverlay = (row: ChurnPrediction) => (
    <>
      {draftingId === row.customer_id ? (
        <span className="inline-flex items-center gap-1.5 px-2 py-1 text-[10px] text-[var(--color-accent)]">
          <Loader2 size={12} className="animate-spin" />
          Generating...
        </span>
      ) : (
        <button
          onClick={(e) => {
            e.stopPropagation();
            setEmailPromptId(emailPromptId === row.customer_id ? null : row.customer_id);
            setEmailInput('');
            setDraftError(null);
          }}
          disabled={draftingId !== null}
          className="inline-flex items-center gap-1 px-2.5 py-1 text-[10px] font-semibold rounded-lg bg-[var(--color-accent)]/10 text-[var(--color-accent)] hover:bg-[var(--color-accent)]/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Mail size={10} />
          Generate Outreach
        </button>
      )}

      {emailPromptId === row.customer_id && draftingId === null && (
        <div
          ref={overlayRef}
          className="absolute right-0 top-full mt-1 z-50 w-72 bg-white border border-[var(--color-border)] rounded-xl p-3 shadow-[0_4px_20px_rgba(0,0,0,0.12)]"
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
              className="w-full px-2.5 py-1.5 text-xs bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)]"
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleDraftEmail(row, emailInput.trim() || null);
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
                      : 'bg-[var(--color-bg-primary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border)]'
                  }`}
                >
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleDraftEmail(row, emailInput.trim() || null)}
              className="flex-1 px-3 py-1.5 text-[10px] font-semibold rounded-lg bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-glow)] transition-colors"
            >
              Generate
            </button>
            <button
              onClick={() => handleDraftEmail(row, null)}
              className="px-3 py-1.5 text-[10px] font-medium rounded-lg bg-[var(--color-bg-primary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] transition-colors"
            >
              Skip Email
            </button>
          </div>
        </div>
      )}
    </>
  );

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

  return (
    <div>
      <div className="mb-8">
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

          {/* Section 2: Risk Distribution Strip */}
          {totalTierArr > 0 && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
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
          <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
            <h3 className="text-sm font-semibold mb-4">Top 10 Accounts To Save Now</h3>

            {draftError && (
              <div className="mb-3 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-xs text-[var(--color-danger)]">
                {draftError}
              </div>
            )}

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
                      <th className="py-2 text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topRisk.map((row, i) => (
                      <tr key={row.customer_id} className={`border-b border-[var(--color-border)]/50 ${i % 2 === 1 ? 'bg-[var(--color-bg-primary)]' : ''}`}>
                        <td className="py-2.5 pr-3 font-medium text-xs">{row.customer_id}</td>
                        <td className="py-2.5 pr-3 text-right">
                          <span className={`font-bold ${row.churn_risk_pct >= 70 ? 'text-[var(--color-danger)]' : row.churn_risk_pct >= 40 ? 'text-[var(--color-warning)]' : 'text-[var(--color-success)]'}`}>
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
                        <td className="py-2.5 text-center relative">
                          {renderOutreachOverlay(row)}
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
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
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
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
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
    </div>
  );
}
