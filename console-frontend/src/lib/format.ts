/**
 * Format a number as compact currency: $123, $12.3k, $1.23M, $1.23B
 */
export function formatCurrency(value: number | null | undefined): string {
  if (value == null || isNaN(value)) return '—';
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';

  if (abs >= 1_000_000_000) {
    return `${sign}$${(abs / 1_000_000_000).toFixed(2)}B`;
  }
  if (abs >= 1_000_000) {
    const m = abs / 1_000_000;
    return `${sign}$${m >= 100 ? m.toFixed(0) : m >= 10 ? m.toFixed(1) : m.toFixed(2)}M`;
  }
  if (abs >= 1_000) {
    const k = abs / 1_000;
    return `${sign}$${k >= 100 ? k.toFixed(0) : k >= 10 ? k.toFixed(1) : k.toFixed(2)}k`;
  }
  return `${sign}$${abs.toFixed(0)}`;
}
