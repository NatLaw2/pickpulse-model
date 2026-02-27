export function LeaveBehind() {
  return (
    <div
      className="flex items-center justify-center bg-[#0C1017]"
      style={{ minHeight: '100vh' }}
    >
      {/* Fixed page container — letter-ish proportions, never overflows */}
      <div
        className="bg-[#0C1017] text-[#D6DAE0] overflow-hidden"
        style={{
          width: '816px',
          height: '1056px',
          padding: '52px 56px 40px',
          fontFamily: 'Inter, system-ui, sans-serif',
        }}
      >
        {/* ── Header ── */}
        <div className="flex items-center justify-between" style={{ marginBottom: 40 }}>
          <div className="flex items-center" style={{ gap: 14 }}>
            <div
              className="flex items-center justify-center rounded-full"
              style={{
                width: 40,
                height: 40,
                background: 'linear-gradient(135deg, #5CF2C2, #4DA3FF)',
              }}
            >
              <span style={{ color: '#0C1017', fontSize: 11, fontWeight: 800, letterSpacing: '-0.02em' }}>PPI</span>
            </div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 700, color: '#FFFFFF', letterSpacing: '-0.01em' }}>
                PickPulse Intelligence
              </div>
              <div style={{ fontSize: 10, fontWeight: 500, color: '#5CF2C2', letterSpacing: '0.18em', textTransform: 'uppercase' as const, opacity: 0.5 }}>
                Churn Risk Engine
              </div>
            </div>
          </div>
          <div
            className="rounded-full"
            style={{
              padding: '5px 14px',
              border: '1px solid rgba(255,255,255,0.08)',
              fontSize: 9,
              fontWeight: 500,
              color: '#6B7280',
              letterSpacing: '0.12em',
              textTransform: 'uppercase' as const,
            }}
          >
            Executive Overview
          </div>
        </div>

        {/* ── Tagline ── */}
        <div style={{ marginBottom: 36 }}>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: '#FFFFFF', lineHeight: 1.2, letterSpacing: '-0.02em', margin: 0 }}>
            Know which accounts are at risk.<br />Act before they churn.
          </h1>
          <p style={{ fontSize: 13, color: '#7B8494', marginTop: 10, lineHeight: 1.5, maxWidth: 520 }}>
            PickPulse trains a model on your historical churn data and scores every current account with a calibrated churn probability, ranked by ARR exposure.
          </p>
        </div>

        {/* ── What You Get — 3 pillars ── */}
        <div style={{ marginBottom: 36 }}>
          <SectionHead text="What You Get" />
          <div className="flex" style={{ gap: 20, marginTop: 14 }}>
            <Pillar
              icon={<ShieldIcon />}
              title="Risk Tiers"
              body="Every account scored with a real churn probability."
              bullets={['High / Medium / Low segmentation', 'Calibrated, not an opaque index']}
            />
            <Pillar
              icon={<ListIcon />}
              title="Prioritized Save List"
              body="Ranked by ARR at risk and renewal urgency."
              bullets={['Your CS team knows where to focus', 'Exportable to CRM']}
            />
            <Pillar
              icon={<ChartIcon />}
              title="Executive Reporting"
              body="ARR-at-risk quantified with recovery modeling."
              bullets={['Board-ready PDF', 'Adjustable save-rate simulation']}
            />
          </div>
        </div>

        {/* ── How It Works — 5 steps ── */}
        <div style={{ marginBottom: 36 }}>
          <SectionHead text="How It Works" />
          <div className="flex items-start" style={{ gap: 0, marginTop: 16 }}>
            <Step n="1" title="Ingest" desc="Export from CRM or billing system." />
            <Arrow />
            <Step n="2" title="Train" desc="Model learns from your churn outcomes." />
            <Arrow />
            <Step n="3" title="Score" desc="Every account gets a risk probability." />
            <Arrow />
            <Step n="4" title="Prioritize" desc="Ranked by ARR and renewal urgency." />
            <Arrow />
            <Step n="5" title="Report" desc="Executive summary and save list." last />
          </div>
        </div>

        {/* ── Onboarding — 4 weeks ── */}
        <div style={{ marginBottom: 36 }}>
          <div className="flex items-center" style={{ gap: 10 }}>
            <SectionHead text="Onboarding" />
            <span
              className="rounded-full"
              style={{
                padding: '3px 10px',
                border: '1px solid rgba(92,242,194,0.15)',
                fontSize: 8,
                fontWeight: 600,
                color: '#5CF2C2',
                letterSpacing: '0.1em',
                textTransform: 'uppercase' as const,
                opacity: 0.7,
              }}
            >
              30-Day Pilot
            </span>
          </div>
          <div className="flex" style={{ gap: 16, marginTop: 14 }}>
            <WeekCard week="Week 1" title="Data Alignment" items={['Template mapping', 'Field validation']} />
            <WeekCard week="Week 2" title="Model Training" items={['Train and calibrate', 'Accuracy review']} />
            <WeekCard week="Week 3" title="Live Scoring" items={['Score all accounts', 'Deliver save list']} />
            <WeekCard week="Week 4" title="Impact Report" items={['ARR-at-risk analysis', 'Executive summary']} />
          </div>
        </div>

        {/* ── Bottom — Outcome + CTA ── */}
        <div
          className="rounded-xl"
          style={{
            padding: '20px 28px',
            background: 'linear-gradient(135deg, rgba(92,242,194,0.06), rgba(77,163,255,0.04))',
            border: '1px solid rgba(255,255,255,0.06)',
            marginBottom: 28,
          }}
        >
          <div className="flex items-center justify-between">
            <div>
              <div style={{ fontSize: 20, fontWeight: 700, color: '#FFFFFF', letterSpacing: '-0.01em', lineHeight: 1.3 }}>
                Lower churn. Higher NRR. Clear ARR visibility.
              </div>
              <div style={{ fontSize: 12, color: '#7B8494', marginTop: 6 }}>
                Next step: 15-min working session to confirm data sources and deliver a pilot plan.
              </div>
            </div>
            <div
              className="flex items-center justify-center rounded-full"
              style={{
                width: 36,
                height: 36,
                border: '1.5px solid rgba(92,242,194,0.2)',
                flexShrink: 0,
                marginLeft: 24,
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#5CF2C2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.6 }}>
                <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
              </svg>
            </div>
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="flex items-center justify-between" style={{ borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: 12 }}>
          <span style={{ fontSize: 9, color: '#3D4452', letterSpacing: '0.04em' }}>Confidential &middot; For internal evaluation</span>
          <span style={{ fontSize: 9, color: '#3D4452' }}>pickpulse.co</span>
        </div>
      </div>
    </div>
  );
}

