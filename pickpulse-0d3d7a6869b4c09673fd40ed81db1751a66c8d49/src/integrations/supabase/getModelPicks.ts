// src/integrations/supabase/getModelPicks.ts

import { supabase } from "@/integrations/supabase/client";
import type { DateFilter } from "@/types/sports";
import type { SlateWithPicksResponse } from "@/types/modelPicks";

/**
 * Decision-slate response types (frontend)
 */
export type DecisionPick = {
  game_id: string;
  league: string;
  start_time: string; // ISO
  market: "spread" | "moneyline" | "total";
  side: string;
  confidence: number; // 0..1
  why: string[];
  signals?: any; // backend may evolve this
};

export type DecisionSlateResponse = {
  date: string;
  generated_at: string;
  top_pick: DecisionPick | null;
  strong_leans: DecisionPick[];
  watchlist: DecisionPick[];
  meta: {
    version: string;
    notes?: string;
  };
};

const DAY_PARAM_MAP: Record<DateFilter, string> = {
  today: "today",
  tomorrow: "tomorrow",
  nextDay: "nextDay",
  week: "today", // fallback until week is supported
};

/**
 * -----------------------------------------
 * Tiny cache layer (memory + sessionStorage)
 * -----------------------------------------
 * - Memory cache: fastest, resets on reload
 * - sessionStorage: survives refresh/reload (same tab)
 * - TTL: prevents stale values hanging around
 * - In-flight dedupe: prevents duplicate parallel calls
 */
type CacheEntry<T> = { ts: number; data: T };

const CACHE_TTL_MS = 1000 * 60 * 3; // 3 minutes (tune anytime)
const STORAGE_PREFIX = "pp_cache_v1:";

const memoryCache = new Map<string, CacheEntry<any>>();
const inFlight = new Map<string, Promise<any>>();

function now() {
  return Date.now();
}

function isExpired(ts: number) {
  return now() - ts > CACHE_TTL_MS;
}

function storageKey(key: string) {
  return `${STORAGE_PREFIX}${key}`;
}

function safeGetSession<T>(key: string): CacheEntry<T> | null {
  try {
    const raw = sessionStorage.getItem(storageKey(key));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CacheEntry<T>;
    if (!parsed || typeof parsed.ts !== "number" || !("data" in parsed)) return null;
    if (isExpired(parsed.ts)) {
      sessionStorage.removeItem(storageKey(key));
      return null;
    }
    return parsed;
  } catch {
    // Corrupt entry → remove
    try {
      sessionStorage.removeItem(storageKey(key));
    } catch {}
    return null;
  }
}

function safeSetSession<T>(key: string, entry: CacheEntry<T>) {
  try {
    sessionStorage.setItem(storageKey(key), JSON.stringify(entry));
  } catch {
    // Ignore quota / disabled storage — memory cache still works
  }
}

function safeRemoveSession(key: string) {
  try {
    sessionStorage.removeItem(storageKey(key));
  } catch {}
}

function getCached<T>(key: string): T | null {
  // 1) memory cache
  const mem = memoryCache.get(key);
  if (mem) {
    if (isExpired(mem.ts)) {
      memoryCache.delete(key);
    } else {
      return mem.data as T;
    }
  }

  // 2) sessionStorage cache
  const sess = safeGetSession<T>(key);
  if (sess) {
    // hydrate memory for speed next time
    memoryCache.set(key, sess);
    return sess.data;
  }

  return null;
}

function setCached<T>(key: string, data: T) {
  const entry: CacheEntry<T> = { ts: now(), data };
  memoryCache.set(key, entry);
  safeSetSession(key, entry);
}

