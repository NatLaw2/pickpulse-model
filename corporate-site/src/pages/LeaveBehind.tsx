export function LeaveBehind() {
  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#0B0F14',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          width: 816,
          height: 1056,
          background: '#0B0F14',
          fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
          display: 'flex',
          flexDirection: 'column',
          padding: '52px 64px 32px',
          overflow: 'hidden',
        }}
      >
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 72 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #5CF2C2, #4DA3FF)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <span style={{ color: '#0B0F14', fontSize: 9, fontWeight: 800 }}>PPI</span>
          </div>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#FFFFFF', letterSpacing: '-0.01em' }}>
            PickPulse Intelligence
          </span>
        </div>

        {/* COMMAND */}
        <div style={{ textAlign: 'center', marginBottom: 80 }}>
          <h1
            style={{
              fontSize: 44,
              fontWeight: 800,
              color: '#FFFFFF',
              lineHeight: 1.1,
              letterSpacing: '-0.03em',
              margin: 0,
            }}
          >
            Know which accounts are at risk.
            <br />
            Act before they churn.
          </h1>
          <p style={{ fontSize: 15, color: '#6B7280', marginTop: 24, lineHeight: 1.5 }}>
            PickPulse ranks every account by calibrated churn probability and ARR exposure.
          </p>
        </div>

        {/* OPERATING FLOW */}
        <div style={{ marginBottom: 80 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'center' }}>
            <FlowStep title="DATA" sub="CRM or billing export" />
            <FlowArrow />
            <FlowStep title="TRAIN" sub="Learns churn patterns" />
            <FlowArrow />
            <FlowStep title="SCORE" sub="Calibrated probability" />
            <FlowArrow />
            <FlowStep title="PRIORITIZE" sub="Ranked by ARR + urgency" />
            <FlowArrow />
            <FlowStep title="REPORT" sub="ARR-at-risk + exec summary" />
          </div>
        </div>

        {/* OUTPUT */}
        <div style={{ display: 'flex', gap: 48, flex: 1 }}>
          <div style={{ flex: 1, paddingTop: 4 }}>
            <div
              style={{
                fontSize: 10,
                fontWeight: 700,
                color: '#4B5563',
                letterSpacing: '0.14em',
                textTransform: 'uppercase' as const,
                marginBottom: 22,
              }}
            >
              Pilot Outputs
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <OutputItem text="Risk tiers per account" />
              <OutputItem text="Prioritized save list" />
              <OutputItem text="ARR-at-risk summary" />
              <OutputItem text="Executive PDF" />
            </div>
          </div>

          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <h2
              style={{
                fontSize: 34,
                fontWeight: 800,
                color: '#FFFFFF',
                lineHeight: 1.15,
                letterSpacing: '-0.025em',
                margin: 0,
                textAlign: 'right',
              }}
            >
              Lower churn.
              <br />
              Higher NRR.
              <br />
              <span style={{ color: '#5CF2C2' }}>Clear ARR visibility.</span>
            </h2>
          </div>
        </div>

        {/* ACTION */}
        <div
          style={{
            textAlign: 'center',
            paddingTop: 28,
            borderTop: '1px solid rgba(255,255,255,0.06)',
            marginTop: 28,
          }}
        >
          <p style={{ fontSize: 14, color: '#6B7280', margin: 0, fontWeight: 500 }}>
            <span style={{ color: '#5CF2C2', marginRight: 10, fontWeight: 600 }}>Next step</span>
            <span style={{ marginRight: 10, opacity: 0.4 }}>&rarr;</span>
            15-min working session to confirm data and deliver pilot plan.
          </p>
        </div>

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginTop: 18,
            paddingTop: 10,
          }}
        >
          <span style={{ fontSize: 8, color: '#2D333B', letterSpacing: '0.05em' }}>
            Confidential &middot; For internal evaluation
          </span>
          <span style={{ fontSize: 8, color: '#2D333B' }}>pickpulse.co</span>
        </div>
      </div>
    </div>
  );
}

function FlowStep({ title, sub }: { title: string; sub: string }) {
  return (
    <div style={{ flex: 1, textAlign: 'center', minWidth: 0 }}>
      <div
        style={{
          fontSize: 24,
          fontWeight: 800,
          color: '#FFFFFF',
          letterSpacing: '0.04em',
          marginBottom: 8,
        }}
      >
        {title}
      </div>
      <div style={{ fontSize: 11, color: '#6B7280', lineHeight: 1.4 }}>{sub}</div>
    </div>
  );
}

function FlowArrow() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', paddingTop: 6, paddingLeft: 2, paddingRight: 2 }}>
      <svg width="32" height="14" viewBox="0 0 32 14" fill="none">
        <path
          d="M0 7h27M24 3l5 4-5 4"
          stroke="#5CF2C2"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.45"
        />
      </svg>
    </div>
  );
}

function OutputItem({ text }: { text: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#5CF2C2" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.45, flexShrink: 0 }}>
        <polyline points="20 6 9 17 4 12" />
      </svg>
      <span style={{ fontSize: 14, color: '#9CA3AF', fontWeight: 500 }}>{text}</span>
    </div>
  );
}

export default LeaveBehind;
