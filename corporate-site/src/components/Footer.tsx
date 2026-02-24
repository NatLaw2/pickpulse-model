import { Link } from 'react-router-dom';

export function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-slate-50">
      <div className="max-w-6xl mx-auto px-6 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center text-white font-bold text-xs">
                P
              </div>
              <span className="text-sm font-bold text-slate-900">PickPulse Intelligence</span>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed">
              Decision ranking engine that quantifies risk and revenue exposure for B2B teams.
            </p>
          </div>

          <div>
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Product</h4>
            <ul className="space-y-2 text-sm">
              <li><Link to="/modules" className="text-slate-600 hover:text-indigo-600">Modules</Link></li>
              <li><Link to="/modules/churn" className="text-slate-600 hover:text-indigo-600">Churn Risk</Link></li>
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Company</h4>
            <ul className="space-y-2 text-sm">
              <li><Link to="/demo" className="text-slate-600 hover:text-indigo-600">Request a Demo</Link></li>
              <li><Link to="/contact" className="text-slate-600 hover:text-indigo-600">Contact</Link></li>
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Resources</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="https://demo.pickpulse.co" className="text-slate-600 hover:text-indigo-600">Live Demo</a></li>
            </ul>
          </div>
        </div>

        <div className="mt-10 pt-6 border-t border-slate-200 text-xs text-slate-400 text-center">
          &copy; {new Date().getFullYear()} PickPulse Intelligence. All rights reserved.
        </div>
      </div>
    </footer>
  );
}
