interface WorkflowStep {
  step: string;
  title: string;
  desc: string;
  bullets: string[];
  optional?: boolean;
}

const workflowSteps: WorkflowStep[] = [
  {
    step: '1',
    title: 'Data Ingestion',
    desc: 'Structured export from CRM or billing.',
    bullets: ['CSV, HubSpot, or Stripe', 'Mapped via clean template'],
  },
  {
    step: '2',
    title: 'Model Training & Risk Scoring',
    desc: 'Gradient-boosted ensemble on your outcomes.',
    bullets: ['Learns feature weights from your data', 'Outputs calibrated probabilities'],
  },
  {
    step: '3',
    title: 'Account Prioritization',
    desc: 'Every account ranked by risk and urgency.',
    bullets: ['Combines churn probability + renewal proximity', 'Segmented into High / Medium / Low tiers'],
  },
  {
    step: '4',
    title: 'Revenue Impact Simulation',
    desc: 'Model recoverable ARR at varying save rates.',
    bullets: ['Adjustable 20\u201360% save assumption', 'ARR-at-risk quantified per tier'],
  },
  {
    step: '5',
    title: 'Portfolio Roll-Up',
    desc: 'Aggregate risk view across the book.',
    bullets: ['Executive summary + PDF export', 'Renewal pipeline overlay'],
    optional: true,
  },
];

