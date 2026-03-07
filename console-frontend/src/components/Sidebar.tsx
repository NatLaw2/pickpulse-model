import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Database, Brain,
  Crosshair, Code2, FileText, ShieldAlert, LogOut
} from 'lucide-react';
import { useDataset } from '../lib/DatasetContext';
import { useAuth } from '../lib/AuthContext';

const mainLinks = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/predict', icon: Crosshair, label: 'Accounts' },
  { to: '/reports', icon: FileText, label: 'Reports' },
];

const configLinks = [
  { to: '/data-sources', icon: Database, label: 'Data Sources' },
  { to: '/model', icon: Brain, label: 'Model' },
  { to: '/api-docs', icon: Code2, label: 'API' },
];

export function Sidebar() {
  const { dataset } = useDataset();
  const { user, signOut } = useAuth();

  return (
    <aside className="fixed left-0 top-0 h-screen w-56 bg-[var(--color-bg-sidebar)] flex flex-col z-30">
      <div className="px-5 py-5 border-b border-[rgba(255,255,255,0.1)]">
        <div className="flex items-center gap-2">
          <ShieldAlert size={18} className="text-[var(--color-accent)]" />
          <h1 className="text-sm font-bold tracking-wide text-[var(--color-accent)]">
            PICKPULSE
          </h1>
        </div>
        <p className="text-[10px] text-[var(--color-sidebar-text-muted)] mt-0.5 tracking-widest uppercase">
          Intelligence
        </p>
        <p className="text-[9px] text-[var(--color-sidebar-text-muted)] mt-1 tracking-wide">
          Churn Risk Module
        </p>
      </div>

      {/* Demo environment banner */}
      <div className="mx-3 mt-3 px-3 py-1.5 bg-[var(--color-accent)]/8 border border-[var(--color-accent)]/20 rounded-lg text-center">
        <span className="text-[9px] font-semibold tracking-widest uppercase text-[var(--color-accent)]">
          Demo Environment
        </span>
      </div>

      {/* Sample data badge */}
      {dataset?.is_demo && (
        <div
          className="mx-3 mt-2 px-3 py-2 bg-[var(--color-warning)]/10 border border-[var(--color-warning)]/25 rounded-xl text-center"
          title="Illustrative metrics generated from a sample dataset. Upload your own data for production-grade insights."
        >
          <span className="text-[10px] font-bold tracking-widest uppercase text-[var(--color-warning)]">
            Sample Data
          </span>
        </div>
      )}

      {/* Dataset indicator */}
      {dataset && (
        <div className="mx-3 mt-2 px-3 py-2 bg-[rgba(255,255,255,0.06)] rounded-xl">
          <div className="text-[10px] text-[var(--color-sidebar-text-muted)] uppercase tracking-wider">Dataset</div>
          <div className="text-xs text-[var(--color-sidebar-text)] truncate mt-0.5" title={dataset.name}>
            {dataset.name}
          </div>
          <div className="text-[10px] text-[var(--color-sidebar-text-muted)] mt-0.5">
            {dataset.rows.toLocaleString()} rows
          </div>
        </div>
      )}

      <nav className="flex-1 py-3 px-2 overflow-y-auto">
        <div className="space-y-0.5">
          {mainLinks.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all ${
                  isActive
                    ? 'bg-[var(--color-bg-sidebar-active)] text-[var(--color-accent)] font-medium shadow-[0_0_0_1px_rgba(123,97,255,0.25)]'
                    : 'text-[var(--color-sidebar-text)] hover:text-white hover:bg-[var(--color-bg-sidebar-hover)]'
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </div>

        <div className="mt-5 mb-2 px-3">
          <span className="text-[9px] font-semibold tracking-widest uppercase text-[var(--color-sidebar-text-muted)]">
            Configuration
          </span>
        </div>

        <div className="space-y-0.5">
          {configLinks.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all ${
                  isActive
                    ? 'bg-[var(--color-bg-sidebar-active)] text-[var(--color-accent)] font-medium shadow-[0_0_0_1px_rgba(123,97,255,0.25)]'
                    : 'text-[var(--color-sidebar-text)] hover:text-white hover:bg-[var(--color-bg-sidebar-hover)]'
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </div>
      </nav>
      <div className="px-4 py-3 border-t border-[rgba(255,255,255,0.1)]">
        {user && (
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-[var(--color-sidebar-text-muted)] truncate max-w-[120px]" title={user.email}>
              {user.email}
            </span>
            <button
              onClick={() => signOut()}
              className="p-1 text-[var(--color-sidebar-text-muted)] hover:text-red-400 transition-colors"
              title="Sign out"
            >
              <LogOut size={13} />
            </button>
          </div>
        )}
        <div className="text-[10px] text-[var(--color-sidebar-text-muted)] mt-1">v1.0.0</div>
      </div>
    </aside>
  );
}
