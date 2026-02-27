export function LeaveBehind() {
  return (
    <div className="min-h-screen bg-[#0B0F14] flex items-center justify-center">
      <div
        className="bg-[#0B0F14] flex flex-col overflow-hidden print:px-12 print:py-12"
        style={{
          width: 816,
          height: 1056,
          padding: '48px 60px 28px',
          fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
        }}
      >
        {/* Brand */}
        <div className="flex items-center gap-3 mb-16">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
            style={{ background: 'linear-gradient(135deg, #5CF2C2, #4DA3FF)' }}
          >
            <span className="text-[#0B0F14] text-[9px] font-extrabold">PPI</span>
          </div>
          <span className="text-[13px] font-semibold text-white tracking-tight">
            PickPulse Intelligence
          </span>
        </div>

        {/* COMMAND */}
        <div className="text-center mb-8">
          <div className="text-5xl font-extrabold leading-[1.05] tracking-tight text-white">
            Know which accounts are at risk.
          </div>
          <div className="text-5xl font-extrabold leading-[1.05] tracking-tight text-white mt-2">
            Act before they churn.
          </div>
        </div>

        <p className="text-lg text-white/70 mt-4 mb-10 text-center">
          PickPulse ranks every account by calibrated churn probability and ARR exposure.
        </p>

        {/* OPERATING FLOW */}
        <div className="mb-16 print:mb-12">
          {/* Line + dots */}
          <div className="relative mb-4">
            <div className="absolute top-1/2 left-[10%] right-[10%] h-[2px] -translate-y-1/2" style={{ background: 'rgba(92,242,194,0.12)' }} />
            <div className="relative grid grid-cols-5">
              {[0, 1, 2, 3, 4].map((i) => (
                <div key={i} className="flex justify-center">
                  <div className="w-[10px] h-[10px] rounded-full" style={{ background: '#5CF2C2', opacity: 0.35, boxShadow: '0 0 8px rgba(92,242,194,0.2)' }} />
                </div>
              ))}
            </div>
          </div>

          {/* Steps */}
          <div className="grid grid-cols-5 gap-6 items-start print:gap-4">
            <FlowStep title="DATA" sub="CRM or billing export" />
            <FlowStep title="TRAIN" sub="Learns churn patterns" />
            <FlowStep title="SCORE" sub="Calibrated probability" />
            <FlowStep title="RANK" sub="Ranked by ARR + urgency" />
            <FlowStep title="REPORT" sub="ARR-at-risk + exec summary" />
          </div>
        </div>

        {/* OUTPUT */}
        <div className="flex gap-12 flex-1">
          <div className="flex-1 pt-1">
            <div className="text-[10px] font-bold text-[#4B5563] tracking-[0.14em] uppercase mb-5">
              Pilot Outputs
            </div>
            <div className="flex flex-col gap-4">
              <OutputItem text="Risk tiers per account" />
              <OutputItem text="Prioritized save list" />
              <OutputItem text="ARR-at-risk summary" />
              <OutputItem text="Executive PDF" />
            </div>
          </div>

          <div className="flex-1 flex items-center justify-end">
            <div className="text-3xl font-bold text-white leading-tight text-right mt-12 mb-6">
              Lower churn.
              <br />
              Higher NRR.
              <br />
              <span className="text-[#5CF2C2]">Clear ARR visibility.</span>
            </div>
          </div>
        </div>

        {/* ACTION */}
        <div className="text-center mt-6" style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 20 }}>
          <div className="font-semibold text-white">
            Next step <span className="text-[#5CF2C2]/50 mx-2">&rarr;</span> 15-min working session
          </div>
          <div className="text-white/60 text-sm mt-1">
            Confirm data sources and deliver pilot plan.
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-between mt-4 pt-2">
          <span className="text-[8px] text-[#2D333B] tracking-wide">Confidential &middot; For internal evaluation</span>
          <span className="text-[8px] text-[#2D333B]">pickpulse.co</span>
        </div>
      </div>
    </div>
  );
}

function FlowStep({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="min-w-0 flex flex-col items-center text-center">
      <div className="text-sm font-extrabold tracking-[0.2em] text-white whitespace-nowrap">
        {title}
      </div>
      <div className="text-sm text-white/70 leading-snug mt-2 max-w-[9rem]">
        {sub}
      </div>
    </div>
  );
}

function OutputItem({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-3">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#5CF2C2" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.45, flexShrink: 0 }}>
        <polyline points="20 6 9 17 4 12" />
      </svg>
      <span className="text-sm text-[#9CA3AF] font-medium">{text}</span>
    </div>
  );
}

export default LeaveBehind;
