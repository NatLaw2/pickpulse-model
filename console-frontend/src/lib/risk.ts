export function riskColor(pct: number): string {
  if (pct >= 30) return 'var(--color-danger)';
  if (pct >= 20) return 'var(--color-warning)';
  return 'var(--color-success)';
}

export function riskLabel(pct: number): string {
  if (pct >= 30) return 'High';
  if (pct >= 20) return 'Med';
  return 'Low';
}
