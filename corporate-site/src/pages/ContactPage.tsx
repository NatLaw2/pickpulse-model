import { useState } from 'react';
import { Mail, Send, CheckCircle2 } from 'lucide-react';

export function ContactPage() {
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
  };

  return (
    <div>
      <section className="bg-gradient-to-br from-indigo-50 via-white to-violet-50 py-20">
        <div className="max-w-6xl mx-auto px-6">
          <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight">Contact</h1>
          <p className="text-lg text-slate-600 mt-4 max-w-2xl leading-relaxed">
            Questions about PickPulse Intelligence? Reach out and we will get back to you promptly.
          </p>
        </div>
      </section>

      <section className="py-16">
        <div className="max-w-xl mx-auto px-6">
          {submitted ? (
            <div className="text-center py-12">
              <CheckCircle2 size={48} className="mx-auto text-emerald-500 mb-4" />
              <h2 className="text-2xl font-bold text-slate-900 mb-2">Message Sent</h2>
              <p className="text-slate-600">Thank you. We will reply within one business day.</p>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3 mb-8 p-4 bg-slate-50 rounded-xl border border-slate-100">
                <Mail size={20} className="text-indigo-600" />
                <span className="text-sm text-slate-700">hello@pickpulse.co</span>
              </div>

              <form onSubmit={handleSubmit} className="space-y-5">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">Name</label>
                  <input
                    type="text"
                    required
                    className="w-full px-4 py-3 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                    placeholder="Jane Smith"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">Email</label>
                  <input
                    type="email"
                    required
                    className="w-full px-4 py-3 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                    placeholder="jane@company.com"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">Subject</label>
                  <input
                    type="text"
                    className="w-full px-4 py-3 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                    placeholder="General inquiry"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">Message</label>
                  <textarea
                    rows={5}
                    required
                    className="w-full px-4 py-3 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 resize-none"
                    placeholder="How can we help?"
                  />
                </div>

                <button
                  type="submit"
                  className="w-full flex items-center justify-center gap-2 px-6 py-3.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-600/20"
                >
                  <Send size={16} />
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