/* ── Sub-components ── */

function SectionHead({ text }: { text: string }) {
  return (
    <div style={{ fontSize: 13, fontWeight: 700, color: '#FFFFFF', letterSpacing: '-0.01em', textTransform: 'uppercase' as const }}>
      {text}
    </div>
  );
}

function Pillar({ icon, title, body, bullets }: { icon: React.ReactNode; title: string; body: string; bullets: string[] }) {
  return (
    <div
      className="rounded-xl"
      style={{
        flex: 1,
        padding: '18px 18px 16px',
        border: '1px solid rgba(255,255,255,0.06)',
        background: 'rgba(255,255,255,0.02)',
      }}
    >
      <div className="flex items-center" style={{ gap: 10, marginBottom: 10 }}>
        <div
          className="flex items-center justify-center rounded-lg"
          style={{ width: 32, height: 32, background: 'rgba(92,242,194,0.08)' }}
        >
          {icon}
        </div>
        <span style={{ fontSize: 14, fontWeight: 600, color: '#F1F3F5' }}>{title}</span>
      </div>
      <p style={{ fontSize: 11, color: '#7B8494', lineHeight: 1.5, margin: '0 0 8px' }}>{body}</p>
      {bullets.map((b, i) => (
        <div key={i} style={{ fontSize: 11, color: '#565E6C', lineHeight: 1.6 }}>
          <span style={{ color: 'rgba(92,242,194,0.35)', marginRight: 6 }}>&rsaquo;</span>{b}
        </div>
      ))}
    </div>
  );
}

function Step({ n, title, desc }: { n: string; title: string; desc: string; last?: boolean }) {
  return (
    <div className="flex flex-col items-center text-center" style={{ flex: 1, minWidth: 0 }}>
      <div
        className="flex items-center justify-center rounded-full"
        style={{
          width: 36,
          height: 36,
          border: n === '5' ? '1.5px dashed rgba(255,255,255,0.1)' : '1.5px solid rgba(92,242,194,0.2)',
          color: n === '5' ? '#6B7280' : '#5CF2C2',
          fontSize: 15,
          fontWeight: 700,
          marginBottom: 8,
          background: '#0C1017',
        }}
      >
        {n}
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, color: '#F1F3F5', marginBottom: 3 }}>{title}</div>
      <div style={{ fontSize: 10, color: '#7B8494', lineHeight: 1.4, maxWidth: 120 }}>{desc}</div>
    </div>
  );
}

function Arrow() {
  return (
    <div className="flex items-center" style={{ paddingTop: 10, paddingLeft: 2, paddingRight: 2 }}>
      <svg width="20" height="10" viewBox="0 0 20 10" fill="none">
        <path d="M0 5h16M14 1l4 4-4 4" stroke="#5CF2C2" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" opacity="0.25" />
      </svg>
    </div>
  );
}

function WeekCard({ week, title, items }: { week: string; title: string; items: string[] }) {
  return (
    <div
      className="rounded-xl"
      style={{
        flex: 1,
        padding: '14px 16px',
        border: '1px solid rgba(255,255,255,0.06)',
        background: 'rgba(255,255,255,0.02)',
      }}
    >
      <div style={{ fontSize: 9, fontWeight: 700, color: '#5CF2C2', opacity: 0.5, letterSpacing: '0.1em', textTransform: 'uppercase' as const, marginBottom: 4 }}>
        {week}
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, color: '#F1F3F5', marginBottom: 8 }}>{title}</div>
      {items.map((item, i) => (
        <div key={i} style={{ fontSize: 10, color: '#7B8494', lineHeight: 1.7 }}>
          <span style={{ color: 'rgba(92,242,194,0.3)', marginRight: 5 }}>&rsaquo;</span>{item}
        </div>
      ))}
    </div>
  );
}

/* ── Icons ── */

function ShieldIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#5CF2C2" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}
function ListIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#5CF2C2" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  );
}
function ChartIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#5CF2C2" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}

export default LeaveBehind;
