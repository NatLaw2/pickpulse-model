/// <reference lib="deno.ns" />
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";

/**
 * snap_odds_nba_near_tip
 *
 * Captures odds snapshots into closing_lines for NBA games starting
 * within the next 30 minutes.  Runs every 2 minutes via cron.
 *
 * Unlike close_nba (which upserts and overwrites), this function
 * INSERTs with ignoreDuplicates so that each 2-minute run creates
 * a new snapshot row (deduplicated per minute by the unique index
 * closing_lines_snap_unique).
 *
 * Requires:
 *   - The closing_lines_snap_unique index (see migration
 *     20260218_closing_lines_add_captured_at_to_unique.sql)
 *   - Env vars: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ODDS_API_KEY
 *
 * Cron: every 2 minutes (configure in Supabase dashboard)
 */

const VERSION = "snap_odds_nba_near_tip@2026-02-18_v1";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

// ---------------------------------------------------------------------------
// Types (same shape as The Odds API v4)
// ---------------------------------------------------------------------------

type OddsOutcome = {
  name: string;
  price: number;
  point?: number;
};

type OddsMarket = {
  key: string; // "h2h" | "spreads"
  outcomes: OddsOutcome[];
};

type OddsBookmaker = {
  key: string;
  title?: string;
  markets: OddsMarket[];
};

type OddsEvent = {
  id: string;
  sport_key: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  bookmakers: OddsBookmaker[];
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getEnv(name: string): string {
  const v = Deno.env.get(name);
  if (!v) throw new Error(`Missing env var: ${name}`);
  return v;
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

// ---------------------------------------------------------------------------
// Odds API fetch
// ---------------------------------------------------------------------------

async function fetchNbaOdds(apiKey: string): Promise<OddsEvent[]> {
  const url =
    `https://api.the-odds-api.com/v4/sports/basketball_nba/odds/` +
    `?apiKey=${encodeURIComponent(apiKey)}` +
    `&regions=us` +
    `&markets=h2h,spreads` +
    `&oddsFormat=american` +
    `&dateFormat=iso`;

  const res = await fetch(url, { method: "GET" });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Odds API ${res.status}: ${body.slice(0, 300)}`);
  }
  return (await res.json()) as OddsEvent[];
}

// ---------------------------------------------------------------------------
// Build closing_lines rows
// ---------------------------------------------------------------------------

function buildRows(
  ev: OddsEvent,
  book: OddsBookmaker,
  capturedAt: string,
): Record<string, unknown>[] {
  const rows: Record<string, unknown>[] = [];

  const base = {
    sport: "nba",
    event_id: ev.id,
    commence_time: ev.commence_time,
    captured_at: capturedAt,
    home_team: ev.home_team,
    away_team: ev.away_team,
    bookmaker_key: book.key,
    bookmaker_title: book.title ?? book.key,
  };

  const h2h = book.markets.find((m) => m.key === "h2h");
  const spreads = book.markets.find((m) => m.key === "spreads");

  if (h2h) {
    for (const o of h2h.outcomes) {
      rows.push({
        ...base,
        market: "h2h",
        outcome_name: o.name,
        price: o.price,
        point: 0, // h2h has no spread point; 0 matches existing convention
      });
    }
  }

  if (spreads) {
    for (const o of spreads.outcomes) {
      rows.push({
        ...base,
        market: "spreads",
        outcome_name: o.name,
        price: o.price,
        point: o.point ?? null,
      });
    }
  }

  return rows;
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const SUPABASE_URL = getEnv("SUPABASE_URL");
    const SERVICE_ROLE_KEY = getEnv("SUPABASE_SERVICE_ROLE_KEY");
    const ODDS_API_KEY = getEnv("ODDS_API_KEY");
    const bookmakerKey = (Deno.env.get("PREFERRED_BOOKMAKER") ?? "fanduel").toLowerCase();

    const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
      auth: { persistSession: false },
    });

    const now = new Date();
    const capturedAt = now.toISOString();

    // Window: games starting between now and now + 30 minutes
    const windowEndMs = now.getTime() + 30 * 60 * 1000;

    // Fetch all NBA odds from The Odds API
    const events = await fetchNbaOdds(ODDS_API_KEY);

    // Filter to games within the 30-minute window
    const nearTip = events.filter((e) => {
      const ct = new Date(e.commence_time).getTime();
      return ct > now.getTime() && ct <= windowEndMs;
    });

    if (nearTip.length === 0) {
      return json({
        ok: true,
        version: VERSION,
        message: "No NBA games starting within 30 minutes",
        captured_at: capturedAt,
        events_total: events.length,
        near_tip: 0,
        inserted: 0,
      });
    }

    // Build rows for each near-tip game
    const allRows: Record<string, unknown>[] = [];

    for (const ev of nearTip) {
      // Prefer FanDuel, else first bookmaker
      const book =
        ev.bookmakers.find((b) => b.key === bookmakerKey) ??
        ev.bookmakers[0];
      if (!book) continue;
      allRows.push(...buildRows(ev, book, capturedAt));
    }

    // INSERT with ignoreDuplicates — the unique index
    // closing_lines_snap_unique (includes date_trunc('minute', captured_at))
    // will reject rows within the same minute for the same key,
    // preventing bloat if the function fires twice in one minute.
    let inserted = 0;
    if (allRows.length > 0) {
      const { error, count } = await supabase
        .from("closing_lines")
        .insert(allRows, { count: "exact" })
        // If the new unique index is in place, Postgres will reject
        // same-minute duplicates automatically (23505 unique violation).
        // We catch that and fall back to ignoreDuplicates upsert.
        ;

      if (error) {
        // Likely unique violation from same-minute re-run.
        // Retry with upsert + ignoreDuplicates to silently skip dups.
        const { error: err2 } = await supabase
          .from("closing_lines")
          .upsert(allRows, {
            onConflict: "sport,event_id,bookmaker_key,market,outcome_name,point",
            ignoreDuplicates: true,
          });
        if (err2) {
          throw new Error(`closing_lines insert failed: ${err2.message}`);
        }
        // In the fallback case, some rows may have been new (different minute)
        // and some skipped.  We report best-effort.
        inserted = allRows.length;
      } else {
        inserted = count ?? allRows.length;
      }
    }

    return json({
      ok: true,
      version: VERSION,
      captured_at: capturedAt,
      bookmaker: bookmakerKey,
      events_total: events.length,
      near_tip: nearTip.length,
      rows_built: allRows.length,
      inserted,
      near_tip_events: nearTip.map((e) => ({
        id: e.id,
        home: e.home_team,
        away: e.away_team,
        commence: e.commence_time,
        mins_to_tip: Math.round(
          (new Date(e.commence_time).getTime() - now.getTime()) / 60000,
        ),
      })),
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[snap_odds_nba_near_tip] error: ${msg}`);
    return json({ ok: false, error: msg }, 500);
  }
});
