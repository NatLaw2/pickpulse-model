// src/components/games/SportAccordion.tsx
import { useState, useEffect, useCallback, type ReactNode } from "react";
import { ChevronDown, Layers } from "lucide-react";
import { SPORT_LABELS, type Sport } from "@/types/sports";

const LS_KEY = "pp_accordion_v1";

// ---------------------------------------------------------------------------
// Persistence helpers
// ---------------------------------------------------------------------------

function loadOpenState(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveOpenState(state: Record<string, boolean>) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(state));
  } catch {}
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SportGroup {
  sport: Sport;
  pickCount: number;
  children: ReactNode;
}

interface SportAccordionProps {
  groups: SportGroup[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SportAccordion({ groups }: SportAccordionProps) {
  // Determine which sport has the most picks (auto-open on first load)
  const [openMap, setOpenMap] = useState<Record<string, boolean>>(() => {
    const saved = loadOpenState();
    if (Object.keys(saved).length > 0) return saved;

    // First visit: open the sport with most picks
    let maxSport = "";
    let maxCount = 0;
    for (const g of groups) {
      if (g.pickCount > maxCount) {
        maxCount = g.pickCount;
        maxSport = g.sport;
      }
    }
    return maxSport ? { [maxSport]: true } : {};
  });

  // Persist on change
  useEffect(() => {
    saveOpenState(openMap);
  }, [openMap]);

  const toggle = useCallback((sport: string) => {
    setOpenMap((prev) => ({ ...prev, [sport]: !prev[sport] }));
  }, []);

  const expandAll = useCallback(() => {
    const next: Record<string, boolean> = {};
    for (const g of groups) next[g.sport] = true;
    setOpenMap(next);
  }, [groups]);

  const collapseAll = useCallback(() => {
    setOpenMap({});
  }, []);

  if (groups.length === 0) return null;

  const anyOpen = Object.values(openMap).some(Boolean);

  return (
    <div>
      {/* Controls */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Layers className="w-5 h-5 text-gray-400" />
          <h2 className="text-lg font-bold text-white tracking-tight">By Sport</h2>
          <span className="text-xs text-gray-500 ml-1">Remaining picks grouped by league</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={expandAll}
            className="text-xs text-gray-500 hover:text-white transition-colors px-2 py-1 rounded"
          >
            Expand all
          </button>
          <span className="text-slate-700">|</span>
          <button
            onClick={collapseAll}
            className="text-xs text-gray-500 hover:text-white transition-colors px-2 py-1 rounded"
          >
            Collapse all
          </button>
        </div>
      </div>

      {/* Accordion sections */}
      <div className="space-y-3">
        {groups.map((g) => {
          const isOpen = !!openMap[g.sport];
          const label = SPORT_LABELS[g.sport] ?? g.sport.toUpperCase();

          return (
            <div
              key={g.sport}
              className="border border-slate-800/60 rounded-xl overflow-hidden bg-slate-900/40 backdrop-blur-sm"
            >
              <button
                onClick={() => toggle(g.sport)}
                aria-expanded={isOpen}
                className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-slate-800/40 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="text-sm font-bold text-white">{label}</span>
                  <span className="text-xs text-gray-500 bg-slate-800 rounded-full px-2 py-0.5">
                    {g.pickCount} {g.pickCount === 1 ? "pick" : "picks"}
                  </span>
                </div>
                <ChevronDown
                  className={`w-4 h-4 text-gray-500 transition-transform duration-200 ${
                    isOpen ? "rotate-180" : ""
                  }`}
                />
              </button>

              {isOpen && (
                <div className="px-4 pb-4 pt-1">
                  {g.children}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
