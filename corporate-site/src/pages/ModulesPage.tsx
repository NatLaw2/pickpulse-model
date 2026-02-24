import { Link } from 'react-router-dom';
import { Shield, TrendingUp, HeartPulse, ArrowRight, Lock } from 'lucide-react';

export function ModulesPage() {
  return (
    <div>
      <section className="bg-gradient-to-br from-indigo-50 via-white to-violet-50 py-20">
        <div className="max-w-6xl mx-auto px-6">
          <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight">Modules</h1>
          <p className="text-lg text-slate-600 mt-4 max-w-2xl">
            PickPulse Intelligence is a modular platform. Each module is a purpose-built prediction
            engine designed for a specific business decision.
          </p>
        </div>
      </section>

      <section className="py-16">
        <div className="max-w-6xl mx-auto px-6 space-y-8">
          {/* Churn — Available */}
          <div className="border border-slate-200 rounded-2xl p-8 hover:border-indigo-200 transition-colors bg-white">
            <div className="flex items-start gap-6">
              <div className="w-14 h-14 rounded-2xl bg-indigo-100 text-indigo-600 flex items-center justify-center flex-shrink-0">
                <Shield size={28} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <h2 className="text-xl font-bold text-slate-900">Churn Risk Engine</h2>
                  <span className="px-2.5 py-1 bg-emerald-100 text-emerald-700 rounded-full text-xs font-semibold">Available</span>
                </div>
                <p className="text-slate-600 leading-relaxed mb-4">
                  Predict which accounts will churn before they do. Calibrated probabilities, urgency
                  scoring, ARR-at-risk quantification, and revenue recovery simulation — all trained on
                  your historical data.
                </p>
                <ul className="text-sm text-slate-500 space-y-1.5 mb-6">
                  <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-indigo-400" /> Account-level churn probabilities with confidence calibration</li>
                  <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-indigo-400" /> Risk tier breakdown: High / Medium / Low</li>
                  <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-indigo-400" /> Urgency scoring factoring renewal proximity</li>
                  <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-indigo-400" /> Revenue recovery simulation with adjustable save rates</li>
                  <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-indigo-400" /> Executive dashboards, PDF reports, CSV exports, REST API</li>
                </ul>
                <Link
                  to="/modules/churn"
                  className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors"
                >
                  Learn More <ArrowRight size={14} />
                </Link>
              </div>
            </div>
          </div>

          {/* Expansion — Coming Next */}
          <div className="border border-slate-200 rounded-2xl p-8 bg-slate-50/50 opacity-75">
            <div className="flex items-start gap-6">
              <div className="w-14 h-14 rounded-2xl bg-slate-100 text-slate-400 flex items-center justify-center flex-shrink-0">
                <TrendingUp size={28} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <h2 className="text-xl font-bold text-slate-400">Expansion Opportunity Scoring</h2>
                  <span className="px-2.5 py-1 bg-slate-100 text-slate-400 rounded-full text-xs font-semibold flex items-center gap-1">
                    <Lock size={10} /> Coming Next
                  </span>
                </div>
                <p className="text-slate-400 leading-relaxed">
                  Identify upsell and cross-sell candidates by scoring expansion propensity across
                  your portfolio. Prioritize accounts most likely to grow.
                </p>
              </div>
            </div>
          </div>

          <div className="border border-slate-200 rounded-2xl p-8 bg-slate-50/50 opacity-75">
            <div className="flex items-start gap-6">
              <div className="w-14 h-14 rounded-2xl bg-slate-100 text-slate-400 flex items-center justify-center flex-shrink-0">
                <HeartPulse size={28} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <h2 className="text-xl font-bold text-slate-400">Health Score Monitor</h2>
                  <span className="px-2.5 py-1 bg-slate-100 text-slate-400 rounded-full text-xs font-semibold flex items-center gap-1">
                    <Lock size={10} /> Planned
                  </span>
                </div>
                <p className="text-slate-400 leading-relaxed">
                  Continuous account health tracking with trend alerts and early warning indicators.
                  Complements churn prediction with real-time signal monitoring.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
