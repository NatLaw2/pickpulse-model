import { useState, useEffect, useRef, useCallback } from 'react';
import { X, Loader2, Mail, Calendar, BookOpen, PhoneForwarded, ShieldCheck, AlertTriangle } from 'lucide-react';
import { api, type ChurnPrediction, type ExplainResponse, type DraftEmailRequest, type TopDriver } from '../lib/api';
import { riskColor, riskLabel } from '../lib/risk';
import { formatCurrency } from '../lib/format';

function confidenceBg(level: string): string {
  if (level === 'high') return 'bg-green-50 text-green-700';
  if (level === 'medium') return 'bg-amber-50 text-amber-700';
  return 'bg-gray-100 text-[var(--color-text-muted)]';
}

function confidenceLabel(level: string): string {
  if (level === 'high') return 'High data confidence';
  if (level === 'medium') return 'Moderate data confidence';
  return 'Low data confidence';
}

type Tone = 'friendly' | 'direct' | 'executive';

interface Props {
  customerId: string;
  prediction: ChurnPrediction;
  onClose: () => void;
}

export function AccountDetailDrawer({ customerId, prediction, onClose }: Props) {
  const [explainData, setExplainData] = useState<ExplainResponse | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);

  const [draftingAction, setDraftingAction] = useState<string | null>(null);
  const [emailPromptAction, setEmailPromptAction] = useState<string | null>(null);
  const [emailInput, setEmailInput] = useState('');
  const [selectedTone, setSelectedTone] = useState<Tone>('friendly');
  const [draftError, setDraftError] = useState<string | null>(null);

  const drawerRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);

  // Fetch explain data when customerId changes
  const fetchExplain = useCallback(async (id: string) => {
    setExplainData(null);
    setExplainError(null);
    setExplainLoading(true);
    setDraftingAction(null);
    setEmailPromptAction(null);
    setDraftError(null);
    try {
      const data = await api.explainAccount(id);
      setExplainData(data);
    } catch (err: any) {
      setExplainError(err?.message || 'Failed to load account details');
    } finally {
      setExplainLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchExplain(customerId);
  }, [customerId, fetchExplain]);

  // Close drawer on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [onClose]);

  // Close email overlay on outside click
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

  // Playbook handlers
  const handleDraftEmail = async (actionType: string, contactEmail: string | null) => {
    setEmailPromptAction(null);
    setDraftingAction(actionType);
    setDraftError(null);
    try {
      const req: DraftEmailRequest = {
        account_id: prediction.account_id,
        customer_name: prediction.name || prediction.account_id,
        contact_email: contactEmail || null,
        churn_risk_pct: prediction.churn_risk_pct,
        arr: prediction.arr ?? 0,
        arr_at_risk: prediction.arr_at_risk ?? 0,
        days_until_renewal: prediction.days_until_renewal ?? 0,
        recommended_action: prediction.recommended_action,
        risk_driver_summary: explainData?.risk_driver_summary || null,
        tier: prediction.tier,
        tone: selectedTone,
      };
      const result = await api.draftOutreachEmail(req);
      await api.logPlaybookAction(prediction.account_id, actionType);
      window.location.href = result.mailto_url;
    } catch (err: any) {
      setDraftError(err?.message || 'Failed to generate email');
    } finally {
      setDraftingAction(null);
      setEmailInput('');
    }
  };

  const handleScheduleReview = async () => {
    setDraftingAction('schedule_success_review');
    try {
      await api.logPlaybookAction(prediction.account_id, 'schedule_success_review');
      await api.downloadIcs(prediction.account_id);
    } catch (err: any) {
      setDraftError(err?.message || 'Failed to download calendar invite');
    } finally {
      setDraftingAction(null);
    }
  };

  const handleEscalateToSales = async () => {
    setDraftingAction('escalate_to_sales');
    try {
      await api.logPlaybookAction(prediction.account_id, 'escalate_to_sales');
      const subject = encodeURIComponent(
        `Escalation: ${prediction.account_id} — ${prediction.churn_risk_pct}% churn risk, ${formatCurrency(prediction.arr_at_risk)} ARR at risk`
      );
      const body = encodeURIComponent(
        `Account ${prediction.account_id} has been flagged for sales escalation.\n\n` +
        `Churn Risk: ${prediction.churn_risk_pct}%\n` +
        `ARR: ${formatCurrency(prediction.arr)}\n` +
        `ARR at Risk: ${formatCurrency(prediction.arr_at_risk)}\n` +
        `Days Until Renewal: ${prediction.days_until_renewal}\n` +
        `Recommended Action: ${prediction.recommended_action}\n` +
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

  const renderEmailOverlay = (actionType: string) => (
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
            if (e.key === 'Enter') handleDraftEmail(actionType, emailInput.trim() || null);
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
          onClick={() => handleDraftEmail(actionType, emailInput.trim() || null)}
          className="flex-1 px-3 py-1.5 text-[10px] font-semibold rounded-lg bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-glow)] transition-colors"
        >
          Generate
        </button>
        <button
          onClick={() => handleDraftEmail(actionType, null)}
          className="px-3 py-1.5 text-[10px] font-medium rounded-lg bg-white border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-primary)] transition-colors"
        >
          Skip Email
        </button>
      </div>
    </div>
  );

  return (
    <div
      ref={drawerRef}
      className="fixed top-0 right-0 w-[400px] h-full bg-white border-l border-[var(--color-border)] shadow-[-10px_0_30px_rgba(0,0,0,0.1)] z-50 overflow-y-auto"
    >
      {/* Drawer header */}
      <div className="sticky top-0 bg-white border-b border-[var(--color-border)] px-5 py-4 flex items-center justify-between z-10">
        <div>
          <h3 className="text-sm font-bold">Why This Account Is At Risk</h3>
          <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{prediction.name || prediction.account_id}</p>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-[var(--color-bg-primary)] transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      <div className="px-5 py-5 space-y-6">
        {/* Urgent renewal warning */}
        {prediction.days_until_renewal != null && prediction.days_until_renewal <= 30 && (
          <div className="flex items-center gap-2 px-3 py-2.5 bg-red-50 border border-red-200 rounded-xl text-xs font-semibold text-red-700">
            ⚠️ Renewal in {prediction.days_until_renewal} days — act now
          </div>
        )}

        {/* Account Summary */}
        <div>
          <h4 className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-3">Account Summary</h4>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-[var(--color-bg-primary)] rounded-xl p-3">
              <div className="text-[10px] text-[var(--color-text-muted)] mb-1">Churn Risk</div>
              <div className="text-lg font-bold" style={{ color: riskColor(prediction.churn_risk_pct) }}>
                {prediction.churn_risk_pct}%
              </div>
              <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                <span className="text-[10px]" style={{ color: riskColor(prediction.churn_risk_pct) }}>
                  {riskLabel(prediction.churn_risk_pct)} Risk
                </span>
                {explainData?.confidence_level && (
                  <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded-full ${confidenceBg(explainData.confidence_level)}`}>
                    {confidenceLabel(explainData.confidence_level)}
                  </span>
                )}
              </div>
            </div>
            <div className="bg-[var(--color-bg-primary)] rounded-xl p-3">
              <div className="text-[10px] text-[var(--color-text-muted)] mb-1">ARR at Risk</div>
              <div className="text-lg font-bold text-[var(--color-danger)]">
                {formatCurrency(prediction.arr_at_risk)}
              </div>
              <div className="text-[10px] text-[var(--color-text-muted)]">
                of {formatCurrency(prediction.arr)} ARR
              </div>
            </div>
            <div className="bg-[var(--color-bg-primary)] rounded-xl p-3">
              <div className="text-[10px] text-[var(--color-text-muted)] mb-1">Renewal</div>
              <div className="text-sm font-bold">{prediction.days_until_renewal} days</div>
              <div className={`text-[10px] ${
                prediction.renewal_window_label === '<30d' ? 'text-[var(--color-danger)]' :
                prediction.renewal_window_label === '30-90d' ? 'text-[var(--color-warning)]' :
                'text-[var(--color-text-muted)]'
              }`}>
                {prediction.renewal_window_label} window
              </div>
            </div>
            <div className="bg-[var(--color-bg-primary)] rounded-xl p-3">
              <div className="text-[10px] text-[var(--color-text-muted)] mb-1">Tier</div>
              <div className="text-sm font-bold">{prediction.tier}</div>
              <div className="text-[10px] text-[var(--color-text-muted)]">
                Auto-renew: {prediction.auto_renew_flag ? 'On' : 'Off'}
              </div>
            </div>
          </div>
        </div>

        {/* Signal Analysis */}
        <div>
          <h4 className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-3">Signal Analysis</h4>
          {explainLoading && (
            <div className="flex items-center gap-2 py-4 text-xs text-[var(--color-text-muted)]">
              <Loader2 size={14} className="animate-spin" />
              Analyzing account signals...
            </div>
          )}
          {explainError && (
            <div className="px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-xs text-[var(--color-danger)]">
              {explainError}
            </div>
          )}
          {explainData && (() => {
            const structuredDrivers: TopDriver[] = explainData.top_drivers ?? [];
            const riskSignals = structuredDrivers.filter(d => d.direction === 'increases_risk');
            const protectiveSignals = structuredDrivers.filter(d => d.direction === 'decreases_risk');

            if (structuredDrivers.length > 0) {
              return (
                <div className="space-y-4">
                  {riskSignals.length > 0 && (
                    <div>
                      <p className="text-[10px] text-[var(--color-text-muted)] flex items-center gap-1 mb-2">
                        <AlertTriangle size={10} className="text-[var(--color-danger)]" />
                        Signals driving risk
                      </p>
                      <div className="space-y-1.5">
                        {riskSignals.map((d, i) => (
                          <div
                            key={i}
                            className={`flex items-start gap-2 px-3 py-2.5 rounded-xl text-xs ${
                              i === 0
                                ? 'bg-red-50 border border-red-100'
                                : 'bg-[var(--color-bg-primary)]'
                            }`}
                          >
                            <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-[var(--color-danger)] flex-shrink-0" />
                            <div>
                              <span className={i === 0 ? 'text-[var(--color-text-primary)] font-semibold' : 'text-[var(--color-text-primary)]'}>
                                {d.label}
                              </span>
                              {d.explanation_text && (
                                <p className="text-[var(--color-text-muted)] mt-0.5 leading-relaxed">
                                  {d.explanation_text}
                                </p>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {protectiveSignals.length > 0 && (
                    <div>
                      <p className="text-[10px] text-[var(--color-text-muted)] flex items-center gap-1 mb-2">
                        <ShieldCheck size={10} className="text-green-600" />
                        Working in their favor
                      </p>
                      <div className="space-y-1.5">
                        {protectiveSignals.map((d, i) => (
                          <div
                            key={i}
                            className="flex items-start gap-2 px-3 py-2.5 rounded-xl text-xs bg-green-50 border border-green-100"
                          >
                            <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
                            <div>
                              <span className="text-[var(--color-text-primary)]">{d.label}</span>
                              {d.explanation_text && (
                                <p className="text-[var(--color-text-muted)] mt-0.5 leading-relaxed">
                                  {d.explanation_text}
                                </p>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            }

            // Contextual fallback — use account facts already in prediction prop.
            // Clearly labeled as a summary, not model-derived signal analysis.
            const fallbackBullets: string[] = [];
            if (prediction.days_until_renewal != null) {
              fallbackBullets.push(
                `Renewal ${prediction.days_until_renewal} day${prediction.days_until_renewal === 1 ? '' : 's'} away` +
                (prediction.renewal_window_label ? ` (${prediction.renewal_window_label} window)` : '')
              );
            }
            if (prediction.arr_at_risk != null && prediction.arr_at_risk > 0) {
              fallbackBullets.push(
                `${formatCurrency(prediction.arr_at_risk)} ARR at risk of ${formatCurrency(prediction.arr ?? 0)} total`
              );
            }
            fallbackBullets.push(
              `Classified as ${prediction.tier ?? 'Unknown'} based on composite model output`
            );
            return (
              <div className="space-y-2">
                <p className="text-[10px] text-[var(--color-text-muted)] leading-relaxed">
                  Limited signal data available from this source. Risk score reflects composite model output.
                </p>
                <div className="space-y-1.5">
                  {fallbackBullets.map((b, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2 px-3 py-2 rounded-lg bg-[var(--color-bg-primary)] text-xs text-[var(--color-text-secondary)]"
                    >
                      <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-[var(--color-text-muted)] flex-shrink-0" />
                      {b}
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}
        </div>

        {/* Priority Tier + Recommended Action */}
        {(explainData?.action_tier || prediction.action_tier || prediction.recommended_action) && (
          <div className="space-y-2">
            {(explainData?.action_tier || prediction.action_tier) && (() => {
              const tier = explainData?.action_tier ?? prediction.action_tier;
              const tierConfig: Record<string, { label: string; cls: string }> = {
                act_now: { label: 'Act Now', cls: 'bg-red-50 border-red-200 text-red-700' },
                watch_closely: { label: 'Watch Closely', cls: 'bg-amber-50 border-amber-200 text-amber-700' },
                low_priority: { label: 'Low Priority', cls: 'bg-gray-50 border-gray-200 text-[var(--color-text-muted)]' },
              };
              const config = tierConfig[tier ?? ''] ?? { label: tier, cls: 'bg-gray-50 border-gray-200 text-[var(--color-text-muted)]' };
              return (
                <div className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border ${config.cls}`}>
                  {config.label}
                </div>
              );
            })()}
            {prediction.recommended_action && (
              <div>
                <h4 className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Recommended Action</h4>
                <div className="px-3 py-2.5 bg-[var(--color-accent)]/8 border border-[var(--color-accent)]/20 rounded-xl text-xs text-[var(--color-accent)]">
                  {prediction.recommended_action}
                </div>
              </div>
            )}
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
              {emailPromptAction === 'generate_outreach' && !draftingAction && renderEmailOverlay('generate_outreach')}
            </div>

            {/* Schedule Success Review */}
            <button
              onClick={handleScheduleReview}
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
              {emailPromptAction === 'send_feature_training' && !draftingAction && renderEmailOverlay('send_feature_training')}
            </div>

            {/* Escalate to Sales */}
            <button
              onClick={handleEscalateToSales}
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
  );
}
