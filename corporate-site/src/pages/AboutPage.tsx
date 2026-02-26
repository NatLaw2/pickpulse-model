import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

export function AboutPage() {
  return (
    <div>
      {/* Hero */}
      <section className="bg-gradient-to-br from-indigo-50 via-white to-violet-50 py-20">
        <div className="max-w-6xl mx-auto px-6">
          <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight">About PickPulse Intelligence</h1>
          <h2 className="text-xl font-semibold text-slate-700 mt-4">Built by an Operator. Designed for Revenue Teams.</h2>
          <p className="text-lg text-slate-600 mt-6 max-w-3xl leading-relaxed">
            PickPulse Intelligence was founded to solve a simple but expensive problem:
            Most SaaS companies do not know which customers are actually at risk until it is too late.
          </p>
          <p className="text-lg text-slate-600 mt-4 max-w-3xl leading-relaxed">
            After leading revenue and partnership initiatives inside high-growth environments including GoDaddy, Amazon, and Zillow, I saw the same pattern repeatedly:
          </p>
          <div className="mt-6 max-w-3xl space-y-2">
            <p className="text-lg text-slate-600">Teams had data.</p>
            <p className="text-lg text-slate-600">They had dashboards.</p>
            <p className="text-lg text-slate-600">They had reports.</p>
          </div>
          <p className="text-lg text-slate-700 font-medium mt-6 max-w-3xl">
            What they did not have was clear prioritization.
          </p>
          <div className="mt-6 max-w-3xl space-y-2">
            <p className="text-lg text-slate-600">Customer success managers were working hard.</p>
            <p className="text-lg text-slate-600">But they were not always working on the right accounts.</p>
          </div>
          <p className="text-lg text-slate-700 font-semibold mt-6 max-w-3xl">
            PickPulse was built to fix that.
          </p>
        </div>
      </section>

      {/* The Founder */}
      <section className="py-20 bg-white">
        <div className="max-w-6xl mx-auto px-6">
          <h2 className="text-2xl font-bold text-slate-900 mb-3">The Founder</h2>
          <div className="max-w-3xl">
            <p className="text-lg font-semibold text-slate-900">Nathan Lawrence</p>
            <p className="text-sm text-slate-500 mb-6">Founder, PickPulse Intelligence</p>
            <p className="text-slate-600 leading-relaxed mb-4">
              I have spent my career building and scaling revenue systems inside fast-moving organizations. I have led teams, managed pipeline accountability, and designed frameworks that improve performance through clarity and prioritization.
            </p>
            <div className="space-y-2 mb-6">
              <p className="text-slate-600">PickPulse is not an academic experiment.</p>
              <p className="text-slate-700 font-medium">It is an operator-built churn intelligence engine.</p>
            </div>
            <p className="text-slate-700 font-medium mb-4">The mission is simple:</p>
            <ul className="space-y-2 text-slate-600 mb-6">
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                Identify risk earlier
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                Prioritize accounts intelligently
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                Give revenue teams clarity on where to act
              </li>
            </ul>
            <p className="text-slate-600">
              This platform was built from real-world operating experience, not theory.
            </p>
          </div>
        </div>
      </section>

      {/* Why PickPulse Exists */}
      <section className="py-20 bg-slate-50">
        <div className="max-w-6xl mx-auto px-6">
          <h2 className="text-2xl font-bold text-slate-900 mb-6">Why PickPulse Exists</h2>
          <div className="max-w-3xl">
            <p className="text-slate-600 mb-4">Most churn tools require:</p>
            <ul className="space-y-2 text-slate-600 mb-8">
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                Heavy integrations
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                Months of implementation
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                Complex dashboards
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                Large upfront contracts
              </li>
            </ul>
            <p className="text-slate-700 font-semibold mb-6">PickPulse takes a different approach.</p>
            <p className="text-slate-600 mb-6">You do not need a six-month deployment to start understanding risk.</p>
            <p className="text-slate-600 mb-4">You need:</p>
            <ul className="space-y-2 text-slate-600 mb-6">
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                The right data
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                A clean model
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-600 mt-1">&#8226;</span>
                A clear priority list
              </li>
            </ul>
            <p className="text-slate-700 font-semibold">That is what we deliver.</p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 bg-gradient-to-br from-indigo-600 to-violet-600">
        <div className="max-w-3xl mx-auto px-6 text-center">
          <h2 className="text-3xl font-bold text-white">Ready to See It In Action?</h2>
          <p className="text-indigo-100 mt-4 text-lg">
            See how PickPulse can prioritize your at-risk accounts.
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
