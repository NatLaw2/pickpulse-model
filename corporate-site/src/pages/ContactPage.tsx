import { Mail, Send, CheckCircle2, Linkedin } from 'lucide-react';

// ─── Pulse dot (matches site-wide pattern) ────────────────────────────────────
function PulseDot() {
  return (
    <span className="relative inline-flex items-center justify-center">
      <span className="absolute w-3.5 h-3.5 rounded-full bg-teal-400/25 animate-ping opacity-70" />
      <span className="relative w-1.5 h-1.5 rounded-full bg-teal-400" />
    </span>
  );
}

export function ContactPage() {
  const params = new URLSearchParams(window.location.search);
  const submitted = params.get('success') === '1';

  return (
    <div className="bg-[#0D0F12]">

      {/* ═══ OPENING ═══ */}
      <section className="relative overflow-hidden py-20 md:py-28">
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
        <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-b from-transparent to-[#0D0F12] pointer-events-none" />

        <div className="relative max-w-6xl mx-auto px-6">
          <div className="flex items-center gap-2.5 mb-8">
            <PulseDot />
            <span className="text-[11px] font-semibold text-teal-400 uppercase tracking-widest">
              Contact · PickPulse Intelligence
            </span>
          </div>
          <h1 className="text-4xl md:text-5xl font-black text-white leading-tight tracking-tight">
            Get in touch.
          </h1>
          <p className="text-base text-slate-400 leading-relaxed mt-5 max-w-md">
            Questions about PickPulse? Reach out directly —
            we typically respond within one business day.
          </p>
        </div>
      </section>

      {/* ═══ CONTACT INFO + FORM ═══ */}
      <section className="py-14 pb-32 bg-[#0D0F12]">
        <div className="max-w-xl mx-auto px-6">

          {submitted ? (
            /* ── Success state ── */
            <div className="text-center py-20">
              <div className="w-14 h-14 rounded-2xl bg-teal-500/[0.1] border border-teal-500/[0.2] flex items-center justify-center mx-auto mb-6">
                <CheckCircle2 size={22} className="text-teal-400" />
              </div>
              <h2 className="text-2xl font-bold text-white mb-3">Message sent.</h2>
              <p className="text-slate-500 text-sm">
                We typically reply within one business day.
              </p>
            </div>
          ) : (
            <>
              {/* ── Contact methods ── */}
              <div className="space-y-2 mb-10">
                {/* Email */}
                <a
                  href="mailto:hello@pickpulse.co"
                  className="flex items-center gap-3.5 p-4 bg-white/[0.03] border border-white/[0.08] rounded-xl hover:border-white/[0.14] transition-colors group"
                >
                  <div className="w-8 h-8 rounded-xl bg-teal-500/[0.1] border border-teal-500/[0.18] flex items-center justify-center shrink-0">
                    <Mail size={14} className="text-teal-400" />
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-600 uppercase tracking-widest font-semibold mb-0.5">
                      Email
                    </p>
                    <p className="text-sm font-semibold text-slate-300 group-hover:text-white transition-colors">
                      hello@pickpulse.co
                    </p>
                  </div>
                </a>

                {/* LinkedIn */}
                <a
                  href="https://www.linkedin.com/in/nathan-l-086501405/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-3.5 p-4 bg-white/[0.03] border border-white/[0.08] rounded-xl hover:border-white/[0.14] transition-colors group"
                >
                  <div className="w-8 h-8 rounded-xl bg-white/[0.05] border border-white/[0.08] flex items-center justify-center shrink-0">
                    <Linkedin size={14} className="text-slate-500 group-hover:text-white transition-colors" />
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-600 uppercase tracking-widest font-semibold mb-0.5">
                      LinkedIn
                    </p>
                    <p className="text-sm font-semibold text-slate-400 group-hover:text-white transition-colors">
                      Connect on LinkedIn
                    </p>
                  </div>
                </a>
              </div>

              {/* ── Form ── */}
              <form
                name="contact"
                method="POST"
                data-netlify="true"
                netlify-honeypot="bot-field"
                action="/contact?success=1"
                className="space-y-5"
              >
                <input type="hidden" name="form-name" value="contact" />
                <input type="hidden" name="bot-field" />

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-1.5">
                    Name
                  </label>
                  <input
                    type="text"
                    name="name"
                    required
                    placeholder="Jane Smith"
                    className="w-full px-4 py-3 bg-[#131720] border border-white/[0.1] rounded-xl text-sm text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500/40 transition-colors"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-1.5">
                    Email
                  </label>
                  <input
                    type="email"
                    name="email"
                    required
                    placeholder="jane@company.com"
                    className="w-full px-4 py-3 bg-[#131720] border border-white/[0.1] rounded-xl text-sm text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500/40 transition-colors"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-1.5">
                    Subject
                  </label>
                  <input
                    type="text"
                    name="subject"
                    placeholder="General inquiry"
                    className="w-full px-4 py-3 bg-[#131720] border border-white/[0.1] rounded-xl text-sm text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500/40 transition-colors"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-1.5">
                    Message
                  </label>
                  <textarea
                    name="message"
                    rows={5}
                    required
                    placeholder="How can we help?"
                    className="w-full px-4 py-3 bg-[#131720] border border-white/[0.1] rounded-xl text-sm text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500/40 transition-colors resize-none"
                  />
                </div>

                <button
                  type="submit"
                  className="w-full flex items-center justify-center gap-2 px-6 py-3.5 bg-teal-500 text-white rounded-lg text-sm font-bold hover:bg-teal-400 transition-colors shadow-lg shadow-teal-500/20"
                >
                  <Send size={14} />
                  Send Message
                </button>
              </form>
            </>
          )}
        </div>
      </section>

    </div>
  );
}
