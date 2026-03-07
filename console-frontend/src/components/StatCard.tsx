import { type ReactNode } from 'react';

interface Props {
  label: string;
  value: string | number | null;
  sub?: string;
  icon?: ReactNode;
  accent?: string;
  onClick?: () => void;
  tooltip?: string;
}

export function StatCard({ label, value, sub, icon, accent, onClick, tooltip }: Props) {
  return (
    <button
      onClick={onClick}
      title={tooltip}
      className={`bg-white border border-[var(--color-border)] rounded-2xl p-6 text-left card-hover shadow-[0_1px_3px_rgba(0,0,0,0.08)] relative overflow-hidden ${onClick ? 'cursor-pointer' : 'cursor-default'}`}
    >
      {/* Accent top line */}
      {accent && (
        <div
          className="absolute top-0 left-0 right-0 h-[3px]"
          style={{
            background: `linear-gradient(90deg, ${accent}, ${accent}88 70%, transparent)`,
          }}
        />
      )}
      <div className="flex items-center gap-2 mb-3">
        {icon && <span style={accent ? { color: accent } : { color: 'var(--color-text-muted)' }}>{icon}</span>}
        <span className="text-xs text-[var(--color-text-muted)] uppercase tracking-wider font-medium">{label}</span>
      </div>
      <div className="text-3xl font-bold tracking-tight" style={accent ? { color: accent } : {}}>
        {value ?? '—'}
      </div>
      {sub && <div className="text-xs text-[var(--color-text-secondary)] mt-2">{sub}</div>}
    </button>
  );
}
