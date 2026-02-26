import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

export function OnboardingPage() {
  return (
    <div>
      {/* Hero */}
      <section className="bg-gradient-to-br from-indigo-50 via-white to-violet-50 py-20">
        <div className="max-w-6xl mx-auto px-6">
          <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight">How Onboarding Works</h1>
          <p className="text-lg text-slate-600 mt-4 max-w-2xl leading-relaxed">
            PickPulse is designed to be lightweight and fast to deploy.
          </p>
          <p className="text-lg text-slate-600 mt-4 max-w-2xl leading-relaxed">
            Most pilots are live within 7 to 14 days.
          </p>
          <p className="text-lg text-slate-600 mt-4 max-w-2xl leading-relaxed">
            We provide a clean data template to make onboarding simple.
          </p>
        </div>
      </section>

      {/* What Data Is Required */}
      <section className="py-20 bg-white">
        <div className="max-w-6xl mx-auto px-6">
          <h2 className="text-2xl font-bold text-slate-900 mb-3">What Data Is Required</h2>
          <div className="max-w-3xl">
            <p className="text-slate-600 mb-2 leading-relaxed">
              We start with a structured export from your CRM or billing system.
            </p>
            <p className="text-slate-600 mb-6 leading-relaxed">
              Our template makes it easy to map fields.
            </p>
            <p className="text-slate-600 mb-4">At minimum, we typically need:</p>
            <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6 mb-6">
              <ul className="space-y-2 text-slate-600">
                <li className="flex items-start gap-2">
                  <span className="text-indigo-600 mt-1">&#8226;</span>
                  Account ID
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-indigo-600 mt-1">&#8226;</span>
                  ARR or MRR
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-indigo-600 mt-1">&#8226;</span>
                  Contract start date
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-indigo-600 mt-1">&#8226;</span>
                  Renewal date
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-indigo-600 mt-1">&#8226;</span>
                  Account status
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-indigo-600 mt-1">&#8226;</span>
                  Customer segment or industry
                </li>
              </ul>
            </div>
            <p className="text-slate-700 font-medium">That is enough to establish a strong baseline model.</p>
          </div>
        </div>
      </section>

      {/* Optional Data */}
      <section className="py-20 bg-slate-50">
        <div className="max-w-6xl mx-auto px-6">
          <h2 className="text-2xl font-bold text-slate-900 mb-3">Data That Improves Accuracy (Optional)</h2>
          <div className="max-w-3xl">
            <p className="text-slate-600 mb-6">
              If available, these signals can further enhance predictions:
            </p>
            <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-6">
              <ul className="space-y-2 text-slate-600">
                <li className="flex items-start gap-2">
                  <span className="text-indigo-600 mt-1">&#8226;</span>
                  Product usage metrics
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-indigo-600 mt-1">&#8226;</span>
                  Support ticket volume
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-indigo-600 mt-1">&#8226;</span>
                  Payment history
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-indigo-600 mt-1">&#8226;</span>
                  NPS or CSAT scores
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-indigo-600 mt-1">&#8226;</span>
                  Seat counts or license data
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-indigo-600 mt-1">&#8226;</span>
                  Expansion or downgrade history
                </li>
              </ul>
            </div>
            <p className="text-slate-600">These are helpful but not required to begin.</p>
          </div>
        </div>
      </section>

      {/* Implementation Timeline */}
      <section className="py-20 bg-white">
        <div className="max-w-6xl mx-auto px-6">
          <h2 className="text-2xl font-bold text-slate-900 mb-10">Implementation Timeline</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-4xl">
            <div className="border border-slate-200 rounded-2xl p-6 hover:border-indigo-200 transition-colors">
              <div className="w-10 h-10 rounded-xl bg-indigo-100 text-indigo-600 flex items-center justify-center mb-4 text-sm font-bold">
                W1
              </div>
              <h3 className="font-semibold text-slate-900 mb-2">Week 1</h3>
              <p className="text-sm text-slate-500 leading-relaxed">
                Data export, model training, baseline validation
              </p>
            </div>
            <div className="border border-slate-200 rounded-2xl p-6 hover:border-indigo-200 transition-colors">
              <div className="w-10 h-10 rounded-xl bg-indigo-100 text-indigo-600 flex items-center justify-center mb-4 text-sm font-bold">
                W2
              </div>
              <h3 className="font-semibold text-slate-900 mb-2">Week 2</h3>
              <p className="text-sm text-slate-500 leading-relaxed">
                Risk calibration and executive review
              </p>
            </div>
            <div className="border border-slate-200 rounded-2xl p-6 hover:border-indigo-200 transition-colors">
              <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-600 flex items-center justify-center mb-4 text-sm font-bold">
                &#8734;
              </div>
              <h3 className="font-semibold text-slate-900 mb-2">Ongoing</h3>
              <p className="text-sm text-slate-500 leading-relaxed">
                Weekly refreshed risk lists and executive reporting
              </p>
            </div>
          </div>
          <p className="text-slate-600 mt-8 max-w-3xl">No heavy engineering lift required.</p>
        </div>
      </section>

      {/* How This Is Different */}
      <section className="py-20 bg-slate-50">
        <div className="max-w-6xl mx-auto px-6">
          <h2 className="text-2xl font-bold text-slate-900 mb-6">How This Is Different</h2>
          <div className="max-w-3xl">
            <ul className="space-y-3 text-slate-600 mb-8">
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                No multi-month integration process
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                No complicated deployment
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                Operator-led implementation
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                Prioritized action lists, not just dashboards
              </li>
            </ul>
            <p className="text-slate-700 font-semibold text-lg">Start simple. Scale intelligently.</p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 bg-gradient-to-br from-indigo-600 to-violet-600">
        <div className="max-w-3xl mx-auto px-6 text-center">
          <h2 className="text-3xl font-bold text-white">Ready to Get Started?</h2>
          <p className="text-indigo-100 mt-4 text-lg">
            Most pilots are live within two weeks. Let us show you how.
          </p>
          <Link
            to="/demo"
            className="inline-flex items-center gap-2 mt-8 px-8 py-4 bg-white text-indigo-700 rounded-xl text-sm font-bold hover:bg-indigo-50 transition-colors shadow-lg"
          >
            Request a Demo <ArrowRight size={16} />
          </Link>
        </div>
      </section>
    </div>
  );
}