export function LeaveBehind() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0B0F14] to-[#0E1623] text-[#E8ECF1] print:bg-[#0B0F14]">
      <div className="max-w-[960px] mx-auto px-8 py-10 print:py-6 print:px-6">

        {/* ─── Header ─── */}
        <header className="flex items-center justify-between mb-8 print:mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#5CF2C2] to-[#4DA3FF] flex items-center justify-center">
              <span className="text-[#0B0F14] text-xs font-extrabold tracking-tight leading-none">PPI</span>
            </div>
            <div>
              <div className="text-sm font-bold tracking-tight text-white">PickPulse Intelligence</div>
              <div className="text-[10px] text-[#5CF2C2]/70 font-medium tracking-widest uppercase">Churn Risk Engine</div>
            </div>
          </div>
          <div className="px-3 py-1 rounded-full border border-[#5CF2C2]/20 bg-[#5CF2C2]/5 text-[10px] font-semibold text-[#5CF2C2] uppercase tracking-wider">
            Workflow Overview
          </div>
        </header>

        {/* ─── 1. Recap ─── */}
        <section className="mb-7 print:mb-5">
          <SectionLabel number="01" title="What It Is" />
          <div className="grid grid-cols-1 md:grid-cols-5 gap-2.5 mt-3">
            {[
              'Predicts account-level churn using your historical data and outcomes.',
              'Assigns a calibrated probability to every account — not an opaque score.',
              'Ranks accounts by revenue exposure and renewal urgency.',
              'Generates a prioritized save list your CS team can act on immediately.',
              'Delivers executive reporting with ARR-at-risk visibility.',
            ].map((text, i) => (
              <div key={i} className="flex gap-2.5 items-start bg-white/[0.03] border border-white/[0.06] rounded-lg px-3 py-2.5">
                <span className="mt-0.5 shrink-0 w-4 h-4 rounded-full bg-[#5CF2C2]/10 border border-[#5CF2C2]/30 flex items-center justify-center">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#5CF2C2]" />
                </span>
                <p className="text-[11px] leading-[1.45] text-[#B0B8C5]">{text}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ─── 2. Workflow ─── */}
        <section className="mb-7 print:mb-5">
          <SectionLabel number="02" title="How It Works" />
          <div className="flex items-stretch gap-0 mt-3 overflow-x-auto print:overflow-visible">
            {(workflowSteps).map((item, i, arr) => (
              <div key={i} className="flex items-stretch shrink-0" style={{ width: `${100 / arr.length}%`, minWidth: 155 }}>
                <div className={`flex-1 border border-white/[0.06] bg-white/[0.03] rounded-lg px-3 py-3 flex flex-col ${item.optional ? 'border-dashed border-[#4DA3FF]/30' : ''}`}>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="w-5 h-5 rounded-md bg-[#5CF2C2]/10 text-[#5CF2C2] text-[10px] font-bold flex items-center justify-center">{item.step}</span>
                    <span className="text-[11px] font-semibold text-white leading-tight">{item.title}</span>
                    {item.optional && (
                      <span className="ml-auto px-1.5 py-0.5 rounded text-[8px] font-semibold uppercase tracking-wider bg-[#4DA3FF]/10 text-[#4DA3FF] border border-[#4DA3FF]/20">Optional</span>
                    )}
                  </div>
                  <p className="text-[10px] text-[#8891A0] leading-snug mb-1.5">{item.desc}</p>
                  <ul className="space-y-0.5 mt-auto">
                    {item.bullets.map((b, j) => (
                      <li key={j} className="text-[10px] text-[#6B7280] leading-snug flex gap-1.5 items-start">
                        <span className="text-[#5CF2C2]/50 mt-px">›</span>{b}
                      </li>
                    ))}
                  </ul>
                </div>
                {i < arr.length - 1 && (
                  <div className="flex items-center px-1 shrink-0">
                    <svg width="14" height="10" viewBox="0 0 14 10" fill="none" className="text-[#5CF2C2]/30">
                      <path d="M0 5h11M9 1l4 4-4 4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* ─── 3. Onboarding ─── */}
        <section className="mb-7 print:mb-5">
          <div className="flex items-center gap-3 mb-3">
            <SectionLabel number="03" title="Onboarding" />
            <span className="px-2 py-0.5 rounded-full bg-[#5CF2C2]/8 border border-[#5CF2C2]/15 text-[9px] font-semibold text-[#5CF2C2] uppercase tracking-wider">30-Day Pilot</span>
          </div>
          <div className="grid grid-cols-4 gap-2.5">
            {([
              { week: 'Week 1', title: 'Data Alignment', items: ['Template mapping', 'Field validation', 'Historical outcome labeling'] },
              { week: 'Week 2', title: 'Model Training', items: ['Feature engineering', 'Model fit + cross-validation', 'Calibration check'] },
              { week: 'Week 3', title: 'Live Scoring', items: ['Full account scoring', 'Risk tier assignment', 'Prioritized save list'] },
              { week: 'Week 4', title: 'Impact Modeling', items: ['ARR-at-risk quantification', 'Save-rate simulation', 'Executive summary delivery'] },
            ] as const).map((w, i) => (
              <div key={i} className="bg-white/[0.03] border border-white/[0.06] rounded-lg px-3 py-3">
                <div className="text-[9px] font-bold text-[#5CF2C2]/60 uppercase tracking-wider mb-0.5">{w.week}</div>
                <div className="text-[12px] font-semibold text-white mb-2">{w.title}</div>
                <ul className="space-y-1">
                  {w.items.map((item, j) => (
                    <li key={j} className="text-[10px] text-[#8891A0] leading-snug flex gap-1.5 items-start">
                      <span className="text-[#5CF2C2]/40 mt-px">›</span>{item}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="mt-2.5 px-4 py-2 rounded-lg bg-[#5CF2C2]/[0.04] border border-[#5CF2C2]/10 flex items-center gap-2">
            <span className="text-[9px] font-bold text-[#5CF2C2]/50 uppercase tracking-wider shrink-0">Deliverables</span>
            <span className="w-px h-3 bg-[#5CF2C2]/15" />
            <span className="text-[10px] text-[#B0B8C5]">Risk tiers &nbsp;·&nbsp; Prioritized save list &nbsp;·&nbsp; ARR at risk &nbsp;·&nbsp; Executive summary</span>
          </div>
        </section>

        {/* ─── Bottom Row: Outcome + ARR Impact Lens ─── */}
        <div className="grid grid-cols-3 gap-2.5 mb-6 print:mb-4">
          {/* Outcome band */}
          <div className="col-span-2 rounded-lg bg-gradient-to-r from-[#5CF2C2]/[0.06] to-[#4DA3FF]/[0.06] border border-white/[0.06] px-5 py-4 flex items-center">
            <div>
              <div className="text-[9px] font-bold text-[#5CF2C2]/50 uppercase tracking-wider mb-1.5">Outcome</div>
              <div className="text-[15px] font-semibold text-white leading-snug">
                Lower churn. Higher NRR. Clear ARR-at-risk visibility.
              </div>
            </div>
          </div>

          {/* ARR Impact Lens */}
          <div className="rounded-lg border border-dashed border-[#4DA3FF]/25 bg-[#4DA3FF]/[0.03] px-4 py-3">
            <div className="flex items-center gap-1.5 mb-2.5">
              <span className="text-[9px] font-bold text-[#4DA3FF]/70 uppercase tracking-wider">ARR Impact Lens</span>
              <span className="px-1.5 py-0.5 rounded text-[7px] font-semibold uppercase tracking-wider bg-white/5 text-[#6B7280] border border-white/[0.06]">Pilot Output</span>
            </div>
            <div className="space-y-1.5">
              {([
                ['ARR at Risk', '$___'],
                ['Modeled Save Lift', '__%'],
                ['EBITDA Sensitivity', '__x'],
              ] as const).map(([label, val]) => (
                <div key={label} className="flex items-center justify-between">
                  <span className="text-[10px] text-[#8891A0]">{label}</span>
                  <span className="text-[11px] font-mono font-semibold text-[#4DA3FF]/60 bg-[#4DA3FF]/[0.06] px-2 py-0.5 rounded">{val}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ─── Footer ─── */}
        <footer className="pt-3 border-t border-white/[0.06] flex items-center justify-between">
          <span className="text-[9px] text-[#4B5563] tracking-wide">Confidential &nbsp;·&nbsp; For internal evaluation</span>
          <span className="text-[9px] text-[#4B5563]">pickpulse.co</span>
        </footer>
      </div>
    </div>
  );
}

/* ─── Shared subcomponent ─── */

function SectionLabel({ number, title }: { number: string; title: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-bold text-[#5CF2C2]/40 font-mono">{number}</span>
      <span className="text-[13px] font-semibold text-white tracking-tight">{title}</span>
    </div>
  );
}

export default LeaveBehind;
