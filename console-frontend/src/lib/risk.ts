export function riskColor(pct: number): string {
  if (pct >= 70) return 'var(--color-danger)';
  if (pct >= 40) return 'var(--color-warning)';
  return 'var(--color-success)';
}

export function riskLabel(pct: number): string {
  if (pct >= 70) return 'High';
  if (pct >= 40) return 'Med';
  return 'Low';
}
