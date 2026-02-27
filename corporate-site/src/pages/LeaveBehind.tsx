/* ─── Inline SVG icon components (consistent 16px, 1.5 stroke) ─── */

function IconShield() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}
function IconList() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  );
}
function IconBarChart() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}
function IconCheck() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}
function IconArrowRight() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

/* ─── Data ─── */

const workflow = [
  {
    step: '1',
    title: 'Data Ingestion',
    line: 'Export from your CRM or billing system.',
    bullets: ['CSV, HubSpot, or Stripe', 'Mapped via standard template'],
  },
  {
    step: '2',
    title: 'Model Training',
    line: 'Trains on your historical churn outcomes.',
    bullets: ['Calibrated likelihood per account', 'Optional drivers and explanations'],
  },
  {
    step: '3',
    title: 'Account Prioritization',
    line: 'Ranked by ARR exposure and renewal urgency.',
    bullets: ['High / Medium / Low risk tiers', 'Actionable save list'],
  },
  {
    step: '4',
    title: 'Revenue Simulation',
    line: 'Model recoverable ARR at varying save rates.',
    bullets: ['Adjustable save assumptions', 'ARR-at-risk quantified per tier'],
  },
  {
    step: '5',
    title: 'Portfolio Roll-Up',
    line: 'Aggregate risk view across the book.',
    bullets: ['Executive summary + PDF', 'Renewal pipeline overlay'],
    optional: true,
  },
];

const timeline = [
  { week: 'Wk 1', title: 'Data Alignment', bullets: ['Template mapping', 'Field validation', 'Outcome labeling'] },
  { week: 'Wk 2', title: 'Model Training', bullets: ['Model fit + validation', 'Calibration check', 'Accuracy review'] },
  { week: 'Wk 3', title: 'Live Scoring', bullets: ['Full account scoring', 'Risk tier assignment', 'Save list delivery'] },
  { week: 'Wk 4', title: 'Impact Modeling', bullets: ['ARR-at-risk report', 'Save-rate simulation', 'Executive summary'] },
];

/* ─── Component ─── */

