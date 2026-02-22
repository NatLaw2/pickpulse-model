// src/components/games/ConfidenceBar.tsx

interface ConfidenceBarProps {
  /** 0..1 probability value */
  value: number;
  className?: string;
}

export function ConfidenceBar({ value, className = "" }: ConfidenceBarProps) {
  const pct = Math.max(0, Math.min(100, value * 100));

  return (
    <div className={`w-full bg-slate-800 rounded-full h-2 ${className}`}>
      <div
        className="bg-emerald-400 h-2 rounded-full transition-all duration-700 ease-out"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
