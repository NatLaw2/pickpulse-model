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
        className="print:!p-10"
        style={{
          width: 816,
          height: 1056,
          background: '#0B0F14',
          fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
          display: 'flex',
          flexDirection: 'column',
          padding: '48px 60px 28px',
          overflow: 'hidden',
        }}
      >
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 64 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #5CF2C2, #4DA3FF)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <span style={{ color: '#0B0F14', fontSize: 9, fontWeight: 800 }}>PPI</span>
          </div>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#FFFFFF', letterSpacing: '-0.01em' }}>
            PickPulse Intelligence
          </span>
        </div>

        {/* ── COMMAND ── */}
        <div style={{ textAlign: 'center', marginBottom: 72 }}>
          <h1
            style={{
              fontSize: 46,
              fontWeight: 800,
              color: '#FFFFFF',
              lineHeight: 1.08,
              letterSpacing: '-0.035em',
              margin: 0,
            }}
          >
            <span style={{ display: 'block' }}>Know which accounts are at risk.</span>
            <span style={{ display: 'block', marginTop: 4 }}>Act before they churn.</span>
          </h1>
          <p
            className="print:!text-[13px]"
            style={{ fontSize: 16, color: '#6B7280', marginTop: 20, lineHeight: 1.5 }}
          >
            PickPulse ranks every account by calibrated churn probability and ARR exposure.
          </p>
        </div>

        {/* ── OPERATING FLOW ── */}
        <div className="print:!mb-14" style={{ marginBottom: 72 }}>
          {/* Flow line + dots */}
          <div style={{ position: 'relative', marginBottom: 14 }}>
            {/* Horizontal line */}
            <div
              style={{
                position: 'absolute',
                top: '50%',
                left: '10%',
                right: '10%',
                height: 2,
                background: 'rgba(92,242,194,0.12)',
                transform: 'translateY(-50%)',
              }}
            />
            {/* Dots */}
            <div
              style={{
                position: 'relative',
                display: 'grid',
                gridTemplateColumns: 'repeat(5, 1fr)',
              }}
            >
              {[0, 1, 2, 3, 4].map((i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'center' }}>
                  <div
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      background: '#5CF2C2',
                      opacity: 0.35,
                      boxShadow: '0 0 8px rgba(92,242,194,0.2)',
                    }}
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Step labels */}
          <div
            className="print:!gap-4"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(5, 1fr)',
              gap: 24,
            }}
          >
            <FlowStep title="DATA" sub="CRM or billing export" />
            <FlowStep title="TRAIN" sub="Learns churn patterns" />
            <FlowStep title="SCORE" sub="Calibrated probability" />
            <FlowStep title="RANK" sub="Ranked by ARR + urgency" />
            <FlowStep title="REPORT" sub="ARR-at-risk + exec summary" />
          </div>
        </div>

        {/* ── OUTPUT ── */}
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

        {/* ── ACTION ── */}
        <div
          style={{
            textAlign: 'center',
            paddingTop: 24,
            borderTop: '1px solid rgba(255,255,255,0.06)',
            marginTop: 24,
          }}
        >
          <p style={{ fontSize: 15, color: '#FFFFFF', margin: 0, fontWeight: 600 }}>
            Next step
            <span style={{ color: '#5CF2C2', margin: '0 10px', opacity: 0.5 }}>&rarr;</span>
            <span style={{ fontWeight: 600 }}>15-min working session</span>
          </p>
          <p
            className="print:!text-[12px]"
            style={{ fontSize: 13, color: '#6B7280', margin: '6px 0 0', fontWeight: 400 }}
          >
            Confirm data sources and deliver pilot plan.
          </p>
        </div>

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginTop: 16,
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
    <div style={{ textAlign: 'center', minWidth: 0 }}>
      <div
        style={{
          fontSize: 22,
          fontWeight: 800,
          color: '#FFFFFF',
          letterSpacing: '0.06em',
          marginBottom: 6,
          whiteSpace: 'nowrap' as const,
        }}
      >
        {title}
      </div>
      <div
        className="print:!text-[10px]"
        style={{
          fontSize: 11,
          color: '#6B7280',
          lineHeight: 1.4,
          maxWidth: 130,
          margin: '0 auto',
        }}
      >
        {sub}
      </div>
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
