import { useEffect, useState } from 'react';
import { Check, Download } from 'lucide-react';
import { api, type OnboardingStep } from '../lib/api';

export function OnboardingPage() {
  const [steps, setSteps] = useState<OnboardingStep[]>([]);

  const load = () => api.onboarding().then((d) => setSteps(d.steps)).catch(console.error);
  useEffect(() => { load(); }, []);

  const toggle = async (id: string, current: string) => {
    if (current === 'complete') {
      await api.resetStep(id);
    } else {
      await api.completeStep(id);
    }
    load();
  };

  const completed = steps.filter((s) => s.status === 'complete').length;
  const total = steps.length;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Implementation Guide</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">Step-by-step onboarding checklist to get your churn prediction model live</p>
      </div>

      {/* Progress bar */}
      <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium">{completed} of {total} steps complete</span>
          <span className="text-sm text-[var(--color-accent-glow)] font-bold">{pct}%</span>
        </div>
        <div className="h-2.5 bg-[rgba(255,255,255,0.06)] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${pct}%`, background: 'linear-gradient(90deg, var(--color-accent), var(--color-accent-glow))' }}
          />
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-2">
        {steps.map((step, i) => (
          <button
            key={step.id}
            onClick={() => toggle(step.id, step.status)}
            className={`w-full flex items-center gap-4 px-6 py-4 rounded-2xl text-left transition-all ${
              step.status === 'complete'
                ? 'bg-[var(--color-success)]/10 border border-[var(--color-success)]/20'
                : 'bg-[var(--color-bg-card)] border border-[var(--color-border)] hover:border-[var(--color-border-bright)]'
            } shadow-[0_10px_30px_rgba(0,0,0,0.35)]`}
          >
            <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${
              step.status === 'complete'
                ? 'bg-[var(--color-success)] text-white'
                : 'border-2 border-[rgba(255,255,255,0.2)]'
            }`}>
              {step.status === 'complete' ? <Check size={14} /> : <span className="text-xs text-[var(--color-text-muted)]">{i + 1}</span>}
            </div>
            <div className="flex-1 min-w-0">
              <div className={`text-sm font-medium ${step.status === 'complete' ? 'text-[var(--color-success)]' : ''}`}>
                {step.label}
              </div>
              <div className="text-xs text-[var(--color-text-secondary)] mt-0.5">{step.description}</div>
            </div>
          </button>
        ))}
      </div>

      {/* Actions */}
      <div className="mt-8 flex gap-3">
        <a
          href={api.downloadTemplate()}
          className="flex items-center gap-2 px-4 py-2.5 bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-xl text-sm hover:bg-[var(--color-bg-card-hover)] transition-colors"
        >
          <Download size={14} />
          Download Data Template
        </a>
      </div>
    </div>
  );
}
