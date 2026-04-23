import { Link } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import { ArrowRight } from 'lucide-react';

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

// ─── About page ───────────────────────────────────────────────────────────────
export function AboutPage() {
  const { ref: patternRef,   inView: patternInView }   = useInView(0.15);
  const { ref: founderRef,   inView: founderInView }   = useInView(0.15);
  const { ref: manifestoRef, inView: manifestoInView } = useInView(0.2);
  const { ref: contrastRef,  inView: contrastInView }  = useInView(0.15);

  return (
    <div className="bg-[#0D0F12]">

      {/* ═══════════════════════════════════════════════════════════════════
          OPENING — tension before the pitch
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
              About PickPulse · Operator-Built
            </span>
          </div>

          <div className="max-w-5xl">
            <h1 className="text-5xl md:text-6xl lg:text-7xl font-black text-white leading-[1.0] tracking-tight">
              Built from the problem.
            </h1>
            <h1 className="text-5xl md:text-6xl lg:text-7xl font-black text-slate-600 leading-[1.0] tracking-tight mt-1">
              Not around it.
            </h1>
          </div>

          <div className="mt-12 grid grid-cols-1 md:grid-cols-2 gap-10 max-w-4xl">
            <p className="text-lg text-slate-400 leading-relaxed">
              PickPulse was not created from a market analysis or a pitch deck thesis.
              It was created by someone who spent years inside high-growth revenue organizations —
              watching capable teams miss their number despite having more data than ever before.
            </p>
            <p className="text-base text-slate-500 leading-relaxed">
              The problem was never a lack of information. It was the absence of a system that
              turned that information into clear priorities and accountable predictions.
            </p>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          THE PATTERN WE KEPT SEEING — insight, not memoir
      ════════════════════════════════════════════════════════════════════ */}
      <section
        ref={patternRef as React.RefObject<HTMLDivElement>}
        className="py-28 md:py-40 bg-[#090B0E]"
      >
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-[5fr_7fr] gap-14 md:gap-20 items-start">

            <div className="md:sticky md:top-28">
              <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-5">
                The Operating Pattern
              </p>
              <h2 className="text-4xl font-black text-white leading-tight tracking-tight">
                The pattern<br />
                we kept seeing<br />
                <span className="text-slate-600">inside real<br />revenue teams.</span>
              </h2>
              <p className="text-sm text-slate-600 leading-relaxed mt-6 max-w-[220px]">
                Across organizations. Across roles. Across different data stacks.
              </p>
            </div>

            <div>
              {[
                {
                  label: 'They had data.',
                  desc: 'CRM records, billing history, product logs. More data than any previous generation of revenue operators. Often too much.',
                },
                {
                  label: 'They had dashboards.',
                  desc: 'Health scores, NRR charts, cohort retention curves. Hundreds of metrics always available, always on.',
                },
                {
                  label: 'They had weekly reports.',
                  desc: 'QBRs, churn reviews, executive decks with trend lines going back 18 months. The narrative was clear in hindsight.',
                },
                {
                  label: 'They had a capable team.',
                  desc: 'Experienced CSMs, attentive account managers, leadership that genuinely wanted to improve retention.',
                },
              ].map((item, i) => (
                <div
                  key={item.label}
                  className="py-7 border-t border-white/[0.06] transition-all duration-500"
                  style={{
                    opacity: patternInView ? 1 : 0,
                    transform: patternInView ? 'none' : 'translateX(-14px)',
                    transitionDelay: `${i * 100}ms`,
                  }}
                >
                  <p className="text-base font-bold text-slate-500 mb-1.5">{item.label}</p>
                  <p className="text-sm text-slate-700 leading-relaxed">{item.desc}</p>
                </div>
              ))}

              {/* The missing piece — visually distinct */}
              <div
                className="py-8 mt-2 border-t border-teal-500/25 transition-all duration-700"
                style={{
                  opacity: patternInView ? 1 : 0,
                  transitionDelay: '480ms',
                }}
              >
                <p className="text-xl font-bold text-white mb-3">
                  What they did not have was prioritization.
                </p>
                <p className="text-sm text-slate-400 leading-relaxed max-w-[420px]">
                  No one could answer: "Which accounts do I call today?" Not with confidence.
                  Not with a probability attached. Not with ARR exposure quantified and sorted.
                  The team worked hard — but not always on the right accounts. The miss was
                  visible in the data. No one had a system that surfaced it in time.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          FOUNDER SECTION — credibility through experience
      ════════════════════════════════════════════════════════════════════ */}
      <section
        ref={founderRef as React.RefObject<HTMLDivElement>}
        className="py-28 md:py-40 bg-[#0D0F12]"
      >
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid grid-cols-1 lg:grid-cols-[6fr_4fr] gap-16 lg:gap-24 items-start">

            {/* Copy */}
            <div
              className="transition-all duration-700"
              style={{ opacity: founderInView ? 1 : 0, transform: founderInView ? 'none' : 'translateX(-20px)' }}
            >
              <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-10">
                Founder
              </p>

              {/* Pull quote */}
              <p className="text-2xl md:text-3xl font-bold text-white leading-snug tracking-tight mb-10 border-l-2 border-teal-500/50 pl-6">
                "I've sat in QBRs where the miss was explained in a 40-slide deck
                that could have been a warning 90 days earlier."
              </p>

              <p className="text-base font-bold text-white mb-0.5">Nathan Lawrence</p>
              <p className="text-sm text-slate-500 mb-8">Founder, PickPulse Intelligence</p>

              <p className="text-base text-slate-400 leading-relaxed mb-5 max-w-lg">
                I spent my career inside high-growth revenue organizations — including GoDaddy, Amazon,
                and Zillow — building and scaling the systems that revenue teams depend on. I've led
                teams, carried pipeline accountability, and watched companies with excellent people
                still miss their number because no one had a clear, ranked view of where risk
                was actually concentrated.
              </p>
              <p className="text-base text-slate-400 leading-relaxed mb-5 max-w-lg">
                The tools that existed were built for reporting, not action. Complex to deploy.
                Slow to show value. And none of them held their own predictions accountable
                against real outcomes.
              </p>
              <p className="text-base text-slate-300 font-medium leading-relaxed max-w-lg">
                PickPulse is the tool I needed then. Built for the operators who are
                running the number today.
              </p>
            </div>

            {/* Photo */}
            <div
              className="transition-all duration-700 lg:pt-20"
              style={{
                opacity: founderInView ? 1 : 0,
                transform: founderInView ? 'none' : 'translateX(20px)',
                transitionDelay: '200ms',
              }}
            >
              <div className="relative">
                <div className="absolute -inset-6 bg-teal-500/[0.03] rounded-3xl blur-2xl pointer-events-none" />
                <div className="relative overflow-hidden rounded-2xl ring-1 ring-white/[0.1] shadow-2xl shadow-black/60">
                  <img
                    src="/LinkedInProfile.png"
                    alt="Nathan Lawrence, Founder of PickPulse Intelligence"
                    className="w-full block"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          MANIFESTO — the belief system, set in type
      ════════════════════════════════════════════════════════════════════ */}
      <section
        ref={manifestoRef as React.RefObject<HTMLDivElement>}
        className="py-28 md:py-40 bg-[#090B0E] border-t border-white/[0.06]"
      >
        <div className="max-w-5xl mx-auto px-6">
          <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-14">
            What we believe
          </p>

          <div className="space-y-5">
            {[
              { line: 'Data is not the same as clarity.',                                     bright: true  },
              { line: 'Dashboards are not the same as prioritization.',                       bright: false },
              { line: 'Scores are not the same as accountability.',                           bright: true  },
              { line: 'Visibility that arrives too late is just a better explanation of the miss.', bright: false },
            ].map((item, i) => (
              <p
                key={i}
                className={`text-3xl md:text-4xl lg:text-5xl font-black leading-tight tracking-tight transition-all duration-700 ${
                  item.bright ? 'text-white' : 'text-slate-700'
                }`}
                style={{
                  opacity: manifestoInView ? 1 : 0,
                  transform: manifestoInView ? 'none' : 'translateY(20px)',
                  transitionDelay: `${i * 130}ms`,
                }}
              >
                {item.line}
              </p>
            ))}
          </div>

          <div
            className="mt-16 pt-12 border-t border-teal-500/20 transition-all duration-700"
            style={{
              opacity: manifestoInView ? 1 : 0,
              transitionDelay: '620ms',
            }}
          >
            <p className="text-2xl md:text-3xl font-bold text-white leading-snug">
              Revenue teams need to know where to act.
            </p>
            <p className="text-2xl md:text-3xl font-bold text-teal-400 leading-snug mt-1">
              Now. Not after the QBR.
            </p>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          CONTRAST — most tools vs PickPulse
      ════════════════════════════════════════════════════════════════════ */}
      <section
        ref={contrastRef as React.RefObject<HTMLDivElement>}
        className="py-28 md:py-40 bg-[#0D0F12]"
      >
        <div className="max-w-6xl mx-auto px-6">
          <div className="mb-16">
            <p className="text-[11px] text-teal-500 uppercase tracking-widest font-semibold mb-5">
              Why PickPulse is different
            </p>
            <h2 className="text-4xl font-black text-white leading-tight tracking-tight">
              Built for action.
              <br />
              <span className="text-slate-600">Not reporting theater.</span>
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-0">

            {/* Left — what most tools create */}
            <div
              className="md:pr-14 transition-all duration-700"
              style={{ opacity: contrastInView ? 1 : 0, transform: contrastInView ? 'none' : 'translateX(-16px)' }}
            >
              <p className="text-[10px] uppercase tracking-widest font-semibold text-slate-700 mb-8">
                Most tools create
              </p>
              {[
                {
                  label: 'More dashboards to monitor',
                  sub: 'More surfaces. More time in review. Less clarity on where to act.',
                },
                {
                  label: 'Months of implementation',
                  sub: 'A data engineering project before your team sees any useful output.',
                },
                {
                  label: 'Proprietary scores you cannot interpret',
                  sub: "Numbers without meaning. You can't stake a retention budget on a black-box index.",
                },
                {
                  label: 'Reports that explain the miss',
                  sub: 'After the quarter closes. After the board asks why. Retroactive clarity is not intelligence.',
                },
              ].map((item) => (
                <div key={item.label} className="py-6 border-t border-white/[0.05]">
                  <p className="text-sm font-semibold text-slate-500">{item.label}</p>
                  <p className="text-xs text-slate-700 mt-1.5 leading-relaxed">{item.sub}</p>
                </div>
              ))}
            </div>

            {/* Right — PickPulse */}
            <div
              className="md:pl-14 md:border-l md:border-white/[0.07] mt-12 md:mt-0 transition-all duration-700"
              style={{
                opacity: contrastInView ? 1 : 0,
                transform: contrastInView ? 'none' : 'translateX(16px)',
                transitionDelay: '150ms',
              }}
            >
              <p className="text-[10px] uppercase tracking-widest font-semibold text-teal-500 mb-8">
                PickPulse delivers
              </p>
              {[
                {
                  label: 'Earlier signal — before renewal',
                  sub: '90-day advance visibility on which accounts are already deciding. Before it shows in the CRM.',
                },
                {
                  label: 'Live in 14 days',
                  sub: 'Connect your CRM or drop a CSV. Train on your history. Ranked accounts arrive in two weeks.',
                },
                {
                  label: 'Calibrated probabilities with meaning',
                  sub: "When we say 70%, that's a number you can build a retention plan, a budget case, and a board slide around.",
                },
                {
                  label: 'Predictions matched to real outcomes',
                  sub: 'The model tracks its own accuracy in production — not just at training. You always know if it is working.',
                },
              ].map((item) => (
                <div key={item.label} className="py-6 border-t border-white/[0.07]">
                  <p className="text-sm font-bold text-white">{item.label}</p>
                  <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">{item.sub}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          CLOSING CTA
      ════════════════════════════════════════════════════════════════════ */}
      <section className="py-36 bg-[#090B0E] relative overflow-hidden border-t border-white/[0.06]">
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-[900px] h-[300px] bg-teal-500/[0.04] rounded-full blur-3xl" />
        </div>
        <div className="relative max-w-2xl mx-auto px-6 text-center">
          <div className="flex items-center justify-center gap-2.5 mb-8">
            <PulseDot color="teal" size="md" />
            <span className="text-[11px] font-semibold text-teal-400 uppercase tracking-widest">
              See the accounts already deciding your quarter
            </span>
          </div>
          <h2 className="text-4xl md:text-5xl font-black text-white leading-tight tracking-tight mb-6">
            See what your<br />
            CRM is missing.
          </h2>
          <p className="text-slate-400 text-base leading-relaxed mb-10">
            The signals are already in your data. PickPulse reads them, ranks the accounts
            that matter, and tells your team exactly where to act — before the quarter decides itself.
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
