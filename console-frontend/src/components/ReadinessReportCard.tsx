import { CheckCircle2, AlertCircle, Info, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import type { ReadinessReport } from '../lib/api';

interface Props {
  report: ReadinessReport;
}

const MODE_CONFIG = {
  TRAINING_READY: {
    label: 'Training-Ready',
    description: 'Supervised churn model training is available.',
    color: 'text-green-700',
    bg: 'bg-green-50',
    border: 'border-green-200',
    dot: 'bg-green-500',
    icon: 'ok' as const,
  },
  TRAINING_DEGRADED: {
    label: 'Training-Ready (Degraded)',
    description: 'Training available with random split — metrics may be slightly optimistic.',
    color: 'text-amber-700',
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    dot: 'bg-amber-400',
    icon: 'warn' as const,
  },
  ANALYSIS_READY: {
    label: 'Behavioral Analysis Mode',
    description: 'No churn label found. Health scoring and cohort analysis are available.',
    color: 'text-blue-700',
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    dot: 'bg-blue-400',
    icon: 'warn' as const,
  },
  PARTIAL: {
    label: 'Partial Dataset',
    description: 'Some required fields are missing. Map more columns to proceed.',
    color: 'text-orange-700',
    bg: 'bg-orange-50',
    border: 'border-orange-200',
    dot: 'bg-orange-400',
    icon: 'warn' as const,
  },
  BLOCKED: {
    label: 'Blocked',
    description: 'Cannot proceed — see required fields below.',
    color: 'text-red-700',
    bg: 'bg-red-50',
    border: 'border-red-200',
    dot: 'bg-red-500',
    icon: 'block' as const,
  },
};

export function ReadinessReportCard({ report }: Props) {
  const [showPreview, setShowPreview] = useState(false);
  const cfg = MODE_CONFIG[report.mode] ?? MODE_CONFIG.BLOCKED;

  const requiredFields = Object.entries(report.required_mapped);
  const mappedRecommended = Object.values(report.recommended_mapped).filter(Boolean).length;
  const totalRecommended = Object.keys(report.recommended_mapped).length;

  const previewCols = report.normalized_preview.length > 0
    ? Object.keys(report.normalized_preview[0])
    : [];

  return (
    <div className="bg-white border border-[var(--color-border)] rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.08)] overflow-hidden">
      {/* Mode banner */}
      <div className={`px-6 py-4 ${cfg.bg} border-b ${cfg.border}`}>
        <div className="flex items-center gap-2">
          <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${cfg.dot}`} />
          <span className={`text-sm font-semibold ${cfg.color}`}>{cfg.label}</span>
        </div>
        <p className={`text-xs mt-0.5 ${cfg.color} opacity-80`}>{cfg.description}</p>
        {report.mode_reason && report.mode_reason !== cfg.description && (
          <p className={`text-xs mt-1 ${cfg.color} opacity-70`}>{report.mode_reason}</p>
        )}
      </div>

      <div className="px-6 py-4 space-y-4">
        {/* Coverage summary */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-[var(--color-bg-primary)] rounded-xl p-3 text-center">
            <div className="text-lg font-bold text-[var(--color-text-primary)]">
              {requiredFields.filter(([, v]) => v).length}/{requiredFields.length}
            </div>
            <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5">Required fields</div>
          </div>
          <div className="bg-[var(--color-bg-primary)] rounded-xl p-3 text-center">
            <div className="text-lg font-bold text-[var(--color-text-primary)]">
              {mappedRecommended}/{totalRecommended}
            </div>
            <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5">Recommended fields</div>
          </div>
          <div className="bg-[var(--color-bg-primary)] rounded-xl p-3 text-center">
            <div className="text-lg font-bold text-[var(--color-text-primary)]">
              {report.usable_feature_count}
            </div>
            <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5">Usable features</div>
          </div>
        </div>

        {/* Required fields status */}
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
            Required Fields
          </p>
          <div className="space-y-1.5">
            {requiredFields.map(([field, mapped]) => (
              <div key={field} className="flex items-center gap-2">
                {mapped ? (
                  <CheckCircle2 size={13} className="text-[var(--color-success)] shrink-0" />
                ) : (
                  <AlertCircle size={13} className="text-[var(--color-danger)] shrink-0" />
                )}
                <code className="text-xs text-[var(--color-accent)]">{field}</code>
                {!mapped && (
                  <span className="text-[10px] text-[var(--color-danger)]">
                    {field === 'churned'
                      ? '— training disabled, analysis mode only'
                      : field === 'snapshot_date'
                      ? '— random split will be used'
                      : '— required, not found'}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Derived fields */}
        {report.derived_fields.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1.5">
              Derived Automatically
            </p>
            <div className="flex flex-wrap gap-1.5">
              {report.derived_fields.map(f => (
                <span key={f} className="text-[10px] px-2 py-0.5 bg-[var(--color-accent)]/10 text-[var(--color-accent)] border border-[var(--color-accent)]/20 rounded-full">
                  {f}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Label distribution */}
        {report.label_distribution && (
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1.5">
              Label Distribution
            </p>
            <div className="flex items-center gap-3 text-xs">
              {Object.entries(report.label_distribution).map(([k, n]) => (
                <span key={k} className="px-2 py-1 bg-[var(--color-bg-primary)] rounded-lg font-mono text-xs">
                  {k === '0' ? 'Retained' : 'Churned'}: {n.toLocaleString()}
                </span>
              ))}
              {report.split_strategy === 'random' && (
                <span className="text-[10px] text-amber-600 ml-1">· random split</span>
              )}
              {report.split_strategy === 'time_based' && (
                <span className="text-[10px] text-green-600 ml-1">· time-based split</span>
              )}
            </div>
          </div>
        )}

        {/* Warnings */}
        {report.warnings.length > 0 && (
          <div className="space-y-1">
            {report.warnings.map((w, i) => (
              <div key={i} className="flex items-start gap-1.5 text-xs text-amber-700">
                <Info size={12} className="mt-0.5 shrink-0" />
                {w}
              </div>
            ))}
          </div>
        )}

        {/* Improvement suggestions */}
        {report.improvements.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1.5">
              What would improve model quality
            </p>
            <ul className="space-y-1">
              {report.improvements.map((tip, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-[var(--color-text-secondary)]">
                  <span className="shrink-0 mt-0.5 text-[var(--color-text-muted)]">•</span>
                  {tip}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Normalized preview (collapsible) */}
        {report.normalized_preview.length > 0 && (
          <div>
            <button
              onClick={() => setShowPreview(v => !v)}
              className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
            >
              {showPreview ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              Normalized Preview (5 rows)
            </button>
            {showPreview && (
              <div className="mt-2 overflow-x-auto rounded-xl border border-[var(--color-border)]">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-[var(--color-bg-primary)] border-b border-[var(--color-border)]">
                      {previewCols.map(col => (
                        <th key={col} className="px-3 py-2 text-left font-mono text-[10px] text-[var(--color-text-muted)] whitespace-nowrap">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {report.normalized_preview.map((row, i) => (
                      <tr key={i} className="border-b border-[var(--color-border)]/50">
                        {previewCols.map(col => (
                          <td key={col} className="px-3 py-1.5 text-[var(--color-text-secondary)] whitespace-nowrap max-w-[120px] truncate">
                            {row[col] === null || row[col] === undefined ? (
                              <span className="text-[var(--color-text-muted)]">—</span>
                            ) : String(row[col])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
