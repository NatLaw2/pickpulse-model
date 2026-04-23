import { Link } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Clock } from 'lucide-react';

// ─── Scroll-reveal hook ────────────────────────────────────────────────────────
function useInView(threshold = 0.15) {
  const ref = useRef<HTMLElement>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setInView(true); },
      { threshold }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);
  return { ref, inView };
}

// ─── Pulse signal dot ─────────────────────────────────────────────────────────
function PulseDot({ color = 'teal', size = 'sm' }: { color?: 'teal' | 'rose' | 'amber'; size?: 'sm' | 'md' }) {
  const palettes = {
    teal:  { dot: 'bg-teal-400',  ring: 'bg-teal-400/25' },
    rose:  { dot: 'bg-rose-400',  ring: 'bg-rose-400/25' },
    amber: { dot: 'bg-amber-400', ring: 'bg-amber-400/25' },
  };
  const sizes = {
    sm: { dot: 'w-1.5 h-1.5', ring: 'w-3.5 h-3.5' },
    md: { dot: 'w-2 h-2',     ring: 'w-5 h-5' },
  };
  const p = palettes[color];
  const s = sizes[size];
  return (
    <span className="relative inline-flex items-center justify-center">
      <span className={`absolute ${s.ring} rounded-full ${p.ring} animate-ping opacity-70`} />
      <span className={`relative ${s.dot} rounded-full ${p.dot}`} />
    </span>
  );
}

