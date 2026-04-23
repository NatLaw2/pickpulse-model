import { Link } from 'react-router-dom';

export function Footer() {
  return (
    <footer className="bg-[#090B0E] border-t border-white/[0.08]">
      <div className="max-w-6xl mx-auto px-6 py-14">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-10">
          {/* Brand */}
          <div>
            <div className="mb-4">
              <img
                src="/PickPulse Logo.png"
                alt="PickPulse Intelligence"
                className="h-16"
              />
            </div>
            <p className="text-xs text-slate-500 leading-relaxed max-w-[210px]">
              Revenue intelligence for operators who take their number seriously.
            </p>
          </div>

          {/* Navigation */}
          <div>
            <h4 className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest mb-4">
              Navigation
            </h4>
            <ul className="space-y-2.5">
              <li>
                <Link to="/" className="text-sm text-slate-400 hover:text-white transition-colors">
                  Home
                </Link>
              </li>
              <li>
                <Link to="/onboarding" className="text-sm text-slate-400 hover:text-white transition-colors">
                  How It Works
                </Link>
              </li>
              <li>
                <a
                  href="https://demo.pickpulse.co"
                  className="text-sm text-slate-400 hover:text-white transition-colors"
                >
                  Live Demo
                </a>
              </li>
            </ul>
          </div>

          {/* Company */}
          <div>
            <h4 className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest mb-4">
              Company
            </h4>
            <ul className="space-y-2.5">
              <li>
                <Link to="/about" className="text-sm text-slate-400 hover:text-white transition-colors">
                  About
                </Link>
              </li>
              <li>
                <Link to="/contact" className="text-sm text-slate-400 hover:text-white transition-colors">
                  Contact
                </Link>
              </li>
              <li>
                <Link to="/demo" className="text-sm text-slate-400 hover:text-white transition-colors">
                  Book a Demo
                </Link>
              </li>
            </ul>
          </div>

          {/* Resources */}
          <div>
            <h4 className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest mb-4">
              Resources
            </h4>
            <ul className="space-y-2.5">
              <li>
                <Link to="/onboarding" className="text-sm text-slate-400 hover:text-white transition-colors">
                  Onboarding Guide
                </Link>
              </li>
              <li>
                <Link to="/modules/churn" className="text-sm text-slate-400 hover:text-white transition-colors">
                  Data Requirements
                </Link>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-12 pt-6 border-t border-white/[0.06]">
          <p className="text-[11px] text-slate-600 text-center">
            &copy; {new Date().getFullYear()} PickPulse Intelligence. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
