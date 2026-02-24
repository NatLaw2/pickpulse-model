import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Database, Brain, BarChart3,
  Crosshair, Code2, ListChecks, FileText, ShieldAlert
} from 'lucide-react';
import { useDataset } from '../lib/DatasetContext';

const links = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/datasets', icon: Database, label: 'Datasets' },
  { to: '/train', icon: Brain, label: 'Train' },
  { to: '/evaluate', icon: BarChart3, label: 'Evaluate' },
  { to: '/predict', icon: Crosshair, label: 'Predict' },
  { to: '/api-docs', icon: Code2, label: 'API' },
  { to: '/onboarding', icon: ListChecks, label: 'Onboarding' },
  { to: '/reports', icon: FileText, label: 'Reports' },
];

export function Sidebar() {
  const { dataset } = useDataset();

  return (
    <aside className="fixed left-0 top-0 h-screen w-56 bg-[var(--color-bg-secondary)] border-r border-[var(--color-border)] flex flex-col z-30">
      <div className="px-5 py-5 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2">
          <ShieldAlert size={18} className="text-[var(--color-accent)]" />
          <h1 className="text-sm font-bold tracking-wide text-[var(--color-accent-glow)]">
            PICKPULSE
          </h1>
        </div>
        <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5 tracking-widest uppercase">
          Intelligence
        </p>
      </div>

      {/* Demo badge */}
      {dataset?.is_demo && (
        <div
          className="mx-3 mt-3 px-3 py-2 bg-[var(--color-warning)]/10 border border-[var(--color-warning)]/25 rounded-xl text-center"
          title="Illustrative metrics generated from a sample dataset. Upload your own data for production-grade insights."
        >
          <span className="text-[10px] font-bold tracking-widest uppercase text-[var(--color-warning)]">
            Demo Dataset
          </span>
        </div>
      )}

      {/* Dataset indicator */}
      {dataset && (
        <div className="mx-3 mt-3 px-3 py-2 bg-[rgba(255,255,255,0.04)] rounded-xl">
          <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider">Dataset</div>
          <div className="text-xs text-[var(--color-text-secondary)] truncate mt-0.5" title={dataset.name}>
            {dataset.name}
          </div>
          <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5">
            {dataset.rows.toLocaleString()} rows
          </div>
        </div>
      )}

      <nav className="flex-1 py-3 space-y-0.5 px-2">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all ${
                isActive
                  ? 'bg-[var(--color-accent)]/15 text-[var(--color-accent-glow)] font-medium shadow-[0_0_0_1px_rgba(123,97,255,0.25)]'
                  : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[rgba(255,255,255,0.04)]'
              }`
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="px-4 py-3 border-t border-[var(--color-border)] text-[10px] text-[var(--color-text-muted)]">
        v1.0.0
      </div>
    </aside>
  );
}
