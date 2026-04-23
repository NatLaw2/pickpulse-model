import { Link } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Mail, FileText } from 'lucide-react';

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
    md: { dot: 'w-2 h-2',     ring: 'w-4.5 h-4.5' },
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

// ─── CRM table data ───────────────────────────────────────────────────────────
type CRMRow = {
  account: string;
  arr: string;
  risk: boolean;
  crmStatus: string;
  churnPct: string;
  tier: string;
  arrAtRisk: string;
};

const CRM_ROWS: CRMRow[] = [
  { account: 'Meridian Health', arr: '$420K', risk: true,  crmStatus: 'On Track', churnPct: '81%', tier: 'High',   arrAtRisk: '$420K' },
  { account: 'Vantage Capital', arr: '$210K', risk: true,  crmStatus: 'Healthy',  churnPct: '74%', tier: 'High',   arrAtRisk: '$210K' },
  { account: 'Apex Dynamics',   arr: '$185K', risk: false, crmStatus: 'On Track', churnPct: '31%', tier: 'Medium', arrAtRisk: '$57K'  },
  { account: 'Northstar Ops',   arr: '$160K', risk: true,  crmStatus: 'Healthy',  churnPct: '68%', tier: 'High',   arrAtRisk: '$160K' },
  { account: 'Clearline Tech',  arr: '$98K',  risk: false, crmStatus: 'Healthy',  churnPct: '22%', tier: 'Low',    arrAtRisk: '$22K'  },
  { account: 'Ironbridge Co.',  arr: '$77K',  risk: true,  crmStatus: 'On Track', churnPct: '79%', tier: 'High',   arrAtRisk: '$77K'  },
];

// ─── Decision compression — dot constellation ─────────────────────────────────
const HIGH_RISK_INDICES = new Set([5, 12, 23, 38, 51, 67, 89, 103]);
const DOT_COUNT = 192;

function AccountDotGrid({ revealed }: { revealed: boolean }) {
  return (
    <div>
      <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(16, minmax(0, 1fr))' }}>
        {Array.from({ length: DOT_COUNT }).map((_, i) => {
          const isHigh = HIGH_RISK_INDICES.has(i);
          return (
            <div
              key={i}
              className="transition-all duration-500"
              style={{ transitionDelay: `${i * 3}ms` }}
            >
              {isHigh && revealed ? (
                <span className="relative flex items-center justify-center w-2.5 h-2.5">
                  <span className="absolute w-5 h-5 rounded-full bg-rose-400/20 animate-ping" />
                  <span className="relative w-2.5 h-2.5 rounded-full bg-rose-400" />
                </span>
              ) : (
                <span
                  className="block w-2.5 h-2.5 rounded-full transition-all duration-500"
                  style={{
                    background: revealed ? 'rgba(255,255,255,0.04)' : 'rgba(255,255,255,0.08)',
                    transitionDelay: `${i * 2}ms`,
                  }}
                />
              )}
            </div>
          );
        })}
      </div>
      <p
        className="mt-4 text-xs text-slate-600 transition-all duration-700"
        style={{ opacity: revealed ? 1 : 0, transitionDelay: '700ms' }}
      >
        8 of 192 accounts · High Risk · $1.2M ARR exposed
      </p>
    </div>
  );
}

