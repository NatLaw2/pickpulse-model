// src/components/games/CountdownLock.tsx
import { useEffect, useState } from "react";

interface CountdownLockProps {
  /** ISO start times of all upcoming games */
  gameTimes: string[];
}

function nextLockMs(gameTimes: string[]): number | null {
  const now = Date.now();
  let nearest: number | null = null;

  for (const iso of gameTimes) {
    const tip = new Date(iso).getTime();
    if (Number.isNaN(tip)) continue;
    const lockAt = tip - 15 * 60_000; // 15 min before tip
    if (lockAt > now && (nearest === null || lockAt < nearest)) {
      nearest = lockAt;
    }
  }

  return nearest;
}

function fmtCountdown(ms: number): string {
  if (ms <= 0) return "0s";
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;

  if (h > 0) return `${h}h ${m}m ${String(s).padStart(2, "0")}s`;
  if (m > 0) return `${m}m ${String(s).padStart(2, "0")}s`;
  return `${s}s`;
}

export function CountdownLock({ gameTimes }: CountdownLockProps) {
  const [remaining, setRemaining] = useState<number | null>(null);

  useEffect(() => {
    function tick() {
      const lock = nextLockMs(gameTimes);
      if (lock === null) {
        setRemaining(null);
        return;
      }
      setRemaining(Math.max(0, lock - Date.now()));
    }

    tick();
    const id = setInterval(tick, 1_000);
    return () => clearInterval(id);
  }, [gameTimes]);

  if (remaining === null) {
    return (
      <span className="inline-flex items-center bg-slate-800 text-gray-500 rounded-full px-3 py-1 text-xs">
        No upcoming locks today
      </span>
    );
  }

  return (
    <span className="inline-flex items-center bg-slate-800 text-gray-300 rounded-full px-3 py-1 text-xs">
      Next lock in {fmtCountdown(remaining)}
    </span>
  );
}
