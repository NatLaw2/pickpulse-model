// src/components/games/EdgeMovement.tsx

const STORAGE_KEY = "pp_edge_prev_v1";

type EdgeMap = Record<string, number>;

function loadEdgeMap(): EdgeMap {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveEdgeMap(map: EdgeMap) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {}
}

/**
 * Records the current edge and returns the delta from the previous value.
 * Returns null on first observation (no prior snapshot to compare).
 */
export function recordEdge(pickId: string, currentEdge: number): number | null {
  const map = loadEdgeMap();
  const prev = map[pickId];
  map[pickId] = currentEdge;
  saveEdgeMap(map);

  if (prev === undefined) return null;
  const delta = currentEdge - prev;
  if (Math.abs(delta) < 0.05) return null; // ignore noise
  return delta;
}

interface EdgeMovementProps {
  /** Delta from recordEdge, or null */
  delta: number | null;
}

export function EdgeMovement({ delta }: EdgeMovementProps) {
  if (delta === null) return null;

  const positive = delta > 0;
  const arrow = positive ? "\u2191" : "\u2193";
  const color = positive ? "text-emerald-400" : "text-red-400";
  const sign = positive ? "+" : "";

  return (
    <span className={`text-xs ${color} ml-1`}>
      {arrow} {sign}{delta.toFixed(1)}%
    </span>
  );
}
