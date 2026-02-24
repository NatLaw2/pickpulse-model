import { Link } from 'react-router-dom';
import { ArrowRight, BarChart3, Download, Target, Shield, Activity } from 'lucide-react';

export function ChurnPage() {
  return (
    <div>
      {/* Hero */}
      <section className="bg-gradient-to-br from-indigo-50 via-white to-violet-50 py-20">
        <div className="max-w-6xl mx-auto px-6">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-emerald-100 text-emerald-700 rounded-full text-xs font-semibold mb-4">
            Module 1 — Available Now
          </div>
          <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight">Churn Risk Engine</h1>
          <p className="text-lg text-slate-600 mt-4 max-w-2xl leading-relaxed">
            Predict account-level churn with calibrated probabilities trained on your data.
            Quantify ARR at risk, prioritize outreach, and simulate revenue recovery.
          </p>
          <div className="flex flex-wrap gap-4 mt-8">
            <Link
              to="/demo"
              className="inline-flex items-center gap-2 px-7 py-3.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-600/20"
            >
              Request a Demo <ArrowRight size={16} />
            </Link>
            <a
              href="https://demo.pickpulse.co"
              className="inline-flex items-center gap-2 px-7 py-3.5 bg-white border border-slate-300 text-slate-700 rounded-xl text-sm font-semibold hover:border-indigo-300 hover:text-indigo-600 transition-colors"
            >
              Try Live Demo
            </a>
          </div>
        </div>
      </section>

      {/* Capabilities */}
      <section className="py-20 bg-white">
        <div className="max-w-6xl mx-auto px-6">
          <h2 className="text-2xl font-bold text-slate-900 mb-10">What You Get</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              {
                icon: <Target size={22} />,
                title: 'Calibrated Churn Predictions',
                desc: 'Every account receives a true probability estimate. A 70% score means 7 in 10 similar accounts will churn. Not an opaque index — a probability you can act on.',
              },
              {
                icon: <Shield size={22} />,
                title: 'Risk Tier Segmentation',
                desc: 'Accounts are automatically segmented into High, Medium, and Low risk tiers with associated ARR exposure, churn rates, and recommended actions.',
              },
              {
                icon: <BarChart3 size={22} />,
                title: 'Lift Analysis',
                desc: 'Understand how much better the model is than random targeting. See lift curves, decile tables, and cumulative capture rates.',
              },
              {
                icon: <Activity size={22} />,
                title: 'Urgency Scoring',
                desc: 'A composite score combining churn probability and renewal proximity. Surfaces the accounts that need immediate attention — not just high risk, but high risk soon.',
              },
              {
                icon: <Download size={22} />,
                title: 'Executive Reports & Exports',
                desc: 'PDF reports for board presentations. CSV exports for CRM import. REST API for workflow integration. Built for operators and executives.',
              },
              {
                icon: <BarChart3 size={22} />,
                title: 'Revenue Recovery Simulation',
                desc: 'Model projected recoverable ARR at different save rate assumptions. Adjust the slider from conservative (20%) to aggressive (60%) and see the impact.',
              },
            ].map((item) => (
              <div key={item.title} className="border border-slate-200 rounded-2xl p-6 hover:border-indigo-200 transition-colors">
                <div className="w-10 h-10 rounded-xl bg-indigo-100 text-indigo-600 flex items-center justify-center mb-4">
                  {item.icon}
                </div>
                <h3 className="font-semibold text-slate-900 mb-2">{item.title}</h3>
                <p className="text-sm text-slate-500 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Data Requirements */}
      <section className="py-20 bg-slate-50">
        <div className="max-w-6xl mx-auto px-6">
          <h2 className="text-2xl font-bold text-slate-900 mb-3">Data Requirements</h2>
          <p className="text-slate-500 mb-8 max-w-2xl">
            The Churn Risk Engine works with standard SaaS account data. Minimum required fields below
            — additional signals improve accuracy.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl">
            <div className="bg-white border border-slate-200 rounded-2xl p-6">
              <h3 className="text-sm font-semibold text-slate-900 mb-3">Required</h3>
              <ul className="text-sm text-slate-600 space-y-2">
                <li>Account ID</li>
                <li>Annual Recurring Revenue (ARR)</li>
                <li>Contract / renewal date</li>
                <li>Churn label (historical outcomes)</li>
              </ul>
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl p-6">
              <h3 className="text-sm font-semibold text-slate-900 mb-3">Recommended</h3>
              <ul className="text-sm text-slate-600 space-y-2">
                <li>Monthly active users / login frequency</li>
                <li>Support ticket count and severity</li>
                <li>NPS / CSAT scores</li>
                <li>Payment history and billing method</li>
                <li>Account tier / segment</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Success Metrics */}
      <section className="py-20 bg-white">
        <div className="max-w-6xl mx-auto px-6">
          <h2 className="text-2xl font-bold text-slate-900 mb-8">Typical Performance</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {[
              { metric: 'AUC', value: '> 0.80', desc: 'Strong discrimination' },
              { metric: 'Lift @ Top 10%', value: '> 3.0x', desc: 'vs. random targeting' },
              { metric: 'Calibration Error', value: '< 5%', desc: 'Reliable probabilities' },
              { metric: 'Time to Live', value: '2-4 weeks', desc: 'Data to dashboard' },
            ].map((item) => (
              <div key={item.metric} className="text-center p-6 bg-slate-50 rounded-2xl border border-slate-100">
                <div className="text-3xl font-extrabold text-indigo-600">{item.value}</div>
                <div className="text-sm font-semibold text-slate-900 mt-2">{item.metric}</div>
                <div className="text-xs text-slate-400 mt-1">{item.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 bg-gradient-to-br from-indigo-600 to-violet-600">
        <div className="max-w-3xl mx-auto px-6 text-center">
          <h2 className="text-3xl font-bold text-white">Ready to See It In Action?</h2>
          <p className="text-indigo-100 mt-4 text-lg">
            We will walk you through the Churn Risk Engine using your data or our sample dataset.
          </p>
          <Link
            to="/demo"
            className="inline-flex items-center gap-2 mt-8 px-8 py-4 bg-white text-indigo-700 rounded-xl text-sm font-bold hover:bg-indigo-50 transition-colors shadow-lg"
          >
            Book a Demo <ArrowRight size={16} />
          </Link>
        </div>
      </section>
    </div>
  );
}
