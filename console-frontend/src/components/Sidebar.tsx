import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Brain,
  Crosshair, Code2, FileText, ShieldAlert, LogOut,
  RotateCcw, Loader2, FlaskConical,
} from 'lucide-react';
import { api } from '../lib/api';
import { useDataset } from '../lib/DatasetContext';
import { usePredictions } from '../lib/PredictionContext';
import { useAuth } from '../lib/AuthContext';
import { useExecutiveSummary } from '../lib/ExecutiveSummaryContext';
import { useActiveMode, type ActiveMode } from '../lib/ActiveModeContext';

// Primary navigation — never includes Data Sources (accessed via Welcome page)
const mainLinks = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/predict', icon: Crosshair, label: 'Accounts' },
  { to: '/reports', icon: FileText, label: 'Reports' },
];

// Configuration links — model management and API docs
const configLinks = [
  { to: '/model', icon: Brain, label: 'Model' },
  { to: '/api-docs', icon: Code2, label: 'API' },
];

const MODE_LABELS: Record<Exclude<ActiveMode, 'none'>, string> = {
  salesforce: 'Salesforce',
  hubspot: 'HubSpot',
  csv: 'CSV Upload',
};

export function Sidebar() {
  const { dataset, refresh } = useDataset();
  const { clearPredictions } = usePredictions();
  const { user, signOut } = useAuth();
  const { clearSummary } = useExecutiveSummary();
  const { mode, setMode } = useActiveMode();
  const navigate = useNavigate();

  const [resetting, setResetting] = useState(false);
  const [resetToast, setResetToast] = useState(false);

  const handleReset = async () => {
    if (!window.confirm('Reset to a clean state? This removes all data, models, predictions, and the active workflow mode.')) return;

    setResetting(true);
    try {
      await api.resetDemo();
      clearPredictions();
      clearSummary();
      refresh();
      // Clear the active mode — returns the app to the welcome page
      await setMode('none');
      setResetToast(true);
      setTimeout(() => setResetToast(false), 3000);
      navigate('/');
    } catch (err: any) {
      console.error('[reset] failed:', err);
      alert(err?.message || 'Reset failed');
    } finally {
      setResetting(false);
    }
  };

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

      {/* Active mode indicator + reset */}
      <div className="mx-3 mt-3 px-3 py-1.5 bg-[var(--color-accent)]/8 border border-[var(--color-accent)]/20 rounded-lg flex items-center justify-between">
        <span className="text-[9px] font-semibold tracking-widest uppercase text-[var(--color-accent)]">
          {mode !== 'none' ? MODE_LABELS[mode] : 'No Source'}
        </span>
        <button
          onClick={handleReset}
          disabled={resetting}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium text-[var(--color-sidebar-text-muted)] hover:text-white transition-colors disabled:opacity-50"
          title="Reset to clean state and return to source selection"
        >
          {resetting ? <Loader2 size={10} className="animate-spin" /> : <RotateCcw size={10} />}
          Reset
        </button>
      </div>

      {/* Reset success toast */}
      {resetToast && (
        <div className="mx-3 mt-2 px-3 py-2 bg-[var(--color-success)]/15 border border-[var(--color-success)]/25 rounded-lg text-center">
          <span className="text-[10px] font-medium text-[var(--color-success)]">
            Reset complete. Select a data source to begin.
          </span>
        </div>
      )}

      {/* Sample data badge (CSV demo data) */}
      {dataset?.is_demo && (
        <div
          className="mx-3 mt-2 px-3 py-2 bg-[var(--color-warning)]/10 border border-[var(--color-warning)]/25 rounded-xl text-center"
          title="Illustrative metrics from a sample dataset."
        >
          <span className="text-[10px] font-bold tracking-widest uppercase text-[var(--color-warning)]">
            Sample Data
          </span>
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

      {/* Labs — visually separated from production nav */}
      <div className="px-2 pb-2">
        <div className="border-t border-[rgba(255,255,255,0.08)] pt-3 mt-1">
          <div className="mb-1.5 px-3">
            <span className="text-[9px] font-semibold tracking-widest uppercase text-[rgba(255,255,255,0.25)]">
              Labs
            </span>
          </div>
          <NavLink
            to="/expansion-demo"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-xl text-xs transition-all ${
                isActive
                  ? 'bg-[var(--color-bg-sidebar-active)] text-[var(--color-accent)] font-medium'
                  : 'text-[rgba(255,255,255,0.35)] hover:text-[rgba(255,255,255,0.6)] hover:bg-[var(--color-bg-sidebar-hover)]'
              }`
            }
          >
            <FlaskConical size={14} />
            Expansion (Beta)
          </NavLink>
        </div>
      </div>

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