async function withCache<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  // 1) Serve fresh cache if present
  const cached = getCached<T>(key);
  if (cached) return cached;

  // 2) If already fetching, await the same promise (dedupe)
  const existing = inFlight.get(key);
  if (existing) return (await existing) as T;

  // 3) Start a new fetch
  const p = (async () => {
    const data = await fetcher();
    setCached(key, data);
    return data;
  })();

  inFlight.set(key, p);

  try {
    return await p;
  } catch (e) {
    // If fetch fails, ensure we don't leave behind a bad cached value
    memoryCache.delete(key);
    safeRemoveSession(key);
    throw e;
  } finally {
    inFlight.delete(key);
  }
}

/**
 * Helpers for consistent Edge Function fetching
 */
function getSupabaseEnv() {
  const baseUrl = import.meta.env.VITE_SUPABASE_URL;
  const anonKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

  if (!baseUrl) throw new Error("Missing VITE_SUPABASE_URL");
  if (!anonKey) throw new Error("Missing VITE_SUPABASE_PUBLISHABLE_KEY");

  return { baseUrl, anonKey };
}

function emptySlateWithPicks(): SlateWithPicksResponse {
  return {
    nba: [],
    mlb: [],
    nhl: [],
    ncaab: [],
    ncaaf: [],
    nfl: [],
  };
}

/**
 * Fetches the slate-with-picks from edge function (GET + query param).
 * Refactored to match getDecisionSlate() for consistency.
 * Cached per-day (memory + sessionStorage).
 */
export async function getSlateWithPicks(dateFilter: DateFilter): Promise<SlateWithPicksResponse> {
  const dayParam = DAY_PARAM_MAP[dateFilter] ?? "today";
  const cacheKey = `slate-with-picks:${dayParam}`;

  return withCache<SlateWithPicksResponse>(cacheKey, async () => {
    const { baseUrl, anonKey } = getSupabaseEnv();

    const url = `${baseUrl}/functions/v1/slate-with-picks?day=${encodeURIComponent(dayParam)}`;
    console.log("Fetching slate-with-picks with:", dayParam);

    const res = await fetch(url, {
      method: "GET",
      headers: {
        apikey: anonKey,
        authorization: `Bearer ${anonKey}`,
        "content-type": "application/json",
      },
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`slate-with-picks failed: ${res.status} ${text}`);
    }

    const data = (await res.json()) as SlateWithPicksResponse;

    // Safe empty fallback
    return data ?? emptySlateWithPicks();
  });
}

/**
 * Fetches the scarcity-based decision-slate from edge function (GET + query param).
 * Cached per-day (memory + sessionStorage).
 */
export async function getDecisionSlate(dateFilter: DateFilter): Promise<DecisionSlateResponse> {
  const dayParam = DAY_PARAM_MAP[dateFilter] ?? "today";
  const cacheKey = `decision-slate:${dayParam}`;

  return withCache<DecisionSlateResponse>(cacheKey, async () => {
    const { baseUrl, anonKey } = getSupabaseEnv();

    const url = `${baseUrl}/functions/v1/decision-slate?day=${encodeURIComponent(dayParam)}`;
    console.log("Fetching decision-slate with:", dayParam);

    const res = await fetch(url, {
      method: "GET",
      headers: {
        apikey: anonKey,
        authorization: `Bearer ${anonKey}`,
        "content-type": "application/json",
      },
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`decision-slate failed: ${res.status} ${text}`);
    }

    const data = (await res.json()) as DecisionSlateResponse;

    // Defensive fallback
    if (!data) {
      return {
        date: dayParam,
        generated_at: new Date().toISOString(),
        top_pick: null,
        strong_leans: [],
        watchlist: [],
        meta: { version: "decision-slate/v1", notes: "empty" },
      };
    }

    return data;
  });
}

/**
 * Manual reset (helpful for debugging)
 */
export function clearSlateCaches() {
  memoryCache.clear();
  inFlight.clear();

  // Remove only our keys from sessionStorage
  try {
    const keysToRemove: string[] = [];
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i);
      if (k && k.startsWith(STORAGE_PREFIX)) keysToRemove.push(k);
    }
    for (const k of keysToRemove) sessionStorage.removeItem(k);
  } catch {
    // ignore
  }
}
