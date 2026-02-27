export function LeaveBehind() {
  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#0C1017',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          width: 816,
          height: 1056,
          background: '#0C1017',
          fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
          color: '#D0D4DB',
          display: 'flex',
          flexDirection: 'column',
          padding: '56px 64px 36px',
          overflow: 'hidden',
        }}
      >
        {/* ── Brand mark ── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 56 }}>
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #5CF2C2, #4DA3FF)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <span style={{ color: '#0C1017', fontSize: 10, fontWeight: 800, letterSpacing: '-0.03em' }}>PPI</span>
          </div>
          <span style={{ fontSize: 14, fontWeight: 600, color: '#FFFFFF', letterSpacing: '-0.01em' }}>
            PickPulse Intelligence
          </span>
        </div>

        {/* ═══════════════════════════════════════════════
            SECTION 1 — COMMAND
        ═══════════════════════════════════════════════ */}
        <div style={{ textAlign: 'center', marginBottom: 64 }}>
          <h1
            style={{
              fontSize: 36,
              fontWeight: 800,
              color: '#FFFFFF',
              lineHeight: 1.15,
              letterSpacing: '-0.025em',
              margin: 0,
            }}
          >
            Know which accounts are at risk.
            <br />
            Act before they churn.
          </h1>
          <p style={{ fontSize: 15, color: '#7B8494', marginTop: 18, lineHeight: 1.5 }}>
            PickPulse ranks every account by calibrated churn probability and ARR exposure.
          </p>
        </div>

        {/* ═══════════════════════════════════════════════
            SECTION 2 — THE OPERATING FLOW
        ═══════════════════════════════════════════════ */}
        <div style={{ marginBottom: 64 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'center',
              gap: 0,
            }}
          >
            <FlowStep title="Data" sub="CRM or billing export" />
            <FlowArrow />
            <FlowStep title="Train" sub="Learns churn patterns" />
            <FlowArrow />
            <FlowStep title="Score" sub="Calibrated probability per account" />
            <FlowArrow />
            <FlowStep title="Prioritize" sub="Ranked by ARR + urgency" />
            <FlowArrow />
            <FlowStep title="Report" sub="ARR-at-risk + exec summary" />
          </div>
        </div>

        {/* ═══════════════════════════════════════════════
            SECTION 3 — OUTPUT
        ═══════════════════════════════════════════════ */}
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', gap: 48 }}>
            {/* Left — Pilot Outputs */}
            <div style={{ flex: 1 }}>
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: '#565E6C',
                  letterSpacing: '0.12em',
                  textTransform: 'uppercase' as const,
                  marginBottom: 18,
                }}
              >
                Pilot Outputs
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <OutputItem text="Risk tiers per account" />
                <OutputItem text="Prioritized save list" />
                <OutputItem text="ARR-at-risk summary" />
                <OutputItem text="Executive PDF" />
              </div>
            </div>

            {/* Right — Outcome headline */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <h2
                style={{
                  fontSize: 28,
                  fontWeight: 700,
                  color: '#FFFFFF',
                  lineHeight: 1.2,
                  letterSpacing: '-0.02em',
                  margin: 0,
                }}
              >
                Lower churn. Higher NRR.
                <br />
                Clear ARR visibility.
              </h2>
            </div>
          </div>
        </div>

        {/* ═══════════════════════════════════════════════
            SECTION 4 — ACTION
        ═══════════════════════════════════════════════ */}
        <div
          style={{
            textAlign: 'center',
            paddingTop: 24,
            borderTop: '1px solid rgba(255,255,255,0.06)',
            marginTop: 24,
          }}
        >
          <p style={{ fontSize: 13, color: '#7B8494', margin: 0 }}>
            <span style={{ color: '#5CF2C2', opacity: 0.6, marginRight: 8 }}>Next step</span>
            <span style={{ color: '#565E6C', marginRight: 8 }}>&rarr;</span>
            15-min working session to confirm data and deliver pilot plan.
          </p>
        </div>

        {/* ── Footer ── */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginTop: 20,
            paddingTop: 12,
          }}
        >
          <span style={{ fontSize: 9, color: '#2D333B', letterSpacing: '0.04em' }}>
            Confidential &middot; For internal evaluation
          </span>
          <span style={{ fontSize: 9, color: '#2D333B' }}>pickpulse.co</span>
        </div>
      </div>
    </div>
  );
}

/* ── Flow step ── */
function FlowStep({ title, sub }: { title: string; sub: string }) {
  return (
    <div style={{ flex: 1, textAlign: 'center', minWidth: 0 }}>
      <div
        style={{
          fontSize: 20,
          fontWeight: 700,
          color: '#FFFFFF',
          letterSpacing: '-0.01em',
          marginBottom: 6,
        }}
      >
        {title}
      </div>
      <div style={{ fontSize: 11, color: '#7B8494', lineHeight: 1.4 }}>{sub}</div>
    </div>
  );
}

/* ── Flow arrow ── */
function FlowArrow() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', paddingTop: 4, paddingLeft: 4, paddingRight: 4 }}>
      <svg width="28" height="12" viewBox="0 0 28 12" fill="none">
        <path
          d="M0 6h24M21 2l5 4-5 4"
          stroke="#5CF2C2"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.3"
        />
      </svg>
    </div>
  );
}

/* ── Output check item ── */
function OutputItem({ text }: { text: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#5CF2C2" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.4, flexShrink: 0 }}>
        <polyline points="20 6 9 17 4 12" />
      </svg>
      <span style={{ fontSize: 14, color: '#A0A8B4' }}>{text}</span>
    </div>
  );
}

export default LeaveBehind;