// ─── Homepage ─────────────────────────────────────────────────────────────────
export function HomePage() {
  // CRM reveal — fires once the section is 30% visible
  const crmSectionRef = useRef<HTMLElement>(null);
  const [crmRevealed, setCrmRevealed] = useState(false);

  useEffect(() => {
    const el = crmSectionRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setCrmRevealed(true); },
      { threshold: 0.25 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // Timeline — dot-by-dot reveal
  const { ref: timelineRef, inView: timelineInView } = useInView(0.2);
  const [dotsShown, setDotsShown] = useState(0);
  useEffect(() => {
    if (!timelineInView) return;
    let count = 0;
    const id = setInterval(() => {
      count++;
      setDotsShown(count);
      if (count >= 5) clearInterval(id);
    }, 320);
    return () => clearInterval(id);
  }, [timelineInView]);

  // Compression + platform
  const { ref: compressionRef, inView: compressionInView } = useInView(0.2);
  const { ref: platformRef, inView: platformInView } = useInView(0.12);

  return (
    <div className="bg-[#0D0F12]">

      {/* ═══════════════════════════════════════════════════════════════════
          HERO — full-screen editorial
      ════════════════════════════════════════════════════════════════════ */}
      <section className="relative min-h-[92vh] flex flex-col justify-center overflow-hidden">
        {/* Subtle grid */}
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
        <div className="absolute bottom-0 left-0 right-0 h-40 bg-gradient-to-b from-transparent to-[#0D0F12] pointer-events-none" />

        <div className="relative max-w-6xl mx-auto px-6 pt-16 pb-20">
          {/* Live signal badge */}
          <div className="flex items-center gap-2.5 mb-10">
            <PulseDot color="teal" />
            <span className="text-[11px] font-semibold text-teal-400 uppercase tracking-widest">
              ARR Intelligence · Live Signal
            </span>
          </div>

          {/* Editorial headline — two-tone contrast */}
          <div className="max-w-4xl">
            <h1 className="text-5xl md:text-6xl lg:text-[4.5rem] font-black text-white leading-[1.0] tracking-tight">
              Your CRM
              <br />
              looks healthy.
            </h1>
            <h1 className="text-5xl md:text-6xl lg:text-[4.5rem] font-black leading-[1.0] tracking-tight mt-1">
              <span className="text-slate-700">Your ARR</span>
              <span className="text-rose-400"> disagrees.</span>
            </h1>
          </div>

          {/* Subtext + CTAs + stats — asymmetric row */}
          <div className="mt-10 flex flex-col md:flex-row md:items-end gap-10 md:gap-20">
            <div className="max-w-md">
              <p className="text-lg text-slate-400 leading-relaxed">
                PickPulse reveals the accounts and deals that will determine
                your revenue in the next 90 days — the ones your CRM is hiding
                in plain sight.
              </p>
              <div className="flex flex-wrap gap-3 mt-8">
                <Link
                  to="/demo"
                  className="inline-flex items-center gap-2 px-6 py-3 bg-teal-500 text-white rounded-lg text-sm font-bold hover:bg-teal-400 transition-colors shadow-lg shadow-teal-500/20"
                >
                  Book a Demo <ArrowRight size={14} />
                </Link>
                <a
                  href="https://demo.pickpulse.co"
                  className="inline-flex items-center gap-2 px-6 py-3 border border-white/[0.12] text-slate-300 rounded-lg text-sm font-semibold hover:border-white/[0.22] hover:text-white transition-colors"
                >
                  See Live Demo
                </a>
              </div>
            </div>

            {/* Stat cluster — right side */}
            <div className="flex gap-10 md:gap-14 md:ml-auto md:pb-1">
              {[
                { value: '90', unit: 'days', label: 'advance signal' },
                { value: '2.7×', unit: '', label: 'lift vs. random' },
                { value: '14', unit: 'days', label: 'to first ranked list' },
              ].map((s) => (
                <div key={s.label}>
                  <div className="flex items-baseline gap-1">
                    <span className="text-3xl font-black text-white">{s.value}</span>
                    {s.unit && <span className="text-sm font-semibold text-teal-400">{s.unit}</span>}
                  </div>
                  <p className="text-[10px] text-slate-600 mt-0.5 uppercase tracking-wider">{s.label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          INTEGRATION STRIP
      ════════════════════════════════════════════════════════════════════ */}
      <section className="bg-[#090B0E] border-y border-white/[0.07] py-6">
        <div className="max-w-6xl mx-auto px-6">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <p className="text-[14px] text-slate-300 font-semibold">
              Works directly on your CRM data —{' '}
              <span className="text-slate-500">no rebuild required</span>
            </p>
            <div className="flex items-center gap-8 opacity-65">
              <span className="flex items-center gap-2 text-[13px] font-medium text-slate-400">
                <svg width="15" height="15" viewBox="0 0 20 20" fill="none">
                  <circle cx="10" cy="10" r="10" fill="#FF7A59" />
                  <circle cx="10" cy="8.5" r="2.8" fill="white" />
                  <path d="M7 14.5c0-1.657 1.343-3 3-3s3 1.343 3 3" stroke="white" strokeWidth="1.6" strokeLinecap="round" fill="none" />
                </svg>
                HubSpot
              </span>
              <span className="w-px h-3 bg-white/[0.14]" />
              <span className="flex items-center gap-2 text-[13px] font-medium text-slate-400">
                <svg width="15" height="15" viewBox="0 0 20 20" fill="none">
                  <path d="M10 4C7.79 4 6 5.79 6 8c0 .36.05.7.13 1.03A2.5 2.5 0 0 0 4.5 11.5 2.5 2.5 0 0 0 7 14h7a2.5 2.5 0 0 0 2.5-2.5c0-1.17-.81-2.15-1.9-2.42A4 4 0 0 0 10 4z" fill="#00A1E0" />
                </svg>
                Salesforce
              </span>
              <span className="w-px h-3 bg-white/[0.14]" />
              <span className="text-[13px] font-medium text-slate-400">CSV</span>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          THE GREEN CRM PROBLEM — signature dual-panel reveal
      ════════════════════════════════════════════════════════════════════ */}
      <section
        ref={crmSectionRef}
        className="py-28 md:py-40 bg-[#0D0F12]"
      >
        <div className="max-w-6xl mx-auto px-6">
          {/* Asymmetric editorial header */}
          <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] items-end mb-14 gap-6">
            <div>
              <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-5">
                The Hidden Revenue Problem
              </p>
              <h2 className="text-4xl md:text-5xl font-black text-white leading-[1.05] tracking-tight">
                Green health scores.<br />
                <span className="text-slate-600">Hidden churn.</span>
              </h2>
            </div>
            <p className="text-sm text-slate-600 max-w-[260px] leading-relaxed md:text-right md:pb-1">
              The same six accounts — two completely different pictures of your revenue.
            </p>
          </div>

          {/* Dual-panel table */}
          <div>
            {/* Column headers */}
            <div className="grid grid-cols-2 gap-4 mb-3">
              <p className="text-[10px] uppercase tracking-widest font-semibold text-slate-600 px-1">
                What your CRM shows
              </p>
              <div
                className="flex items-center gap-2 px-1 transition-opacity duration-700"
                style={{ opacity: crmRevealed ? 1 : 0 }}
              >
                <PulseDot color="teal" />
                <p className="text-[10px] uppercase tracking-widest font-semibold text-teal-500">
                  What PickPulse sees
                </p>
              </div>
            </div>

            {/* Rows */}
            <div className="space-y-2">
              {CRM_ROWS.map((row, i) => (
                <div key={row.account} className="grid grid-cols-2 gap-4">
                  {/* CRM column */}
                  <div className="flex items-center justify-between px-4 py-4 bg-[#131720] border border-white/[0.07] rounded-lg">
                    <div>
                      <p className="text-sm font-semibold text-white">{row.account}</p>
                      <p className="text-xs text-slate-600 mt-0.5">{row.arr} ARR</p>
                    </div>
                    <span className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-400">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      {row.crmStatus}
                    </span>
                  </div>

                  {/* PickPulse column */}
                  <div
                    className="flex items-center justify-between px-4 py-4 rounded-lg border transition-all duration-600"
                    style={{
                      transitionDelay: `${i * 90 + 180}ms`,
                      opacity: crmRevealed ? 1 : 0,
                      transform: crmRevealed ? 'none' : 'translateX(14px)',
                      background: row.risk ? 'rgba(244, 63, 94, 0.05)' : 'rgba(19, 23, 32, 0.5)',
                      borderColor: row.risk ? 'rgba(244, 63, 94, 0.22)' : 'rgba(255,255,255,0.06)',
                    }}
                  >
                    <div>
                      <p className={`text-sm font-semibold ${row.risk ? 'text-white' : 'text-slate-600'}`}>
                        {row.account}
                      </p>
                      {row.risk ? (
                        <p className="text-xs text-rose-400 mt-0.5">{row.arrAtRisk} at risk</p>
                      ) : (
                        <p className="text-xs text-slate-700 mt-0.5">Low risk · {row.arr}</p>
                      )}
                    </div>
                    {row.risk ? (
                      <div className="text-right">
                        <p className="text-xs font-bold text-rose-400">{row.churnPct} churn</p>
                        <span className="inline-flex items-center gap-1 mt-1 px-2 py-0.5 rounded-full bg-rose-500/[0.1] border border-rose-500/[0.18] text-[9px] font-bold text-rose-400 uppercase tracking-wide">
                          <PulseDot color="rose" /> {row.tier} Risk
                        </span>
                      </div>
                    ) : (
                      <p className="text-[11px] text-slate-700">{row.churnPct}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Reveal callout */}
            <div
              className="mt-7 flex items-start gap-4 p-5 bg-rose-500/[0.04] border border-rose-500/[0.14] rounded-xl transition-all duration-700"
              style={{
                transitionDelay: '800ms',
                opacity: crmRevealed ? 1 : 0,
                transform: crmRevealed ? 'none' : 'translateY(10px)',
              }}
            >
              <div className="w-8 h-8 rounded-lg bg-rose-500/[0.1] border border-rose-500/[0.18] flex items-center justify-center shrink-0 mt-0.5">
                <PulseDot color="rose" size="md" />
              </div>
              <div>
                <p className="text-sm font-bold text-white">
                  $867K ARR at risk — invisible in your CRM.
                </p>
                <p className="text-sm text-slate-500 mt-1 leading-relaxed">
                  Four accounts marked "Healthy" or "On Track" are showing 68–81% churn probability.
                  This is the gap PickPulse closes — before the quarter ends.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          THE REVENUE SIGNAL TIMELINE — "oh shit" moment
      ════════════════════════════════════════════════════════════════════ */}
      <section className="py-28 md:py-40 bg-[#090B0E] overflow-hidden">
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-16 md:gap-20 items-center">

            {/* Copy */}
            <div>
              <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-5">
                Revenue Signal Timeline
              </p>
              <h2 className="text-4xl md:text-5xl font-black text-white leading-[1.05] tracking-tight">
                The signals were<br />
                <span className="text-slate-600">always there.</span>
              </h2>
              <p className="text-base text-slate-400 leading-relaxed mt-6 max-w-sm">
                Churn doesn't happen at renewal. It's decided 60–90 days earlier —
                in product usage, support patterns, and engagement signals your
                team never had time to watch.
              </p>
              <p className="text-base text-slate-400 leading-relaxed mt-4 max-w-sm">
                PickPulse monitors every signal continuously. When the pattern
                looks like churn, you know at Day −90. Not Day 0.
              </p>
            </div>

            {/* Timeline — dot-by-dot reveal */}
            <div ref={timelineRef as React.RefObject<HTMLDivElement>}>
              {[
                {
                  day: 'Day −90',
                  color: 'teal' as const,
                  flagged: true,
                  title: 'Usage drop detected',
                  desc: 'Login frequency falls 40%. Key feature adoption stalls.',
                  flag: 'PickPulse flags this account as High Risk.',
                },
                {
                  day: 'Day −60',
                  color: 'amber' as const,
                  flagged: false,
                  title: 'Support tickets spike',
                  desc: 'Three unresolved tickets in 14 days. No escalation response.',
                },
                {
                  day: 'Day −30',
                  color: 'amber' as const,
                  flagged: false,
                  title: 'NPS survey skipped',
                  desc: 'Champion contact unreachable. QBR request declined.',
                },
                {
                  day: 'Day −14',
                  color: 'rose' as const,
                  flagged: false,
                  title: 'Renewal outreach ignored',
                  desc: 'No reply to CSM emails. Procurement contact is new.',
                },
                {
                  day: 'Day 0',
                  color: 'rose' as const,
                  flagged: false,
                  title: 'Churn. Revenue miss.',
                  desc: '$210K ARR lost. QBR explains the miss. Board asks how.',
                },
              ].map((event, i) => {
                const colorMap = {
                  teal:  { text: 'text-teal-400',  dot: 'bg-teal-400',  ring: 'border-teal-500/40 bg-teal-500/10'  },
                  amber: { text: 'text-amber-400', dot: 'bg-amber-400', ring: 'border-amber-500/40 bg-amber-500/10' },
                  rose:  { text: 'text-rose-400',  dot: 'bg-rose-400',  ring: 'border-rose-500/40 bg-rose-500/10'  },
                };
                const c = colorMap[event.color];
                return (
                  <div
                    key={event.day}
                    className="relative flex gap-5 pb-8 last:pb-0 transition-all duration-500"
                    style={{
                      opacity: dotsShown > i ? 1 : 0,
                      transform: dotsShown > i ? 'none' : 'translateX(-12px)',
                      transitionDelay: `${i * 40}ms`,
                    }}
                  >
                    {i < 4 && (
                      <div className="absolute left-[11px] top-7 bottom-0 w-px bg-white/[0.07]" />
                    )}
                    <div className={`relative w-6 h-6 rounded-full border flex items-center justify-center shrink-0 mt-0.5 ${c.ring}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
                    </div>
                    <div className="flex-1">
                      <div className="flex flex-wrap items-center gap-2.5 mb-1">
                        <span className={`text-[10px] font-black uppercase tracking-widest ${c.text}`}>
                          {event.day}
                        </span>
                        {event.flagged && (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-teal-500/[0.1] border border-teal-500/[0.2] text-[9px] font-bold text-teal-400 uppercase tracking-wide">
                            <PulseDot color="teal" /> PickPulse flags
                          </span>
                        )}
                      </div>
                      <p className="text-sm font-bold text-white">{event.title}</p>
                      <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">{event.desc}</p>
                      {event.flag && (
                        <p className="text-xs text-teal-500 mt-1.5 font-medium">{event.flag}</p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          DECISION COMPRESSION — 200 accounts → 8 that decide your quarter
      ════════════════════════════════════════════════════════════════════ */}
      <section
        ref={compressionRef as React.RefObject<HTMLDivElement>}
        className="py-28 md:py-40 bg-[#0D0F12]"
      >
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-16 md:gap-20 items-center">

            {/* Dot constellation */}
            <div className="order-2 md:order-1">
              <AccountDotGrid revealed={compressionInView} />
            </div>

            {/* Copy */}
            <div className="order-1 md:order-2">
              <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-5">
                Signal Compression
              </p>
              <h2 className="text-4xl md:text-5xl font-black text-white leading-[1.05] tracking-tight">
                200 accounts.<br />
                <span className="text-teal-400">8 that decide</span><br />
                <span className="text-slate-600">your quarter.</span>
              </h2>
              <p className="text-base text-slate-400 leading-relaxed mt-6 max-w-sm">
                Revenue outcomes are decided by a small number of accounts and deals —
                but no one has time to watch all 200. PickPulse compresses the signal:
                every renewal risk, every stalling deal, ranked by how much they'll
                move your number.
              </p>
              <p className="text-base text-slate-400 leading-relaxed mt-4 max-w-sm">
                Your team works the list. Highest-impact accounts, first.
              </p>
              <div className="mt-8 flex items-center gap-6">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-400" />
                  <span className="text-xs text-slate-600">High risk</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-white/[0.08] border border-white/[0.1]" />
                  <span className="text-xs text-slate-600">Low risk</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          PLATFORM IN ACTION — asymmetric, alternating layout
      ════════════════════════════════════════════════════════════════════ */}
      <section
        ref={platformRef as React.RefObject<HTMLDivElement>}
        className="py-28 md:py-40 bg-[#090B0E] overflow-hidden"
      >
        <div className="max-w-6xl mx-auto px-6">
          <div className="mb-20">
            <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-5">
              Platform in Action
            </p>
            <h2 className="text-4xl md:text-5xl font-black text-white leading-[1.05] tracking-tight">
              From risk signal<br />
              <span className="text-slate-600">to action — in seconds.</span>
            </h2>
          </div>

          {/* AI Email — screenshot left, copy right */}
          <div className="grid grid-cols-1 lg:grid-cols-[6fr_5fr] gap-14 lg:gap-20 items-center mb-32">
            <div
              className="relative transition-all duration-700"
              style={{ opacity: platformInView ? 1 : 0, transform: platformInView ? 'none' : 'translateX(-20px)' }}
            >
              <div className="absolute -inset-6 bg-teal-500/[0.03] rounded-3xl blur-3xl pointer-events-none" />
              <div className="relative rounded-xl overflow-hidden ring-1 ring-white/[0.08] shadow-2xl shadow-black/70">
                <img
                  src="/AI email drafting.png"
                  alt="AI-drafted outreach interface showing account risk signals and tone selector"
                  className="w-full block"
                />
              </div>
            </div>
            <div
              className="transition-all duration-700"
              style={{ opacity: platformInView ? 1 : 0, transform: platformInView ? 'none' : 'translateX(20px)', transitionDelay: '200ms' }}
            >
              <div className="flex items-center gap-2.5 mb-7">
                <div className="w-8 h-8 rounded-xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center">
                  <Mail size={14} className="text-teal-400" />
                </div>
                <span className="text-[11px] font-semibold text-teal-400 uppercase tracking-widest">
                  AI-Drafted Outreach
                </span>
              </div>
              <h3 className="text-3xl font-black text-white leading-tight tracking-tight">
                Risk detected.<br />
                Outreach drafted.<br />
                <span className="text-slate-500">Ready in seconds.</span>
              </h3>
              <p className="text-base text-slate-400 leading-relaxed mt-5 max-w-sm">
                When PickPulse flags an account, it explains exactly why — then generates
                a targeted retention email grounded in that account's specific signals.
                Adjustable tone. Account-specific. Built for CSMs managing 150 accounts, not 10.
              </p>
            </div>
          </div>

          {/* Executive Brief — copy left, screenshot right */}
          <div className="grid grid-cols-1 lg:grid-cols-[5fr_6fr] gap-14 lg:gap-20 items-center">
            <div
              className="transition-all duration-700"
              style={{ opacity: platformInView ? 1 : 0, transform: platformInView ? 'none' : 'translateX(-20px)', transitionDelay: '150ms' }}
            >
              <div className="flex items-center gap-2.5 mb-7">
                <div className="w-8 h-8 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                  <FileText size={14} className="text-violet-400" />
                </div>
                <span className="text-[11px] font-semibold text-violet-400 uppercase tracking-widest">
                  Executive ARR Brief
                </span>
              </div>
              <h3 className="text-3xl font-black text-white leading-tight tracking-tight">
                Board-ready.<br />
                Auto-generated.<br />
                <span className="text-slate-500">Every week.</span>
              </h3>
              <p className="text-base text-slate-400 leading-relaxed mt-5 max-w-sm">
                A structured summary of ARR at risk, projected recoverable revenue, and the
                accounts driving your 90-day number. Formatted for a board slide or QBR —
                not a dashboard screenshot pasted into a deck.
              </p>
            </div>
            <div
              className="relative transition-all duration-700"
              style={{ opacity: platformInView ? 1 : 0, transform: platformInView ? 'none' : 'translateX(20px)', transitionDelay: '250ms' }}
            >
              <div className="absolute -inset-6 bg-violet-500/[0.025] rounded-3xl blur-3xl pointer-events-none" />
              <div className="relative rounded-xl overflow-hidden ring-1 ring-white/[0.08] shadow-2xl shadow-black/70 max-h-[500px]">
                <img
                  src="/ExecutiveBrief.png"
                  alt="Executive ARR brief showing portfolio summary and top at-risk accounts"
                  className="w-full block"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          HOW IT WORKS — editorial sidebar layout, not card grid
      ════════════════════════════════════════════════════════════════════ */}
      <section className="py-28 md:py-36 bg-[#0D0F12]">
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-[5fr_7fr] gap-14 md:gap-20 items-start">

            {/* Sticky label column */}
            <div className="md:sticky md:top-28">
              <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-5">
                Implementation
              </p>
              <h2 className="text-4xl font-black text-white leading-tight tracking-tight">
                Live in<br />14 days.
              </h2>
              <p className="text-sm text-slate-500 leading-relaxed mt-5 max-w-[240px]">
                No engineering sprint. No data warehouse.
                Connect your revenue data and PickPulse handles everything else.
              </p>
            </div>

            {/* Step list */}
            <div>
              {[
                { num: '01', title: 'Connect', desc: 'Connect HubSpot, Stripe, or drop in a structured CSV. PickPulse handles schema mapping and outcome labeling. No engineering sprint required.' },
                { num: '02', title: 'Train',   desc: "A gradient-boosted model trains on your historical data — learning what churn and deal close look like in your specific business, your cohorts, your signals. Not someone else's averages." },
                { num: '03', title: 'Score',   desc: 'Every account and deal receives a calibrated probability. Not a relative index. Not a proprietary score. A probability you can stake a forecast on.' },
                { num: '04', title: 'Prioritize', desc: 'Ranked lists surface the accounts and deals that matter most, sorted by ARR exposure and urgency. Your team works the list — not the inbox.' },
                { num: '05', title: 'Verify',  desc: 'Predictions are matched against real outcomes automatically. You always know how the model is performing in production — not just on launch day.' },
              ].map((step) => (
                <div
                  key={step.num}
                  className="flex gap-7 py-8 border-t border-white/[0.06] group hover:border-white/[0.1] transition-colors"
                >
                  <span className="text-5xl font-black text-white/[0.06] leading-none shrink-0 group-hover:text-white/[0.1] transition-colors pt-0.5">
                    {step.num}
                  </span>
                  <div>
                    <h3 className="text-base font-bold text-white mb-2">{step.title}</h3>
                    <p className="text-sm text-slate-500 leading-relaxed">{step.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          ACCOUNTABILITY — quiet credibility bar
      ════════════════════════════════════════════════════════════════════ */}
      <section className="py-20 bg-[#090B0E] border-t border-white/[0.06]">
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-[2fr_1fr_1fr_1fr] gap-10 items-center">
            <div>
              <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-4">
                Accountability by design
              </p>
              <p className="text-2xl font-bold text-white leading-snug tracking-tight">
                A model that holds itself to the same standard as your team.
              </p>
            </div>
            {[
              { stat: 'Calibrated',   label: 'probabilities, not relative scores' },
              { stat: 'Zero black boxes', label: 'every prediction is explained' },
              { stat: 'Live accuracy', label: 'matched to real outcomes automatically' },
            ].map((s) => (
              <div key={s.stat} className="border-l border-white/[0.07] pl-8">
                <p className="text-lg font-black text-white">{s.stat}</p>
                <p className="text-xs text-slate-600 mt-1.5 leading-relaxed">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          FINAL CTA
      ════════════════════════════════════════════════════════════════════ */}
      <section className="py-36 bg-[#090B0E] relative overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-[900px] h-[320px] bg-teal-500/[0.04] rounded-full blur-3xl" />
        </div>
        <div className="relative max-w-2xl mx-auto px-6 text-center">
          <div className="flex items-center justify-center gap-2.5 mb-8">
            <PulseDot color="teal" size="md" />
            <span className="text-[11px] font-semibold text-teal-400 uppercase tracking-widest">
              See your 90-day ARR signal
            </span>
          </div>
          <h2 className="text-4xl md:text-5xl font-black text-white leading-tight tracking-tight mb-6">
            What does your ARR look like in 90 days?
          </h2>
          <p className="text-slate-400 text-base leading-relaxed mb-10">
            We'll walk through the platform using your data or a representative sample.
            Most operators leave with a ranked list of their highest-risk accounts.
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
