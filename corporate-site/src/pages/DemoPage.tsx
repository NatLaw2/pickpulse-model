import { useState } from 'react';
import { Send, CheckCircle2 } from 'lucide-react';

export function DemoPage() {
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
  };

  return (
    <div>
      <section className="bg-gradient-to-br from-indigo-50 via-white to-violet-50 py-20">
        <div className="max-w-6xl mx-auto px-6">
          <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight">Request a Demo</h1>
          <p className="text-lg text-slate-600 mt-4 max-w-2xl leading-relaxed">
            See how PickPulse Intelligence can identify at-risk accounts and quantify revenue exposure
            for your business. We typically respond within one business day.
          </p>
        </div>
      </section>

      <section className="py-16">
        <div className="max-w-xl mx-auto px-6">
          {submitted ? (
            <div className="text-center py-12">
              <CheckCircle2 size={48} className="mx-auto text-emerald-500 mb-4" />
              <h2 className="text-2xl font-bold text-slate-900 mb-2">Thank You</h2>
              <p className="text-slate-600">
                We have received your request and will be in touch within one business day.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">First Name</label>
                  <input
                    type="text"
                    required
                    className="w-full px-4 py-3 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                    placeholder="Jane"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">Last Name</label>
                  <input
                    type="text"
                    required
                    className="w-full px-4 py-3 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                    placeholder="Smith"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">Work Email</label>
                <input
                  type="email"
                  required
                  className="w-full px-4 py-3 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                  placeholder="jane@company.com"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">Company</label>
                <input
                  type="text"
                  required
                  className="w-full px-4 py-3 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                  placeholder="Acme Corp"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">Number of Accounts</label>
                <select className="w-full px-4 py-3 border border-slate-300 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500">
                  <option value="">Select range</option>
                  <option value="<500">Under 500</option>
                  <option value="500-2000">500 - 2,000</option>
                  <option value="2000-10000">2,000 - 10,000</option>
                  <option value="10000+">10,000+</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">What are you looking to solve?</label>
                <textarea
                  rows={3}
                  className="w-full px-4 py-3 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 resize-none"
                  placeholder="E.g., We want to reduce gross churn by identifying at-risk accounts earlier..."
                />
              </div>

              <button
                type="submit"
                className="w-full flex items-center justify-center gap-2 px-6 py-3.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-600/20"
              >
                <Send size={16} />
                Submit Request
              </button>

              <p className="text-xs text-slate-400 text-center">
                No commitment required. We will walk you through the platform using your data or our sample dataset.
              </p>
            </form>
          )}
        </div>
      </section>
    </div>
  );
}
