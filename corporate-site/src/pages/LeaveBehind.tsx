function IconShield() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}
function IconList() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  );
}
function IconBarChart() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}
function IconCheck() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}
function IconArrowRight() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

export function LeaveBehind() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0B0F14] to-[#0E1623] text-[#E8ECF1] print:bg-[#0B0F14]">
      <div className="max-w-[940px] mx-auto px-10 py-9 print:py-6 print:px-8">

        {/* Header */}
        <header className="flex items-center justify-between mb-9 print:mb-7">
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#5CF2C2] to-[#4DA3FF] flex items-center justify-center shadow-lg shadow-[#5CF2C2]/10">
              <span className="text-[#0B0F14] text-[11px] font-extrabold tracking-tight leading-none">PPI</span>
            </div>
            <div>
              <div className="text-[15px] font-bold tracking-tight text-white">PickPulse Intelligence</div>
              <div className="text-[10px] text-[#5CF2C2]/50 font-medium tracking-[0.2em] uppercase">Churn Risk Engine</div>
            </div>
          </div>
          <div className="px-3.5 py-1 rounded-full border border-[#5CF2C2]/15 bg-[#5CF2C2]/[0.04] text-[9px] font-semibold text-[#5CF2C2]/70 uppercase tracking-widest">
            Workflow Overview
          </div>
        </header>

        {/* 01 — What You Get */}
        <section className="mb-8 print:mb-6">
          <Label n="01" t="What You Get" />
          <div className="grid grid-cols-3 gap-4 mt-3">
            {[
              {
                icon: <IconShield />,
                title: 'Risk Tiers',
                line: 'Calibrated churn probability for every account.',
                bullets: ['Real percentage, not an opaque score', 'High / Medium / Low segmentation'],
              },
              {
                icon: <IconList />,
                title: 'Prioritized Save List',
                line: 'Accounts ranked by revenue at risk.',
                bullets: ['Sorted by ARR and renewal urgency', 'Exportable to CRM or spreadsheet'],
              },
              {
                icon: <IconBarChart />,
                title: 'Executive Visibility',
                line: 'ARR-at-risk with recovery simulation.',
                bullets: ['Board-ready PDF reporting', 'Adjustable save-rate assumptions'],
              },
            ].map((p, i) => (
              <div key={i} className="py-4 px-1">
                <div className="flex items-center gap-2.5 mb-2">
                  <div className="w-8 h-8 rounded-lg bg-[#5CF2C2]/[0.08] text-[#5CF2C2] flex items-center justify-center">{p.icon}</div>
                  <span className="text-[13px] font-semibold text-white">{p.title}</span>
                </div>
                <p className="text-[11px] text-[#9CA3AF] leading-relaxed mb-2">{p.line}</p>
                <ul className="space-y-1">
                  {p.bullets.map((b, j) => (
                    <li key={j} className="text-[11px] text-[#6B7280] flex gap-2 items-start">
                      <span className="text-[#5CF2C2]/40 mt-px">›</span>{b}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        {/* 02 — How It Works */}
        <section className="mb-8 print:mb-6">
          <Label n="02" t="How It Works" />
          <div className="relative mt-4">
            <div className="absolute top-[19px] left-[40px] right-[40px] h-px bg-gradient-to-r from-[#5CF2C2]/20 via-[#5CF2C2]/10 to-[#4DA3FF]/15" />
            <div className="relative grid grid-cols-5 gap-1">
              {[
                { s: '1', title: 'Data Ingestion', line: 'CRM or billing export via template.', bullets: ['CSV, HubSpot, or Stripe'] },
                { s: '2', title: 'Model Training', line: 'Trains on your historical outcomes.', bullets: ['Calibrated likelihood per account'] },
                { s: '3', title: 'Prioritization', line: 'Ranked by revenue and urgency.', bullets: ['Actionable save list by tier'] },
                { s: '4', title: 'Impact Simulation', line: 'Recoverable ARR at varying save rates.', bullets: ['ARR-at-risk quantified per tier'] },
                { s: '5', title: 'Portfolio View', line: 'Aggregate risk across the book.', bullets: ['Executive summary + PDF'], opt: true },
              ].map((step, i) => (
                <div key={i} className="flex flex-col items-center text-center px-1">
                  <div className={`relative z-10 w-[38px] h-[38px] rounded-full flex items-center justify-center text-[14px] font-bold mb-3 ${
                    step.opt
                      ? 'bg-[#0E1623] border-[1.5px] border-dashed border-[#4DA3FF]/25 text-[#4DA3FF]/60'
                      : 'bg-[#0E1623] border-[1.5px] border-[#5CF2C2]/25 text-[#5CF2C2]'
                  }`}>
                    {step.s}
                  </div>
                  <div className="flex items-center justify-center gap-1 mb-1">
                    <span className="text-[11px] font-semibold text-white">{step.title}</span>
                    {step.opt && <span className="px-1 py-px rounded text-[7px] font-semibold uppercase tracking-wider text-[#4DA3FF]/60 bg-[#4DA3FF]/[0.06]">Opt</span>}
                  </div>
                  <p className="text-[10px] text-[#8891A0] leading-snug mb-1">{step.line}</p>
                  {step.bullets.map((b, j) => (
                    <span key={j} className="text-[10px] text-[#6B7280]"><span className="text-[#5CF2C2]/30">› </span>{b}</span>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* 03 — Onboarding */}
        <section className="mb-8 print:mb-6">
          <div className="flex items-center gap-2.5">
            <Label n="03" t="Onboarding" />
            <span className="px-2.5 py-0.5 rounded-full bg-[#5CF2C2]/[0.05] border border-[#5CF2C2]/10 text-[8px] font-bold text-[#5CF2C2]/60 uppercase tracking-[0.15em]">30-Day Pilot</span>
          </div>
          <div className="relative mt-4">
            <div className="absolute top-[14px] left-[calc(12.5%)] right-[calc(12.5%)] h-px bg-gradient-to-r from-[#5CF2C2]/25 to-[#4DA3FF]/15" />
            <div className="relative grid grid-cols-4 gap-4">
              {[
                { wk: 'Wk 1', title: 'Data Alignment', bullets: ['Template mapping', 'Field validation'] },
                { wk: 'Wk 2', title: 'Model Training', bullets: ['Model fit and calibration', 'Accuracy review'] },
                { wk: 'Wk 3', title: 'Live Scoring', bullets: ['Full account scoring', 'Save list delivery'] },
                { wk: 'Wk 4', title: 'Impact Modeling', bullets: ['ARR-at-risk report', 'Executive summary'] },
              ].map((w, i) => (
                <div key={i} className="flex flex-col items-center">
                  <div className="relative z-10 w-7 h-7 rounded-full bg-[#0E1623] border-[1.5px] border-[#5CF2C2]/25 flex items-center justify-center mb-2.5">
                    <span className="text-[8px] font-bold text-[#5CF2C2]/70">{w.wk}</span>
                  </div>
                  <div className="w-full px-1">
                    <div className="text-[12px] font-semibold text-white mb-1.5 text-center">{w.title}</div>
                    <ul className="space-y-1">
                      {w.bullets.map((b, j) => (
                        <li key={j} className="text-[10px] text-[#8891A0] flex gap-1.5 items-start">
                          <span className="text-[#5CF2C2]/30 mt-px shrink-0">›</span>{b}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Bottom — Outputs + Outcome */}
        <div className="grid grid-cols-2 gap-5 mb-6 print:mb-4">
          <div>
            <div className="text-[10px] font-bold text-[#5CF2C2]/40 uppercase tracking-wider mb-3">Pilot Outputs</div>
            <div className="space-y-2">
              {['Risk tiers per account', 'Prioritized save list', 'ARR-at-risk quantification', 'Executive summary PDF'].map((item) => (
                <div key={item} className="flex items-center gap-2.5">
                  <span className="text-[#5CF2C2]/50"><IconCheck /></span>
                  <span className="text-[12px] text-[#B0B8C5]">{item}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="flex flex-col justify-center">
            <p className="text-[17px] font-semibold text-white leading-snug mb-3">
              Lower churn. Higher NRR.<br />Clear ARR visibility.
            </p>
            <div className="flex items-center gap-2 text-[#9CA3AF]">
              <span className="text-[#5CF2C2]/50"><IconArrowRight /></span>
              <span className="text-[11px]">Next step: 15-min working session to confirm data sources and deliver pilot plan.</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <footer className="pt-3 border-t border-white/[0.04] flex items-center justify-between">
          <span className="text-[8px] text-[#4B5563] tracking-wide">Confidential &middot; For internal evaluation</span>
          <span className="text-[8px] text-[#4B5563]">pickpulse.co</span>
        </footer>
      </div>
    </div>
  );
}

function Label({ n, t }: { n: string; t: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-bold text-[#5CF2C2]/30 font-mono">{n}</span>
      <span className="text-[13px] font-semibold text-white tracking-tight">{t}</span>
    </div>
  );
}

export default LeaveBehind;
