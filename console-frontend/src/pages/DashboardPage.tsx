import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { DollarSign, Clock, AlertTriangle, Activity, TrendingUp, Mail, Loader2, Shield } from 'lucide-react';
import { api, type DashboardResponse, type ChurnPrediction, type DraftEmailRequest } from '../lib/api';
import { StatCard } from '../components/StatCard';
import { useDataset } from '../lib/DatasetContext';
import { formatCurrency } from '../lib/format';

type Tone = 'friendly' | 'direct' | 'executive';

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
        <span className="inline-flex items-center gap-1.5 px-2 py-1 text-[10px] text-[var(--color-accent-glow)]">
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
          className="inline-flex items-center gap-1 px-2.5 py-1 text-[10px] font-semibold rounded-lg bg-[var(--color-accent)]/15 text-[var(--color-accent-glow)] hover:bg-[var(--color-accent)]/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Mail size={10} />
          Generate Outreach
        </button>
      )}

      {emailPromptId === row.customer_id && draftingId === null && (
        <div
          ref={overlayRef}
          className="absolute right-0 top-full mt-1 z-50 w-72 bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-xl p-3 shadow-[0_10px_30px_rgba(0,0,0,0.5)]"
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
                      : 'bg-[rgba(255,255,255,0.06)] text-[var(--color-text-secondary)] hover:bg-[rgba(255,255,255,0.1)]'
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
              className="flex-1 px-3 py-1.5 text-[10px] font-semibold rounded-lg bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent)]/80 transition-colors"
            >
              Generate
            </button>
            <button
              onClick={() => handleDraftEmail(row, null)}
              className="px-3 py-1.5 text-[10px] font-medium rounded-lg bg-[rgba(255,255,255,0.06)] text-[var(--color-text-secondary)] hover:bg-[rgba(255,255,255,0.1)] transition-colors"
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

  return (
    <div>
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Executive Overview</h1>
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
          Real-time churn risk exposure, renewal pipeline health, and projected recovery
        </p>
      </div>

      {mod && (
        <>
          {/* ARR Recovery Opportunity Panel */}
          {kpis && kpis.total_arr_at_risk > 0 && buckets && (
            <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
              <div className="flex items-center gap-2 mb-5">
                <Shield size={16} className="text-[var(--color-accent)]" />
                <h3 className="text-sm font-semibold">ARR Recovery Opportunity</h3>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div>
                  <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">Total ARR at Risk</div>
                  <div className="text-xl font-bold text-[var(--color-danger)]">{formatCurrency(kpis.total_arr_at_risk)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">High Confidence Saves</div>
                  <div className="text-xl font-bold text-[var(--color-danger)]">{formatCurrency(buckets.high_confidence_saves)}</div>
                  <div className="text-[10px] text-[var(--color-text-muted)]">Risk &gt; 70%</div>
                </div>
                <div>
                  <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">Medium Confidence Saves</div>
                  <div className="text-xl font-bold text-[var(--color-warning)]">{formatCurrency(buckets.medium_confidence_saves)}</div>
                  <div className="text-[10px] text-[var(--color-text-muted)]">Risk 40–70%</div>
                </div>
                <div>
                  <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">Low Confidence Saves</div>
                  <div className="text-xl font-bold text-[var(--color-success)]">{formatCurrency(buckets.low_confidence_saves)}</div>
                  <div className="text-[10px] text-[var(--color-text-muted)]">Risk &lt; 40%</div>
                </div>
                <div>
                  <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">Projected Recoverable</div>
                  <div className="text-xl font-bold text-[var(--color-success)]">{formatCurrency(kpis.projected_recoverable_arr)}</div>
                  <div className="text-[10px] text-[var(--color-text-muted)]">at {Math.round(kpis.assumed_save_rate * 100)}% save rate</div>
                </div>
              </div>
            </div>
          )}

          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-10">
            <StatCard
              label="ARR at Risk"
              value={kpis ? formatCurrency(kpis.total_arr_at_risk) : '—'}
              sub="Probability-weighted churn exposure"
              icon={<DollarSign size={16} />}
              accent="var(--color-danger)"
              tooltip="Each account's annual recurring revenue multiplied by its churn probability, summed across the portfolio."
              onClick={() => navigate('/predict')}
            />
            <StatCard
              label="Renewing Within 90 Days"
              value={kpis?.renewing_90d ?? '—'}
              sub="Accounts entering renewal window"
              icon={<Clock size={16} />}
              accent="var(--color-warning)"
              tooltip="Accounts with a contract renewal date in the next 90 days — the highest-leverage intervention window."
              onClick={() => navigate('/predict')}
            />
            <StatCard
              label="High Risk in Window"
              value={kpis?.high_risk_in_window ?? '—'}
              sub="Risk ≥ 70% and renewing soon"
              icon={<AlertTriangle size={16} />}
              accent="var(--color-danger)"
              tooltip="Accounts with ≥70% predicted churn probability that also renew within 90 days. Prioritize these for immediate outreach."
              onClick={() => navigate('/predict')}
            />
            <StatCard
              label="Model Health"
              value={mod.auc != null ? `AUC ${mod.auc.toFixed(3)}` : '—'}
              sub={mod.calibration_error != null ? `Calibration error: ${mod.calibration_error.toFixed(4)}` : 'No model trained yet'}
              icon={<Activity size={16} />}
              accent={mod.auc != null ? (mod.auc > 0.75 ? 'var(--color-success)' : 'var(--color-warning)') : undefined}
              tooltip="AUC measures how well the model separates churners from retainers (1.0 = perfect, 0.5 = random). Calibration error measures how closely predicted probabilities match actual outcomes."
              onClick={() => navigate('/evaluate')}
            />
          </div>

          {/* Save Simulation */}
          {kpis && kpis.total_arr_at_risk > 0 && (
            <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-6 mb-10 shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
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

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Top 10 Accounts To Save Now */}
            <div className="lg:col-span-2 bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
              <h3 className="text-sm font-semibold mb-4">Top 10 Accounts To Save Now</h3>

              {draftError && (
                <div className="mb-3 px-3 py-2 bg-[var(--color-danger)]/10 border border-[var(--color-danger)]/25 rounded-lg text-xs text-[var(--color-danger)]">
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
                        <th className="py-2 text-center">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topRisk.map((row, i) => (
                        <tr key={row.customer_id} className={`border-b border-[var(--color-border)]/30 ${i % 2 === 1 ? 'bg-[rgba(255,255,255,0.03)]' : ''}`}>
                          <td className="py-2.5 pr-3 font-mono text-xs">{row.customer_id}</td>
                          <td className="py-2.5 pr-3 text-right">
                            <span className={`font-bold ${row.churn_risk_pct >= 70 ? 'text-[var(--color-danger)]' : row.churn_risk_pct >= 40 ? 'text-[var(--color-warning)]' : 'text-[var(--color-success)]'}`}>
                              {row.churn_risk_pct}%
                            </span>
                          </td>
                          <td className="py-2.5 pr-3 text-right font-mono text-xs">{formatCurrency(row.arr)}</td>
                          <td className="py-2.5 pr-3 text-right font-mono text-xs font-bold text-[var(--color-danger)]">{formatCurrency(row.arr_at_risk)}</td>
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

            {/* Quick Actions + Model Info */}
            <div className="space-y-6">
              <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
                <h3 className="text-sm font-semibold mb-4">Next Steps</h3>
                <div className="space-y-2">
                  {!mod.has_dataset && (
                    <button
                      onClick={() => navigate('/datasets')}
                      className="w-full text-left px-4 py-3 bg-[rgba(255,255,255,0.04)] rounded-xl text-sm hover:bg-[rgba(255,255,255,0.08)] transition-colors"
                    >
                      1. Load or upload your account data
                    </button>
                  )}
                  {mod.has_dataset && !mod.has_model && (
                    <button
                      onClick={() => navigate('/train')}
                      className="w-full text-left px-4 py-3 bg-[var(--color-accent)]/10 rounded-xl text-sm text-[var(--color-accent-glow)] hover:bg-[var(--color-accent)]/20 transition-colors"
                    >
                      2. Train the churn prediction model
                    </button>
                  )}
                  {mod.has_model && (
                    <>
                      <button
                        onClick={() => navigate('/predict')}
                        className="w-full text-left px-4 py-3 bg-[rgba(255,255,255,0.04)] rounded-xl text-sm hover:bg-[rgba(255,255,255,0.08)] transition-colors"
                      >
                        Score accounts and generate predictions
                      </button>
                      <button
                        onClick={() => navigate('/evaluate')}
                        className="w-full text-left px-4 py-3 bg-[rgba(255,255,255,0.04)] rounded-xl text-sm hover:bg-[rgba(255,255,255,0.08)] transition-colors"
                      >
                        Review model performance metrics
                      </button>
                    </>
                  )}
                </div>
              </div>

              <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
                <h3 className="text-sm font-semibold mb-4">Model Summary</h3>
                <dl className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-[var(--color-text-secondary)]">Version</dt>
                    <dd className="font-mono">{mod.version ?? '—'}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-[var(--color-text-secondary)]">Last Trained</dt>
                    <dd>{mod.trained_at ? new Date(mod.trained_at).toLocaleDateString() : '—'}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-[var(--color-text-secondary)]">Training Rows</dt>
                    <dd>{mod.n_train?.toLocaleString() ?? '—'}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-[var(--color-text-secondary)]">Dataset</dt>
                    <dd>{mod.has_dataset ? 'Loaded' : 'None'}</dd>
                  </div>
                </dl>
              </div>
            </div>
          </div>
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
