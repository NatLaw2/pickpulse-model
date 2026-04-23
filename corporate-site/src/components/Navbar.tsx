import { Link, NavLink } from 'react-router-dom';
import { useState } from 'react';
import { Menu, X } from 'lucide-react';

const links = [
  { to: '/', label: 'Home' },
  { to: '/onboarding', label: 'How It Works' },
  { to: '/about', label: 'About' },
  { to: '/contact', label: 'Contact' },
];

export function Navbar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 bg-[#0D0F12]/95 backdrop-blur-md border-b border-white/[0.08]">
      <div className="max-w-6xl mx-auto flex items-center justify-between px-6 py-4">
        <Link to="/" className="flex items-center">
          <img
            src="/PickPulse Logo.png"
            alt="PickPulse Intelligence"
            className="h-16 brightness-110"
          />
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-8">
          {links.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `text-sm font-medium transition-colors ${
                  isActive ? 'text-white' : 'text-slate-400 hover:text-white'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
          <a
            href="https://demo.pickpulse.co"
            className="text-sm font-medium text-slate-400 hover:text-white transition-colors"
          >
            Sign In
          </a>
          <Link
            to="/demo"
            className="px-5 py-2 bg-teal-500 text-white rounded-lg text-sm font-semibold hover:bg-teal-400 transition-colors shadow-lg shadow-teal-500/20"
          >
            Book a Demo
          </Link>
        </nav>

        <button
          className="md:hidden p-2 text-slate-400 hover:text-white transition-colors"
          onClick={() => setOpen(!open)}
        >
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {open && (
        <div className="md:hidden border-t border-white/[0.08] bg-[#0D0F12] px-6 py-5 space-y-1">
          {links.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setOpen(false)}
              className="block py-2.5 text-sm font-medium text-slate-400 hover:text-white transition-colors"
            >
              {label}
            </NavLink>
          ))}
          <div className="pt-4 border-t border-white/[0.08] space-y-3 mt-2">
            <a
              href="https://demo.pickpulse.co"
              onClick={() => setOpen(false)}
              className="block text-center px-4 py-2.5 text-sm font-medium text-slate-400 border border-white/[0.12] rounded-lg hover:text-white hover:border-white/20 transition-colors"
            >
              Sign In
            </a>
            <Link
              to="/demo"
              onClick={() => setOpen(false)}
              className="block text-center px-5 py-2.5 bg-teal-500 text-white rounded-lg text-sm font-semibold hover:bg-teal-400 transition-colors"
            >
              Book a Demo
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}