export function LeaveBehind() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0B0F14] to-[#0E1623] text-[#E8ECF1] print:bg-[#0B0F14]">
      <div className="max-w-[960px] mx-auto px-8 py-8 print:py-5 print:px-6">

        {/* ─── Header ─── */}
        <header className="flex items-center justify-between mb-7 print:mb-5">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[#5CF2C2] to-[#4DA3FF] flex items-center justify-center shadow-lg shadow-[#5CF2C2]/10">
              <span className="text-[#0B0F14] text-[10px] font-extrabold tracking-tight leading-none">PPI</span>
            </div>
            <div>
              <div className="text-sm font-bold tracking-tight text-white">PickPulse Intelligence</div>
              <div className="text-[9px] text-[#5CF2C2]/60 font-medium tracking-[0.18em] uppercase">Churn Risk Engine</div>
            </div>
          </div>
          <div className="px-3 py-1 rounded-full border border-[#5CF2C2]/20 bg-[#5CF2C2]/5 text-[9px] font-semibold text-[#5CF2C2] uppercase tracking-wider">
            Workflow Overview
          </div>
        </header>

        {/* ─── 1. Value Pillars ─── */}
        <section className="mb-6 print:mb-4">
          <SectionLabel number="01" title="What You Get" />
          <div className="grid grid-cols-3 gap-3 mt-2.5">
            {[
              {
                icon: <IconShield />,
                title: 'Risk Tiers',
                line: 'Calibrated churn likelihood with confidence for every account.',
                bullets: ['Not an opaque score — a real probability', 'High / Medium / Low segmentation'],
              },
              {
                icon: <IconList />,
                title: 'Prioritized Save List',
                line: 'Accounts ranked by ARR exposure and renewal urgency.',
                bullets: ['CS team knows exactly where to focus', 'Exportable to CRM or spreadsheet'],
              },
              {
                icon: <IconBarChart />,
                title: 'Executive Visibility',
                line: 'ARR-at-risk quantified with save-rate simulation.',
                bullets: ['Board-ready PDF reporting', 'Adjustable recovery assumptions'],
              },
            ].map((p, i) => (
              <div key={i} className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4 flex flex-col">
                <div className="flex items-center gap-2.5 mb-2">
                  <div className="w-7 h-7 rounded-lg bg-[#5CF2C2]/10 text-[#5CF2C2] flex items-center justify-center shrink-0">
                    {p.icon}
                  </div>
                  <span className="text-[12px] font-semibold text-white">{p.title}</span>
                </div>
                <p className="text-[10px] text-[#9CA3AF] leading-snug mb-2">{p.line}</p>
                <ul className="space-y-1 mt-auto">
                  {p.bullets.map((b, j) => (
                    <li key={j} className="text-[10px] text-[#6B7280] leading-snug flex gap-1.5 items-start">
                      <span className="text-[#5CF2C2]/50 mt-px shrink-0">›</span>{b}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        {/* ─── 2. How It Works — horizontal flow ─── */}
        <section className="mb-6 print:mb-4">
          <SectionLabel number="02" title="How It Works" />
          <div className="relative mt-3">
            {/* Progress line behind steps */}
            <div className="absolute top-[18px] left-[20px] right-[20px] h-px bg-gradient-to-r from-[#5CF2C2]/25 via-[#5CF2C2]/15 to-[#4DA3FF]/20 print:bg-[#5CF2C2]/15" />

            <div className="relative grid grid-cols-5 gap-0">
              {workflow.map((s, i) => (
                <div key={i} className="flex flex-col items-center px-1">
                  {/* Step number node */}
                  <div className={`relative z-10 w-9 h-9 rounded-full flex items-center justify-center text-[13px] font-bold mb-2.5 ${
                    s.optional
                      ? 'bg-[#0E1623] border-2 border-dashed border-[#4DA3FF]/30 text-[#4DA3FF]/70'
                      : 'bg-[#5CF2C2]/10 border-2 border-[#5CF2C2]/30 text-[#5CF2C2]'
                  }`}>
                    {s.step}
                  </div>
                  {/* Card */}
                  <div className={`w-full rounded-lg px-2.5 py-2.5 text-center ${
                    s.optional
                      ? 'border border-dashed border-[#4DA3FF]/20 bg-[#4DA3FF]/[0.03]'
                      : 'border border-white/[0.06] bg-white/[0.03]'
                  }`}>
                    <div className="flex items-center justify-center gap-1 mb-1">
                      <span className="text-[11px] font-semibold text-white leading-tight">{s.title}</span>
                      {s.optional && (
                        <span className="px-1 py-px rounded text-[7px] font-semibold uppercase tracking-wider bg-[#4DA3FF]/10 text-[#4DA3FF] border border-[#4DA3FF]/20">Opt</span>
                      )}
                    </div>
                    <p className="text-[9px] text-[#8891A0] leading-snug mb-1.5">{s.line}</p>
                    <ul className="space-y-0.5">
                      {s.bullets.map((b, j) => (
                        <li key={j} className="text-[9px] text-[#6B7280] leading-snug">
                          <span className="text-[#5CF2C2]/40">› </span>{b}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── 3. Onboarding Timeline ─── */}
        <section className="mb-5 print:mb-4">
          <div className="flex items-center gap-2.5 mb-2.5">
            <SectionLabel number="03" title="Onboarding" />
            <span className="px-2 py-0.5 rounded-full bg-[#5CF2C2]/[0.07] border border-[#5CF2C2]/15 text-[8px] font-bold text-[#5CF2C2] uppercase tracking-widest">30-Day Pilot</span>
          </div>

          <div className="relative">
            {/* Connecting line */}
            <div className="absolute top-[14px] left-[calc(12.5%+4px)] right-[calc(12.5%+4px)] h-px bg-gradient-to-r from-[#5CF2C2]/30 to-[#4DA3FF]/20" />

            <div className="relative grid grid-cols-4 gap-3">
              {timeline.map((w, i) => (
                <div key={i} className="flex flex-col items-center">
                  {/* Node dot */}
                  <div className="relative z-10 w-7 h-7 rounded-full bg-[#0E1623] border-2 border-[#5CF2C2]/30 flex items-center justify-center mb-2">
                    <span className="text-[9px] font-bold text-[#5CF2C2]/80">{w.week}</span>
                  </div>
                  {/* Card */}
                  <div className="w-full bg-white/[0.03] border border-white/[0.06] rounded-lg px-3 py-2.5">
                    <div className="text-[11px] font-semibold text-white mb-1.5">{w.title}</div>
                    <ul className="space-y-0.5">
                      {w.bullets.map((b, j) => (
                        <li key={j} className="text-[9px] text-[#8891A0] leading-snug flex gap-1 items-start">
                          <span className="text-[#5CF2C2]/40 mt-px shrink-0">›</span>{b}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── 4. Bottom: Pilot Outputs + ARR Impact ─── */}
        <div className="grid grid-cols-2 gap-3 mb-4 print:mb-3">
          {/* Pilot Outputs */}
          <div className="rounded-xl bg-white/[0.03] border border-white/[0.06] px-4 py-3">
            <div className="text-[9px] font-bold text-[#5CF2C2]/50 uppercase tracking-wider mb-2">Pilot Outputs</div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              {['Risk tiers per account', 'Prioritized save list', 'ARR-at-risk quantification', 'Executive summary PDF'].map((item, i) => (
                <div key={i} className="flex items-center gap-1.5">
                  <span className="text-[#5CF2C2]/60 shrink-0"><IconCheck /></span>
                  <span className="text-[10px] text-[#B0B8C5]">{item}</span>
                </div>
              ))}
            </div>
          </div>

          {/* ARR Impact */}
          <div className="rounded-xl border border-[#4DA3FF]/15 bg-gradient-to-br from-[#4DA3FF]/[0.04] to-[#5CF2C2]/[0.02] px-4 py-3">
            <div className="flex items-center gap-2 mb-2.5">
              <span className="text-[9px] font-bold text-[#4DA3FF]/70 uppercase tracking-wider">ARR Impact</span>
              <span className="px-1.5 py-px rounded text-[7px] font-semibold uppercase tracking-wider bg-white/[0.04] text-[#6B7280] border border-white/[0.06]">Pilot Output</span>
            </div>
            <div className="space-y-1.5">
              {([
                { label: 'ARR at Risk', value: '$___', color: 'text-[#5CF2C2]/50' },
                { label: 'Modeled Save Lift', value: '__%', color: 'text-[#5CF2C2]/50' },
                { label: 'EBITDA Sensitivity', value: '__x', color: 'text-[#4DA3FF]/50' },
              ]).map((row) => (
                <div key={row.label} className="flex items-center justify-between">
                  <span className="text-[10px] text-[#8891A0]">{row.label}</span>
                  <div className="flex items-center gap-1.5">
                    <div className="w-12 h-1 rounded-full bg-white/[0.06] overflow-hidden">
                      <div className="w-3/4 h-full rounded-full bg-gradient-to-r from-[#5CF2C2]/20 to-[#4DA3FF]/20" />
                    </div>
                    <span className={`text-[11px] font-mono font-semibold ${row.color} bg-white/[0.03] px-2 py-0.5 rounded`}>{row.value}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ─── CTA ─── */}
        <div className="rounded-xl bg-gradient-to-r from-[#5CF2C2]/[0.06] to-[#4DA3FF]/[0.04] border border-[#5CF2C2]/10 px-5 py-3 flex items-center justify-between mb-4 print:mb-3">
          <div>
            <div className="text-[12px] font-semibold text-white">Next step</div>
            <div className="text-[10px] text-[#9CA3AF] mt-0.5">15-min working session to confirm data sources and deliver a pilot plan.</div>
          </div>
          <div className="flex items-center gap-1.5 text-[#5CF2C2]/70 shrink-0">
            <IconArrowRight />
          </div>
        </div>

        {/* ─── Footer ─── */}
        <footer className="pt-2.5 border-t border-white/[0.05] flex items-center justify-between">
          <span className="text-[8px] text-[#4B5563] tracking-wide">Confidential &nbsp;&middot;&nbsp; For internal evaluation</span>
          <span className="text-[8px] text-[#4B5563]">pickpulse.co</span>
        </footer>
      </div>
    </div>
  );
}

/* ─── Shared ─── */

function SectionLabel({ number, title }: { number: string; title: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[9px] font-bold text-[#5CF2C2]/35 font-mono">{number}</span>
      <span className="text-[12px] font-semibold text-white tracking-tight">{title}</span>
    </div>
  );
}

export default LeaveBehind;
