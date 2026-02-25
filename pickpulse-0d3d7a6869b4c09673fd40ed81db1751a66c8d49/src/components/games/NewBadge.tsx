// src/components/games/NewBadge.tsx
import { useEffect, useState } from "react";

const STORAGE_KEY = "pp_first_seen_v1";
const EXPIRY_MS = 15 * 60_000; // 15 minutes

/**
 * Tracks when a pick was first seen in sessionStorage.
 * Returns the first-seen timestamp for the given pick ID.
 */
function getFirstSeen(pickId: string): number {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    const map: Record<string, number> = raw ? JSON.parse(raw) : {};
    if (map[pickId]) return map[pickId];

    // First time seeing this pick — record it
    map[pickId] = Date.now();
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(map));
    return map[pickId];
  } catch {
    return Date.now();
  }
}

interface NewBadgeProps {
  /** Unique identifier for the pick (e.g. gameId-market) */
  pickId: string;
}

export function NewBadge({ pickId }: NewBadgeProps) {
  const [isNew, setIsNew] = useState(false);

  useEffect(() => {
    const firstSeen = getFirstSeen(pickId);
    const elapsed = Date.now() - firstSeen;
    setIsNew(elapsed < EXPIRY_MS);

    if (elapsed < EXPIRY_MS) {
      const timeout = setTimeout(
        () => setIsNew(false),
        EXPIRY_MS - elapsed,
      );
      return () => clearTimeout(timeout);
    }
  }, [pickId]);

  if (!isNew) return null;

  return (
    <span className="bg-emerald-500/20 text-emerald-400 text-[10px] rounded-full px-2 py-0.5 ml-2">
      NEW
    </span>
  );
}
