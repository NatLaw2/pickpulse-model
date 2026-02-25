// src/components/UpdateIndicator.tsx
import { useEffect, useState } from "react";

interface UpdateIndicatorProps {
  /** ISO timestamp or epoch ms of when data was last fetched/updated */
  updatedAt: string | number | null;
}

function minutesAgo(ts: string | number): number {
  const then = typeof ts === "number" ? ts : new Date(ts).getTime();
  if (Number.isNaN(then)) return Infinity;
  return Math.max(0, Math.floor((Date.now() - then) / 60_000));
}

function dotColor(mins: number): string {
  if (mins <= 10) return "bg-emerald-500";
  if (mins <= 30) return "bg-amber-400";
  return "bg-red-400";
}

function textColor(mins: number): string {
  if (mins <= 10) return "text-gray-400";
  if (mins <= 30) return "text-amber-400";
  return "text-red-400";
}

function label(mins: number): string {
  if (mins === 0) return "Updated just now";
  if (mins === 1) return "Updated 1 minute ago";
  if (mins < 60) return `Updated ${mins} minutes ago`;
  const hrs = Math.floor(mins / 60);
  return `Updated ${hrs}h ago`;
}

export function UpdateIndicator({ updatedAt }: UpdateIndicatorProps) {
  const [mins, setMins] = useState(() =>
    updatedAt ? minutesAgo(updatedAt) : Infinity,
  );

  useEffect(() => {
    if (!updatedAt) return;
    setMins(minutesAgo(updatedAt));
    const id = setInterval(() => setMins(minutesAgo(updatedAt)), 60_000);
    return () => clearInterval(id);
  }, [updatedAt]);

  if (!updatedAt || mins === Infinity) return null;

  return (
    <div className="flex items-center gap-1.5 mt-1">
      <span className={`w-2 h-2 rounded-full ${dotColor(mins)}`} />
      <span className={`text-xs ${textColor(mins)}`}>{label(mins)}</span>
    </div>
  );
}
