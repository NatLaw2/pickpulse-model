import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid, Legend, ReferenceLine } from 'recharts';
import { FileText, Info, TrendingDown, TrendingUp } from 'lucide-react';
import { api, type EvalMetrics, type ModelInsights, type BehavioralDiffItem } from '../lib/api';
import { StatCard } from '../components/StatCard';
import { formatCurrency } from '../lib/format';

export function EvaluatePage({ embedded }: { embedded?: boolean } = {}) {
  const [metrics, setMetrics] = useState<EvalMetrics | null>(null);
  const [insights, setInsights] = useState<ModelInsights | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.evaluate().then(setMetrics).catch((e) => { setMetrics(null); setError(e.message); });
    api.modelInsights().then(setInsights).catch(() => setInsights(null));
  }, []);

  const calData = metrics?.calibration_bins?.map((b) => ({
    bin: `${(b.bin_lo * 100).toFixed(0)}-${(b.bin_hi * 100).toFixed(0)}%`,
    predicted: b.predicted_avg,
    actual: b.actual_rate,
  }));

  const liftData = metrics?.lift_table?.map((r) => ({
    decile: `D${r.decile}`,
    lift: r.lift,
    capture: +(r.cumulative_capture * 100).toFixed(1),
    rate: +(r.actual_rate * 100).toFixed(1),
  }));

  return (
    <div>
      {!embedded && (
        <div className="mb-8">
          <h1 className="text-2xl font-bold">Model Performance</h1>
          <p className="text-sm text-[var(--color-text-secondary)] mt-1">
            Discrimination, calibration, and business impact of the trained churn model
          </p>
        </div>
      )}

      {error && !metrics && (
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-10 text-center text-[var(--color-text-secondary)] shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          No evaluation data available. Train a model first to see performance metrics.
        </div>
      )}

      {metrics && (
        <div className="space-y-8">
          {/* Executive metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <StatCard
              label="AUC"
              value={metrics.auc?.toFixed(3) ?? '—'}
              sub={metrics.auc != null ? (metrics.auc > 0.8 ? 'Strong discrimination' : metrics.auc > 0.7 ? 'Good discrimination' : 'Fair discrimination') : undefined}
              accent="var(--color-accent)"
              tooltip="Area Under the ROC Curve — measures how well the model separates churners from retainers. 1.0 = perfect separation, 0.5 = no better than random."
            />
            <StatCard
              label="Lift @ Top 10%"
              value={metrics.lift_at_top10 != null ? `${metrics.lift_at_top10}x` : '—'}
              sub="vs. random targeting"
              accent="var(--color-success)"
              tooltip="How many times more effective the model's top 10% risk bucket is at identifying churners compared to selecting accounts at random."
            />
            <StatCard
              label="Precision"
              value={metrics.precision != null ? `${(metrics.precision * 100).toFixed(1)}%` : '—'}
              sub={metrics.threshold != null ? `Risk threshold: ${(metrics.threshold * 100).toFixed(1)}%` : undefined}
              tooltip="Of all accounts the model flags as likely churners, what percentage actually churned. Uses the threshold that optimizes the balance between precision and recall."
            />
            <StatCard
              label="Recall"
              value={metrics.recall != null ? `${(metrics.recall * 100).toFixed(1)}%` : '—'}
              sub={metrics.f1 != null ? `Balance score (F1): ${(metrics.f1 * 100).toFixed(1)}%` : undefined}
              tooltip="Of all accounts that actually churned, what percentage the model correctly identified. Higher recall means fewer missed churners."
            />
          </div>

          {/* Business impact */}
          {metrics.business_impact && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
              <div className="flex items-center gap-2 mb-4">
                <h3 className="text-sm font-semibold">Business Impact</h3>
                <span className="text-[var(--color-text-muted)]" title="Quantifies the revenue at risk and the model's ability to concentrate risk into actionable segments."><Info size={14} /></span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm">
                <div>
                  <div className="text-xs text-[var(--color-text-muted)] mb-1">Total ARR</div>
                  <div className="text-xl font-bold">{formatCurrency(metrics.business_impact.total_value)}</div>
                </div>
                <div>
                  <div className="text-xs text-[var(--color-text-muted)] mb-1">Total ARR at Risk</div>
                  <div className="text-xl font-bold text-[var(--color-danger)]">
                    {formatCurrency(metrics.business_impact.total_arr_at_risk ?? 0)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-[var(--color-text-muted)] mb-1">ARR Captured in Top 10%</div>
                  <div className="text-xl font-bold text-[var(--color-warning)]">
                    {formatCurrency(metrics.business_impact.arr_at_risk_top_decile ?? 0)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-[var(--color-text-muted)] mb-1">Churners in Top 10%</div>
                  <div className="text-xl font-bold">{metrics.business_impact.positives_in_top_decile} / {metrics.business_impact.total_positives}</div>
                </div>
              </div>
            </div>
          )}

          {/* What the Model Learned */}
          {insights && (insights.churn_drivers.length > 0 || insights.health_signals.length > 0) && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-sm font-semibold">What the Model Learned</h3>
                <span className="text-[var(--color-text-muted)]" title="Plain-language translation of the model's feature importance — which signals most strongly predict churn or retention in your dataset."><Info size={14} /></span>
              </div>
              {insights.top_insight && (
                <p className="text-sm text-[var(--color-text-secondary)] mb-5">{insights.top_insight}</p>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {/* Churn drivers */}
                {insights.churn_drivers.length > 0 && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-3">
                      <TrendingDown size={13} className="text-[var(--color-danger)]" />
                      <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-danger)]">Top Churn Drivers</span>
                    </div>
                    <div className="space-y-3">
                      {insights.churn_drivers.map((d) => (
                        <div key={d.rank}>
                          <div className="flex items-center justify-between mb-0.5">
                            <span className="text-sm font-medium">{d.label}</span>
                            <span className="text-xs text-[var(--color-text-muted)]">{d.group}</span>
                          </div>
                          <div className="w-full h-1.5 bg-[var(--color-bg-primary)] rounded-full overflow-hidden mb-1">
                            <div
                              className="h-full rounded-full bg-[var(--color-danger)]"
                              style={{ width: `${Math.round(d.importance_normalized * 100)}%`, opacity: 0.7 + d.importance_normalized * 0.3 }}
                            />
                          </div>
                          <p className="text-xs text-[var(--color-text-muted)]">{d.description}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Health signals */}
                {insights.health_signals.length > 0 && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-3">
                      <TrendingUp size={13} className="text-[var(--color-success)]" />
                      <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-success)]">Retention Signals</span>
                    </div>
                    <div className="space-y-3">
                      {insights.health_signals.map((d) => (
                        <div key={d.rank}>
                          <div className="flex items-center justify-between mb-0.5">
                            <span className="text-sm font-medium">{d.label}</span>
                            <span className="text-xs text-[var(--color-text-muted)]">{d.group}</span>
                          </div>
                          <div className="w-full h-1.5 bg-[var(--color-bg-primary)] rounded-full overflow-hidden mb-1">
                            <div
                              className="h-full rounded-full bg-[var(--color-success)]"
                              style={{ width: `${Math.round(d.importance_normalized * 100)}%`, opacity: 0.7 + d.importance_normalized * 0.3 }}
                            />
                          </div>
                          <p className="text-xs text-[var(--color-text-muted)]">{d.description}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              {insights.lift_statement && (
                <p className="mt-5 pt-4 border-t border-[var(--color-border)] text-xs text-[var(--color-text-muted)]">
                  {insights.lift_statement}
                </p>
              )}
            </div>
          )}

          {/* Behavioral Diff — What Churned Accounts Did Differently */}
          {insights?.behavioral_diff && insights.behavioral_diff.items.length > 0 && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-sm font-semibold">What Churned Accounts Did Differently</h3>
                <span className="text-[var(--color-text-muted)]" title="Computed from actual churned vs retained accounts in your dataset — not modeled estimates."><Info size={14} /></span>
              </div>
              <p className="text-xs text-[var(--color-text-muted)] mb-5">
                Compared to retained accounts, churned accounts showed:
              </p>
              <div className="space-y-3 mb-5">
                {insights.behavioral_diff.items.map((item: BehavioralDiffItem) => (
                  <div key={item.label} className="flex items-start gap-3">
                    <span
                      className="mt-0.5 text-base font-bold leading-none"
                      style={{ color: item.direction === 'down' ? 'var(--color-danger)' : 'var(--color-warning)' }}
                    >
                      {item.summary.charAt(0)}
                    </span>
                    <div>
                      <span className="text-sm font-medium">{item.summary.slice(2)}</span>
                      <span className="text-xs text-[var(--color-text-muted)] ml-2">
                        ({item.churned_avg.toLocaleString(undefined, { maximumFractionDigits: 1 })} churned vs {item.retained_avg.toLocaleString(undefined, { maximumFractionDigits: 1 })} retained)
                      </span>
                    </div>
                  </div>
                ))}
              </div>
              {insights.behavioral_diff.interpretation && (
                <p className="pt-4 border-t border-[var(--color-border)] text-xs text-[var(--color-text-secondary)] italic">
                  {insights.behavioral_diff.interpretation}
                </p>
              )}
              <p className="mt-3 text-[10px] text-[var(--color-text-muted)]">
                Based on {insights.behavioral_diff.n_churned} churned and {insights.behavioral_diff.n_retained} retained accounts in the training dataset.
              </p>
            </div>
          )}

          {/* Charts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {calData && calData.length > 0 && (
              <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
                <h3 className="text-sm font-semibold mb-1">Calibration</h3>
                <p className="text-xs text-[var(--color-text-muted)] mb-4">How closely predicted probabilities match observed churn rates</p>
                <ResponsiveContainer width="100%" height={250}>
                  <LineChart data={calData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.08)" />
                    <XAxis dataKey="bin" tick={{ fontSize: 10, fill: '#9CA0B0' }} />
                    <YAxis tick={{ fontSize: 10, fill: '#9CA0B0' }} domain={[0, 1]} />
                    <Tooltip contentStyle={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 12, fontSize: 12 }} />
                    <ReferenceLine stroke="rgba(0,0,0,0.1)" strokeDasharray="3 3" segment={[{ x: calData[0]?.bin, y: 0 }, { x: calData[calData.length - 1]?.bin, y: 1 }]} />
                    <Line type="monotone" dataKey="predicted" stroke="#7B61FF" strokeWidth={2} dot={{ r: 3 }} name="Predicted" />
                    <Line type="monotone" dataKey="actual" stroke="#10B981" strokeWidth={2} dot={{ r: 3 }} name="Actual" />
                    <Legend />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {liftData && liftData.length > 0 && (
              <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
                <h3 className="text-sm font-semibold mb-1">Lift by Decile</h3>
                <p className="text-xs text-[var(--color-text-muted)] mb-4">How effectively the model concentrates churn risk into the top segments</p>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={liftData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.08)" />
                    <XAxis dataKey="decile" tick={{ fontSize: 10, fill: '#9CA0B0' }} />
                    <YAxis tick={{ fontSize: 10, fill: '#9CA0B0' }} />
                    <Tooltip contentStyle={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 12, fontSize: 12 }} />
                    <Bar dataKey="lift" fill="#7B61FF" radius={[6, 6, 0, 0]} name="Lift" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Tier breakdown */}
          {metrics.tier_breakdown && Object.keys(metrics.tier_breakdown).length > 0 && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
              <h3 className="text-sm font-semibold mb-4">Risk Tier Breakdown</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {Object.entries(metrics.tier_breakdown).map(([tier, info]) => {
                  const color = tier.includes('High') ? 'var(--color-danger)' : tier.includes('Medium') ? 'var(--color-warning)' : 'var(--color-success)';
                  return (
                    <div key={tier} className="bg-[var(--color-bg-primary)] rounded-xl p-5">
                      <div className="text-xs uppercase tracking-wider mb-1" style={{ color }}>{tier}</div>
                      <div className="text-2xl font-bold">{info.count}</div>
                      <div className="text-xs text-[var(--color-text-secondary)] mt-2">
                        Actual churn: {(info.actual_rate * 100).toFixed(1)}% | Avg probability: {(info.avg_probability * 100).toFixed(1)}%
                      </div>
                      {info.total_value != null && (
                        <div className="text-xs text-[var(--color-text-secondary)] mt-1">
                          Total ARR: {formatCurrency(info.total_value)}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Advanced — collapsible */}
          <details className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
            <summary className="text-sm font-semibold cursor-pointer">Detailed Metrics</summary>
            <div className="mt-4 space-y-6">
              {/* Additional metrics */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
                <div><span className="text-xs text-[var(--color-text-muted)]">PR-AUC</span><div className="text-lg font-bold">{metrics.pr_auc?.toFixed(4) ?? '—'}</div></div>
                <div><span className="text-xs text-[var(--color-text-muted)]">Brier Score</span><div className="text-lg font-bold">{metrics.brier.toFixed(4)}</div></div>
                <div><span className="text-xs text-[var(--color-text-muted)]">Log Loss</span><div className="text-lg font-bold">{metrics.logloss.toFixed(4)}</div></div>
                <div><span className="text-xs text-[var(--color-text-muted)]">Accuracy</span><div className="text-lg font-bold">{metrics.accuracy != null ? `${(metrics.accuracy * 100).toFixed(1)}%` : '—'}</div></div>
                <div>
                  <span className="text-xs text-[var(--color-text-muted)]">Optimal Threshold</span>
                  <div className="text-lg font-bold">{metrics.threshold != null ? `${(metrics.threshold * 100).toFixed(1)}%` : '—'}</div>
                  <div className="text-[10px] text-[var(--color-text-muted)]">Balances precision vs. recall</div>
                </div>
              </div>

              {/* Confusion matrix */}
              {metrics.confusion_matrix && (
                <div>
                  <h4 className="text-xs text-[var(--color-text-muted)] mb-2 uppercase">Confusion Matrix</h4>
                  <div className="inline-grid grid-cols-3 gap-1 text-sm text-center">
                    <div />
                    <div className="text-xs text-[var(--color-text-muted)] py-2">Predicted Retained</div>
                    <div className="text-xs text-[var(--color-text-muted)] py-2">Predicted Churned</div>
                    <div className="text-xs text-[var(--color-text-muted)] px-3">Actually Retained</div>
                    <div className="bg-[var(--color-bg-primary)] rounded-xl p-3 font-mono">{metrics.confusion_matrix[0][0]}</div>
                    <div className="bg-[var(--color-bg-primary)] rounded-xl p-3 font-mono">{metrics.confusion_matrix[0][1]}</div>
                    <div className="text-xs text-[var(--color-text-muted)] px-3">Actually Churned</div>
                    <div className="bg-[var(--color-bg-primary)] rounded-xl p-3 font-mono">{metrics.confusion_matrix[1][0]}</div>
                    <div className="bg-[var(--color-bg-primary)] rounded-xl p-3 font-mono">{metrics.confusion_matrix[1][1]}</div>
                  </div>
                </div>
              )}

              {/* Lift table */}
              {metrics.lift_table && (
                <div>
                  <h4 className="text-xs text-[var(--color-text-muted)] mb-2 uppercase">Lift / Decile Table</h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs text-[var(--color-text-muted)] uppercase border-b border-[var(--color-border)]">
                          <th className="py-2 pr-3">Decile</th>
                          <th className="py-2 pr-3 text-right">N</th>
                          <th className="py-2 pr-3 text-right">Avg Probability</th>
                          <th className="py-2 pr-3 text-right">Actual Rate</th>
                          <th className="py-2 pr-3 text-right">Lift</th>
                          <th className="py-2 text-right">Cumulative Capture</th>
                        </tr>
                      </thead>
                      <tbody>
                        {metrics.lift_table.map((r, i) => (
                          <tr key={r.decile} className={`border-b border-[var(--color-border)]/50 ${i % 2 === 1 ? 'bg-[var(--color-bg-primary)]' : ''}`}>
                            <td className="py-2 pr-3">{r.decile}</td>
                            <td className="py-2 pr-3 text-right">{r.n}</td>
                            <td className="py-2 pr-3 text-right">{(r.avg_prob * 100).toFixed(1)}%</td>
                            <td className="py-2 pr-3 text-right">{(r.actual_rate * 100).toFixed(1)}%</td>
                            <td className="py-2 pr-3 text-right font-bold">{r.lift.toFixed(2)}x</td>
                            <td className="py-2 text-right">{(r.cumulative_capture * 100).toFixed(1)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </details>

          {/* Download */}
          <div className="flex gap-3">
            <button
              onClick={() => api.downloadReport().catch((e: any) => alert(e.message))}
              className="flex items-center gap-2 px-5 py-2.5 bg-[var(--color-accent)] text-white rounded-xl text-sm font-medium hover:bg-[var(--color-accent-glow)] transition-all shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
            >
              <FileText size={14} />
              Download PDF Report
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
