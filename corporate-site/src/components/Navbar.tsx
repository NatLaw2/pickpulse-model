import { Link, NavLink } from 'react-router-dom';
import { useState } from 'react';
import { Menu, X } from 'lucide-react';

const links = [
  { to: '/modules', label: 'Modules' },
  { to: '/modules/churn', label: 'Churn' },
  { to: '/contact', label: 'Contact' },
];

export function Navbar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 bg-white/90 backdrop-blur-md border-b border-slate-200">
      <div className="max-w-6xl mx-auto flex items-center justify-between px-6 py-4">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center text-white font-bold text-sm">
            P
          </div>
          <span className="text-lg font-bold text-slate-900 tracking-tight">
            PickPulse<span className="text-indigo-600"> Intelligence</span>
          </span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-8">
          {links.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `text-sm font-medium transition-colors ${isActive ? 'text-indigo-600' : 'text-slate-600 hover:text-slate-900'}`
              }
            >
              {label}
            </NavLink>
          ))}
          <Link
            to="/demo"
            className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors shadow-sm"
          >
            Request a Demo
          </Link>
        </nav>

        {/* Mobile toggle */}
        <button className="md:hidden p-2" onClick={() => setOpen(!open)}>
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile nav */}
      {open && (
        <div className="md:hidden border-t border-slate-200 bg-white px-6 py-4 space-y-3">
          {links.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setOpen(false)}
              className="block text-sm font-medium text-slate-700 hover:text-indigo-600"
            >
              {label}
            </NavLink>
          ))}
          <Link
            to="/demo"
            onClick={() => setOpen(false)}
            className="block text-center px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold"
          >
            Request a Demo
          </Link>
        </div>
      )}
    </header>
  );
}