// ─── Account X-Ray — signature product visualization ─────────────────────────
function AccountXRay({ revealed }: { revealed: boolean }) {
  const signals = [
    { label: 'Product usage',   value: '↓ 38% over 30 days',       bars: 4, risk: 'High' as const },
    { label: 'Support tickets', value: '2 open, unresolved 14 days', bars: 4, risk: 'High' as const },
    { label: 'QBR attendance',  value: 'Declined last quarter',      bars: 3, risk: 'Elevated' as const },
    { label: 'Seat adoption',   value: '4 of 12 seats active',       bars: 2, risk: 'Low' as const },
  ];

  const riskStyle = {
    High:     { badge: 'text-rose-400 bg-rose-500/10',   bar: 'from-rose-600 to-rose-400' },
    Elevated: { badge: 'text-amber-400 bg-amber-500/10', bar: 'from-amber-600 to-amber-400' },
    Low:      { badge: 'text-slate-500 bg-white/[0.04]', bar: 'from-slate-700 to-slate-600' },
  };

  return (
    <div className="bg-[#0D0F12] border border-white/[0.1] rounded-2xl overflow-hidden shadow-2xl shadow-black/60">
      {/* Account header */}
      <div className="px-6 py-5 border-b border-white/[0.07] flex items-start justify-between">
        <div>
          <p className="text-sm font-bold text-white">Vantage Capital</p>
          <p className="text-xs text-slate-600 mt-0.5">$210K ARR · Enterprise · SaaS</p>
        </div>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-500/[0.1] border border-rose-500/[0.2]">
          <PulseDot color="rose" />
          <span className="text-[10px] font-bold text-rose-400 uppercase tracking-wide">High Risk</span>
        </span>
      </div>

      {/* Renewal urgency */}
      <div className="px-6 pt-4 flex items-center gap-2">
        <Clock size={11} className="text-amber-400" />
        <span className="text-[11px] text-amber-400 font-semibold">Renewal in 47 days</span>
      </div>

      {/* Signal rows */}
      <div className="px-6 pt-4 pb-4">
        <p className="text-[9px] uppercase tracking-widest font-semibold text-slate-700 mb-4">Risk Signals</p>
        <div className="space-y-4">
          {signals.map((sig, i) => (
            <div
              key={sig.label}
              className="transition-all duration-500"
              style={{
                opacity: revealed ? 1 : 0,
                transform: revealed ? 'none' : 'translateY(8px)',
                transitionDelay: `${i * 110}ms`,
              }}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[12px] text-slate-400">{sig.label}</span>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-slate-600">{sig.value}</span>
                  <span className={`text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full ${riskStyle[sig.risk].badge}`}>
                    {sig.risk}
                  </span>
                </div>
              </div>
              <div className="h-1 bg-white/[0.05] rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full bg-gradient-to-r ${riskStyle[sig.risk].bar} transition-all duration-700`}
                  style={{
                    width: revealed ? `${(sig.bars / 5) * 100}%` : '0%',
                    transitionDelay: `${i * 110 + 180}ms`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Model output */}
      <div className="mx-6 mb-6 mt-2 p-5 bg-[#131720] border border-white/[0.06] rounded-xl">
        <p className="text-[9px] uppercase tracking-widest font-semibold text-slate-700 mb-4">Model Output</p>
        <div className="flex items-center justify-between mb-2.5">
          <span className="text-sm font-bold text-white">Churn Probability</span>
          <span
            className="text-2xl font-black text-rose-400 transition-all duration-700"
            style={{ opacity: revealed ? 1 : 0, transitionDelay: '550ms' }}
          >
            74%
          </span>
        </div>
        <div className="h-2 bg-white/[0.05] rounded-full overflow-hidden mb-4">
          <div
            className="h-full bg-gradient-to-r from-amber-500 to-rose-500 rounded-full transition-all duration-1000"
            style={{ width: revealed ? '74%' : '0%', transitionDelay: '480ms' }}
          />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-600">
            ARR at risk: <span className="text-white font-semibold">$210,000</span>
          </span>
          <span className="text-xs text-slate-600">
            Priority: <span className="text-rose-400 font-semibold">Immediate</span>
          </span>
        </div>
      </div>
    </div>
  );
}

// ─── How It Works page ────────────────────────────────────────────────────────
export function OnboardingPage() {
  const { ref: xrayRef,     inView: xrayInView }     = useInView(0.2);
  const { ref: timelineRef, inView: timelineInView } = useInView(0.15);
  const { ref: diffRef,     inView: diffInView }     = useInView(0.3);

  return (
    <div className="bg-[#0D0F12]">

      {/* ═══════════════════════════════════════════════════════════════════
          OPENING — reframe from "onboarding" to transformation
      ════════════════════════════════════════════════════════════════════ */}
      <section className="relative overflow-hidden py-28 md:py-40">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: `
              linear-gradient(rgba(255,255,255,0.014) 1px, transparent 1px),
              linear-gradient(90deg, rgba(255,255,255,0.014) 1px, transparent 1px)
            `,
            backgroundSize: '72px 72px',
          }}
        />
        <div className="absolute bottom-0 left-0 right-0 h-36 bg-gradient-to-b from-transparent to-[#0D0F12] pointer-events-none" />

        <div className="relative max-w-6xl mx-auto px-6">
          <div className="flex items-center gap-2.5 mb-10">
            <PulseDot color="teal" />
            <span className="text-[11px] font-semibold text-teal-400 uppercase tracking-widest">
              ARR Intelligence · How It Works
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] items-end gap-10 max-w-5xl">
            <div>
              <h1 className="text-5xl md:text-6xl font-black text-white leading-[1.0] tracking-tight">
                From your data
                <br />
                <span className="text-slate-600">to decisions —</span>
              </h1>
              <h1 className="text-5xl md:text-6xl font-black text-teal-400 leading-[1.0] tracking-tight mt-1">
                in under two weeks.
              </h1>
            </div>
            <p className="text-sm text-slate-500 leading-relaxed max-w-[260px] md:pb-2">
              Not an integration project. Not a dashboard rebuild.
              A revenue signal system that reads your CRM and tells you what matters.
            </p>
          </div>

          <div className="flex flex-wrap gap-10 mt-14">
            {[
              { value: '14',    unit: 'days',  label: 'to first ranked list' },
              { value: 'Zero',  unit: '',       label: 'engineering sprints required' },
              { value: '90',    unit: 'days',  label: 'of advance revenue signal' },
            ].map((s) => (
              <div key={s.label}>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-3xl font-black text-white">{s.value}</span>
                  {s.unit && <span className="text-sm font-semibold text-teal-400">{s.unit}</span>}
                </div>
                <p className="text-[10px] text-slate-600 mt-0.5 uppercase tracking-wider">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          WHAT POWERS THE MODEL — data with meaning, not a field list
      ════════════════════════════════════════════════════════════════════ */}
      <section className="py-28 md:py-40 bg-[#090B0E]">
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-[5fr_7fr] gap-14 md:gap-20 items-start">

            <div className="md:sticky md:top-28">
              <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-5">
                The Foundation
              </p>
              <h2 className="text-4xl font-black text-white leading-tight tracking-tight">
                What we use<br />
                to predict<br />
                your next<br />
                90 days.
              </h2>
              <p className="text-sm text-slate-500 leading-relaxed mt-5 max-w-[240px]">
                Six fields from your CRM or billing system. No custom schema. No data warehouse.
                That's the baseline.
              </p>
            </div>

            <div>
              {[
                {
                  field: 'ARR or MRR',
                  signal: "Measures what's at stake",
                  why: "Tells the model how much each prediction matters. Not all accounts churn equally — a $400K account and a $12K account require different urgency, different intervention, different resource allocation.",
                },
                {
                  field: 'Renewal Date',
                  signal: 'Defines the clock',
                  why: "Creates urgency scoring. An account at 78% churn risk with 14 days to renewal is a different emergency than the same score at 180 days. Timing is the variable that separates a save from a miss.",
                },
                {
                  field: 'Contract Start Date',
                  signal: 'Establishes tenure',
                  why: "Cohort patterns matter. Accounts churning at Month 6 look different from Month 18. The model learns your specific churn shape — not someone else's industry averages.",
                },
                {
                  field: 'Account Status',
                  signal: 'Defines the outcome',
                  why: "This is how the model learns what 'churn' actually means in your business. Churned, renewed, expanded — mapped from your real historical data, not a generic label.",
                },
                {
                  field: 'Customer Segment',
                  signal: 'Segments the risk',
                  why: "Enterprise churn looks different from SMB churn. Healthcare behaves differently from SaaS. The model learns your segment-specific patterns — the ones invisible in aggregate numbers.",
                },
                {
                  field: 'Account ID',
                  signal: 'Anchors everything',
                  why: "Joins signals across time. Without this persistent identifier, there's no way to connect a usage drop in March to a churn event in June — no way to learn from history.",
                },
              ].map((item, i) => (
                <div
                  key={item.field}
                  className="flex gap-6 py-7 border-t border-white/[0.06] group hover:border-white/[0.1] transition-colors"
                >
                  <span className="text-4xl font-black text-white/[0.05] leading-none shrink-0 group-hover:text-white/[0.09] transition-colors pt-0.5 tabular-nums">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <div>
                    <div className="flex flex-wrap items-center gap-2.5 mb-2">
                      <h3 className="text-base font-bold text-white">{item.field}</h3>
                      <span className="text-[10px] text-teal-500 font-semibold uppercase tracking-wide px-2 py-0.5 bg-teal-500/[0.08] rounded-full border border-teal-500/[0.15]">
                        {item.signal}
                      </span>
                    </div>
                    <p className="text-sm text-slate-500 leading-relaxed">{item.why}</p>
                  </div>
                </div>
              ))}
              <div className="border-t border-white/[0.06] pt-6">
                <p className="text-sm font-semibold text-white">
                  That's enough to build a model that outperforms your current forecast.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          ACCOUNT X-RAY — signature visual moment
      ════════════════════════════════════════════════════════════════════ */}
      <section
        ref={xrayRef as React.RefObject<HTMLDivElement>}
        className="py-28 md:py-40 bg-[#0D0F12]"
      >
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid grid-cols-1 lg:grid-cols-[5fr_6fr] gap-14 lg:gap-20 items-center">

            <div>
              <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-5">
                Model in Action
              </p>
              <h2 className="text-4xl font-black text-white leading-tight tracking-tight">
                This is how<br />
                the model reads<br />
                <span className="text-slate-600">a single account.</span>
              </h2>
              <p className="text-base text-slate-400 leading-relaxed mt-6 max-w-sm">
                Every account in your CRM gets a version of this. Signals in. Probability out.
                ARR exposure calculated. Ranked by urgency against every other account you have.
              </p>
              <p className="text-base text-slate-400 leading-relaxed mt-4 max-w-sm">
                Not a health score. Not a traffic light. A calibrated probability you can
                stake a retention budget on.
              </p>
              <div className="mt-8 flex items-center gap-3">
                <PulseDot color="rose" />
                <span className="text-sm text-slate-500">
                  Vantage Capital — flagged 90 days before renewal
                </span>
              </div>
            </div>

            <div
              className="transition-all duration-700"
              style={{ opacity: xrayInView ? 1 : 0, transform: xrayInView ? 'none' : 'translateX(16px)' }}
            >
              <AccountXRay revealed={xrayInView} />
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          SIGNALS THAT SHARPEN THE MODEL — optional data as performance
      ════════════════════════════════════════════════════════════════════ */}
      <section className="py-28 md:py-36 bg-[#090B0E]">
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] items-end gap-6 mb-14">
            <div>
              <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-5">
                Performance Tuning
              </p>
              <h2 className="text-4xl font-black text-white leading-tight tracking-tight">
                Signals that<br />
                <span className="text-slate-600">sharpen the model.</span>
              </h2>
            </div>
            <p className="text-sm text-slate-600 max-w-[260px] leading-relaxed md:text-right md:pb-1">
              Not required to start. Each one moves the model's detection window earlier
              and increases probability precision.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              {
                signal: 'Product Usage Metrics',
                impact: 'Earliest risk indicator',
                color: 'teal' as const,
                desc: "Usage drops precede churn by 60–90 days. Login frequency and feature adoption are the model's best early-warning signals — often the first to move before any CRM field changes.",
              },
              {
                signal: 'Support Ticket Volume',
                impact: 'Friction proxy',
                color: 'amber' as const,
                desc: "Unresolved tickets and repeat issues correlate strongly with churn intent. The model learns the specific ticket patterns that predict your churns — not generic support benchmarks.",
              },
              {
                signal: 'Payment History',
                impact: 'Financial stress signal',
                color: 'rose' as const,
                desc: "Late payments, downgrades, and disputed charges are upstream signals of cancellation decisions, often appearing weeks before a formal notice reaches your CSM.",
              },
              {
                signal: 'NPS or CSAT Scores',
                impact: 'Sentiment layer',
                color: 'teal' as const,
                desc: "Low scores and non-responses both matter. A skipped NPS survey is itself a signal — the model accounts for what customers don't say as much as what they do.",
              },
              {
                signal: 'Seat or License Utilization',
                impact: 'Adoption signal',
                color: 'amber' as const,
                desc: "A team paying for 20 seats and using 4 is quietly deciding. Adoption gaps reveal accounts that haven't gotten value — and are weighing their options at renewal.",
              },
              {
                signal: 'Expansion or Contraction History',
                impact: 'Trajectory signal',
                color: 'violet' as const,
                desc: "Accounts that expanded are less likely to churn. Those that contracted are higher risk. Historical trajectory shapes future probability in ways point-in-time signals miss.",
              },
            ].map((item) => {
              const palettes = {
                teal:   { badge: 'text-teal-400 bg-teal-500/[0.08] border-teal-500/[0.15]',     dot: 'bg-teal-400/50' },
                amber:  { badge: 'text-amber-400 bg-amber-500/[0.08] border-amber-500/[0.15]',   dot: 'bg-amber-400/50' },
                rose:   { badge: 'text-rose-400 bg-rose-500/[0.08] border-rose-500/[0.15]',     dot: 'bg-rose-400/50' },
                violet: { badge: 'text-violet-400 bg-violet-500/[0.08] border-violet-500/[0.15]', dot: 'bg-violet-400/50' },
              };
              const c = palettes[item.color];
              return (
                <div
                  key={item.signal}
                  className="p-6 bg-[#131720] border border-white/[0.07] rounded-2xl hover:border-white/[0.12] transition-colors"
                >
                  <div className="flex items-center gap-2 mb-4">
                    <span className={`w-2 h-2 rounded-full ${c.dot}`} />
                    <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full border ${c.badge}`}>
                      {item.impact}
                    </span>
                  </div>
                  <h3 className="text-sm font-bold text-white mb-2">{item.signal}</h3>
                  <p className="text-xs text-slate-500 leading-relaxed">{item.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          THE 14-DAY TRANSFORMATION — timeline as narrative
      ════════════════════════════════════════════════════════════════════ */}
      <section
        ref={timelineRef as React.RefObject<HTMLDivElement>}
        className="py-28 md:py-40 bg-[#0D0F12]"
      >
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-[5fr_7fr] gap-14 md:gap-20 items-start">

            <div className="md:sticky md:top-28">
              <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-5">
                The Transformation
              </p>
              <h2 className="text-4xl font-black text-white leading-tight tracking-tight">
                What actually<br />
                happens<br />
                in 14 days.
              </h2>
              <p className="text-sm text-slate-500 leading-relaxed mt-5 max-w-[240px]">
                Not an onboarding checklist. The sequence of events that turns CRM data
                into a live revenue signal system.
              </p>
            </div>

            <div>
              {[
                {
                  period: 'Days 1–3',
                  color: 'teal' as const,
                  live: false,
                  heading: 'The model learns what churn looks like in your business.',
                  body: "Historical CRM data arrives. The model traces through your churned accounts — and your renewals — learning the specific signal patterns that preceded each outcome. Not industry templates. Your actual history.",
                },
                {
                  period: 'Days 4–7',
                  color: 'teal' as const,
                  live: false,
                  heading: 'Probabilities emerge. The CRM picture changes.',
                  body: "Training completes. Every active account receives a calibrated probability — not a score, a probability with meaning. For the first time, you see which 'healthy' accounts are actually at risk.",
                },
                {
                  period: 'Days 8–14',
                  color: 'amber' as const,
                  live: false,
                  heading: 'Calibration review. The model proves its numbers.',
                  body: "Predicted probabilities are tested against held-out historical outcomes. When the model says 70%, it should have been right 7 in 10 times. If calibration is off, it adjusts before going live.",
                },
                {
                  period: 'Day 15+',
                  color: 'rose' as const,
                  live: true,
                  heading: 'Live. Every signal watched. Every outcome recorded.',
                  body: "Predictions update as signals change. New churn outcomes are automatically matched against prior predictions. The model tracks its own accuracy — in production, not in a test environment.",
                },
              ].map((phase, i) => {
                const colorMap = {
                  teal:  { text: 'text-teal-400',  dot: 'bg-teal-400',  ring: 'border-teal-500/40 bg-teal-500/10' },
                  amber: { text: 'text-amber-400', dot: 'bg-amber-400', ring: 'border-amber-500/40 bg-amber-500/10' },
                  rose:  { text: 'text-rose-400',  dot: 'bg-rose-400',  ring: 'border-rose-500/40 bg-rose-500/10' },
                };
                const c = colorMap[phase.color];
                return (
                  <div
                    key={phase.period}
                    className="relative flex gap-6 pb-10 last:pb-0 transition-all duration-600"
                    style={{
                      opacity: timelineInView ? 1 : 0,
                      transform: timelineInView ? 'none' : 'translateX(-16px)',
                      transitionDelay: `${i * 140}ms`,
                    }}
                  >
                    {i < 3 && (
                      <div className="absolute left-[11px] top-7 bottom-0 w-px bg-white/[0.07]" />
                    )}
                    <div className={`relative w-6 h-6 rounded-full border flex items-center justify-center shrink-0 mt-0.5 ${c.ring}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
                    </div>
                    <div>
                      <div className="flex flex-wrap items-center gap-2.5 mb-2">
                        <span className={`text-[10px] font-black uppercase tracking-widest ${c.text}`}>
                          {phase.period}
                        </span>
                        {phase.live && (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-teal-500/[0.1] border border-teal-500/[0.2] text-[9px] font-bold text-teal-400 uppercase tracking-wide">
                            <PulseDot color="teal" /> Live
                          </span>
                        )}
                      </div>
                      <h3 className="text-[15px] font-bold text-white mb-2 leading-snug">{phase.heading}</h3>
                      <p className="text-sm text-slate-500 leading-relaxed">{phase.body}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          DIFFERENTIATION — no bullets, just a statement
      ════════════════════════════════════════════════════════════════════ */}
      <section
        ref={diffRef as React.RefObject<HTMLDivElement>}
        className="py-28 md:py-40 bg-[#090B0E] border-t border-white/[0.06]"
      >
        <div className="max-w-5xl mx-auto px-6">
          <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-12">
            How this is different
          </p>
          <div
            className="transition-all duration-700"
            style={{ opacity: diffInView ? 1 : 0, transform: diffInView ? 'none' : 'translateY(20px)' }}
          >
            <p className="text-4xl md:text-5xl font-black text-white leading-[1.1] tracking-tight">
              No multi-month integration.
              <br />
              <span className="text-slate-600">No black-box scoring.</span>
              <br />
              No dashboards your team ignores.
            </p>
            <div className="mt-12 w-16 h-px bg-teal-500/30" />
            <p className="text-xl md:text-2xl font-bold text-slate-400 mt-10 leading-relaxed">
              Just a system that shows you what matters —
              <br />
              <span className="text-white">and proves whether it was right.</span>
            </p>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          CLOSING CTA
      ════════════════════════════════════════════════════════════════════ */}
      <section className="py-36 bg-[#090B0E] relative overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-[900px] h-[300px] bg-teal-500/[0.04] rounded-full blur-3xl" />
        </div>
        <div className="relative max-w-2xl mx-auto px-6 text-center">
          <div className="flex items-center justify-center gap-2.5 mb-8">
            <PulseDot color="teal" size="md" />
            <span className="text-[11px] font-semibold text-teal-400 uppercase tracking-widest">
              See what your CRM is missing
            </span>
          </div>
          <h2 className="text-4xl md:text-5xl font-black text-white leading-tight tracking-tight mb-6">
            Your CRM has the signals.
            <br />
            <span className="text-slate-600">You just can't see them yet.</span>
          </h2>
          <p className="text-slate-400 text-base leading-relaxed mb-10">
            Most operators leave their first demo with a ranked list of their highest-risk
            accounts — ones they didn't know were at risk. The signals were always there.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to="/demo"
              className="inline-flex items-center justify-center gap-2 px-8 py-3.5 bg-teal-500 text-white rounded-lg text-sm font-bold hover:bg-teal-400 transition-colors shadow-lg shadow-teal-500/20"
            >
              Book a Demo <ArrowRight size={14} />
            </Link>
            <a
              href="https://demo.pickpulse.co"
              className="inline-flex items-center justify-center gap-2 px-8 py-3.5 border border-white/[0.12] text-slate-300 rounded-lg text-sm font-semibold hover:border-white/[0.22] hover:text-white transition-colors"
            >
              Explore the Live Demo
            </a>
          </div>
          <p className="text-slate-700 text-xs mt-6">
            We typically respond within one business day.
          </p>
        </div>
      </section>

    </div>
  );
}
