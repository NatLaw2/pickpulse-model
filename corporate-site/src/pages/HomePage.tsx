import { Link } from 'react-router-dom';
import { Shield, TrendingUp, BarChart3, Zap, ArrowRight } from 'lucide-react';

export function HomePage() {
  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-50 via-white to-violet-50" />
        <div className="relative max-w-6xl mx-auto px-6 pt-20 pb-24 md:pt-28 md:pb-32">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-indigo-100 text-indigo-700 rounded-full text-xs font-semibold mb-6">
              <Zap size={12} />
              Module 1 — Churn Risk Engine — Now Available
            </div>
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold text-slate-900 leading-tight tracking-tight">
              Know which accounts will churn&mdash;
              <span className="text-indigo-600">before they do.</span>
            </h1>
            <p className="text-lg md:text-xl text-slate-600 mt-6 max-w-2xl leading-relaxed">
              PickPulse Intelligence is a decision ranking engine that quantifies risk and revenue exposure
              at the account level. Calibrated predictions. Prioritized outreach. Protected ARR.
            </p>
            <div className="flex flex-wrap gap-4 mt-8">
              <Link
                to="/demo"
                className="inline-flex items-center gap-2 px-7 py-3.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-600/20"
              >
                Request a Demo
                <ArrowRight size={16} />
              </Link>
              <Link
                to="/modules/churn"
                className="inline-flex items-center gap-2 px-7 py-3.5 bg-white border border-slate-300 text-slate-700 rounded-xl text-sm font-semibold hover:border-indigo-300 hover:text-indigo-600 transition-colors"
              >
                View Churn Module
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* What It Does */}
      <section className="py-20 bg-white">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-bold text-slate-900">What PickPulse Does</h2>
            <p className="text-slate-500 mt-3 max-w-2xl mx-auto">
              Turn your account data into ranked risk scores, actionable insights, and measurable revenue protection.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
            {[
              {
                icon: <Shield size={24} />,
                title: 'Account-Level Risk Scores',
                desc: 'Calibrated churn probabilities for every account, trained on your historical data.',
              },
              {
                icon: <TrendingUp size={24} />,
                title: 'Revenue Exposure Mapping',
                desc: 'ARR at risk quantified per account. Prioritize by dollars, not guesswork.',
              },
              {
                icon: <BarChart3 size={24} />,
                title: 'Recovery Simulation',
                desc: 'Model projected recoverable ARR at different save rate assumptions.',
              },
              {
                icon: <Zap size={24} />,
                title: 'Actionable Exports',
                desc: 'Executive dashboards, PDF reports, CSV exports, and REST API. Built for operators.',
              },
            ].map((item) => (
              <div key={item.title} className="bg-slate-50 rounded-2xl p-6 border border-slate-100">
                <div className="w-12 h-12 rounded-xl bg-indigo-100 text-indigo-600 flex items-center justify-center mb-4">
                  {item.icon}
                </div>
                <h3 className="font-semibold text-slate-900 mb-2">{item.title}</h3>
                <p className="text-sm text-slate-500 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-20 bg-slate-50">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-bold text-slate-900">How It Works</h2>
            <p className="text-slate-500 mt-3">Three steps from raw data to protected revenue.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
            {[
              {
                step: '01',
                title: 'Connect',
                desc: 'Ingest account data from your CRM, billing system, product analytics, and support platforms. We handle schema mapping and feature engineering.',
              },
              {
                step: '02',
                title: 'Train',
                desc: 'PickPulse trains a gradient-boosted model specific to your data. The model is calibrated to produce accurate probabilities, not just rankings.',
              },
              {
                step: '03',
                title: 'Act',
                desc: 'Access predictions through dashboards, scheduled reports, or API. Filter by risk tier, urgency, or ARR exposure. Measure lift against random targeting.',
              },
            ].map((item) => (
              <div key={item.step} className="text-center">
                <div className="w-14 h-14 rounded-2xl bg-indigo-600 text-white flex items-center justify-center text-xl font-bold mx-auto mb-5">
                  {item.step}
                </div>
                <h3 className="text-lg font-semibold text-slate-900 mb-2">{item.title}</h3>
                <p className="text-sm text-slate-500 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Why PickPulse */}
      <section className="py-20 bg-white">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-bold text-slate-900">Why PickPulse</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mx-auto">
            {[
              { title: 'Purpose-Built for Churn', desc: 'Not a generic BI tool. PickPulse is engineered from the ground up to predict account-level churn and quantify revenue exposure.' },
              { title: 'Calibrated Probabilities', desc: 'A 70% risk score means 7 in 10 similar accounts will churn. True probabilities you can act on, not opaque scores.' },
              { title: 'Custom-Trained on Your Data', desc: 'No off-the-shelf models. The engine learns what churn looks like for your business, your cohorts, your signals.' },
              { title: 'Revenue-First Metrics', desc: 'Every dashboard prioritizes ARR impact. Filter by dollars at risk. Simulate recovery scenarios with realistic save rates.' },
            ].map((item) => (
              <div key={item.title} className="border border-slate-200 rounded-2xl p-6 hover:border-indigo-200 transition-colors">
                <h3 className="font-semibold text-slate-900 mb-2">{item.title}</h3>
                <p className="text-sm text-slate-500 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="py-20 bg-gradient-to-br from-indigo-600 to-violet-600">
        <div className="max-w-3xl mx-auto px-6 text-center">
          <h2 className="text-3xl font-bold text-white">Stop Guessing. Start Protecting.</h2>
          <p className="text-indigo-100 mt-4 text-lg">
            See how PickPulse ranks your accounts by true churn risk and models recoverable ARR.
          </p>
          <Link
            to="/demo"
            className="inline-flex items-center gap-2 mt-8 px-8 py-4 bg-white text-indigo-700 rounded-xl text-sm font-bold hover:bg-indigo-50 transition-colors shadow-lg"
          >
            Book a Demo
            <ArrowRight size={16} />
          </Link>
        </div>
      </section>
    </div>
  );
}
