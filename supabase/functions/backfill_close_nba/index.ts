/// <reference lib="deno.ns" />
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

function getEnv(name: string): string {
  const v = Deno.env.get(name);
  if (!v) throw new Error(`Missing env var: ${name}`);
  return v;
}

function json(res: unknown, status = 200) {
  return new Response(JSON.stringify(res), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

async function supaFetch(path: string, init: RequestInit = {}) {
  const SUPABASE_URL = getEnv("SUPABASE_URL");
  const SERVICE_ROLE = getEnv("SUPABASE_SERVICE_ROLE_KEY");

  const url = `${SUPABASE_URL}${path}`;
  const headers = new Headers(init.headers || {});
  headers.set("Authorization", `Bearer ${SERVICE_ROLE}`);
  headers.set("apikey", SERVICE_ROLE);
  headers.set("Content-Type", "application/json");

  const resp = await fetch(url, { ...init, headers });
  const text = await resp.text();
  return { resp, text };
}

type OddsApiMarket = {
  key: string; // h2h, spreads, totals
  outcomes: Array<{ name: string; price: number; point?: number }>;
};

type OddsApiBookmaker = {
  key: string; // fanduel, draftkings...
  title: string;
  last_update: string; // ISO
  markets: OddsApiMarket[];
};

type OddsApiGame = {
  id: string;
  sport_key: string;
  commence_time: string; // ISO
  home_team: string;
  away_team: string;
  bookmakers: OddsApiBookmaker[];
};

type OddsHistoricalResponse = {
  timestamp: string; // snapshot time
  data: OddsApiGame[];
};

type ClosingLineInsert = {
  sport: string;
  event_id: string;
  captured_at: string; // snapshot timestamp
  commence_time: string;
  home_team: string;
  away_team: string;
  bookmaker_key: string;
  bookmaker_title: string;
  market: string;
  outcome_name: string;
  price: number | null;
  point: number; // NOTE: NOT NULL in DB, so we always send a number (0 for h2h)
};

function isoDateOnly(d: Date) {
  // YYYY-MM-DD
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function addDays(d: Date, days: number) {
  const x = new Date(d.getTime());
  x.setUTCDate(x.getUTCDate() + days);
  return x;
}

function historicalUrl(apiKey: string, dateIso: string) {
  // date must be ISO datetime; we'll use noon UTC for each day
  return `https://api.the-odds-api.com/v4/historical/sports/basketball_nba/odds?regions=us&markets=h2h,spreads&oddsFormat=american&date=${encodeURIComponent(
    dateIso,
  )}&apiKey=${apiKey}`;
}

async function upsertClosingLines(rows: ClosingLineInsert[]) {
  if (rows.length === 0) return { upserted: 0 };

  // Insert rows; skip duplicates silently.
  // After the closing_lines_snap_unique migration, the unique index
  // includes date_trunc('minute', captured_at), so historical rows
  // with different timestamps always create new rows.
  const path = `/rest/v1/closing_lines`;

  const { resp, text } = await supaFetch(path, {
    method: "POST",
    headers: {
      Prefer: "resolution=ignore-duplicates,return=representation",
    },
    body: JSON.stringify(rows),
  });

  if (!resp.ok) {
    throw new Error(`closing_lines upsert failed (${resp.status}): ${text}`);
  }
  const returned = JSON.parse(text);
  return { upserted: Array.isArray(returned) ? returned.length : rows.length };
}

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const ODDS_API_KEY = getEnv("ODDS_API_KEY");

    // defaults
    const daysBack = Number(Deno.env.get("BACKFILL_DAYS") ?? "30");
    const preferredBook = (Deno.env.get("PREFERRED_BOOKMAKER") ?? "fanduel").toLowerCase();

    // One snapshot per day at 12:00 UTC (good enough for training/backfill)
    const today = new Date();
    const start = addDays(today, -daysBack);

    let totalFetchedDays = 0;
    let totalGamesSeen = 0;
    let totalRowsBuilt = 0;
    let totalUpserted = 0;

    for (
      let d = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate()));
      d <= today;
      d = addDays(d, 1)
    ) {
      totalFetchedDays++;

      const dateIso = `${isoDateOnly(d)}T12:00:00Z`;
      const url = historicalUrl(ODDS_API_KEY, dateIso);

      const r = await fetch(url);
      const t = await r.text();
      if (!r.ok) {
        // don't hard-fail the entire backfill if a day errors
        console.log(`[backfill_close_nba] odds api error ${r.status} for ${dateIso}: ${t}`);
        continue;
      }

      const payload = JSON.parse(t) as OddsHistoricalResponse;
      const snapshotTs = payload.timestamp;

      const inserts: ClosingLineInsert[] = [];

      for (const g of payload.data ?? []) {
        totalGamesSeen++;

        const book = (g.bookmakers ?? []).find(
          (b) => (b.key ?? "").toLowerCase() === preferredBook,
        );
        if (!book) continue;

        for (const m of book.markets ?? []) {
          if (m.key !== "h2h" && m.key !== "spreads") continue;

          for (const o of m.outcomes ?? []) {
            inserts.push({
              sport: "nba",
              event_id: g.id,
              captured_at: snapshotTs,
              commence_time: g.commence_time,
              home_team: g.home_team,
              away_team: g.away_team,
              bookmaker_key: book.key,
              bookmaker_title: book.title,
              market: m.key,
              outcome_name: o.name,
              price: typeof o.price === "number" ? o.price : null,

              // ✅ FIX: point is NOT NULL in your table.
              // For h2h there is no point, so we set 0.
              point: typeof o.point === "number" ? o.point : 0,
            });
          }
        }
      }

      totalRowsBuilt += inserts.length;
      if (inserts.length > 0) {
        const { upserted } = await upsertClosingLines(inserts);
        totalUpserted += upserted;
      }
    }

    return json({
      ok: true,
      backfill_days: daysBack,
      preferred_bookmaker: preferredBook,
      fetched_days: totalFetchedDays,
      games_seen: totalGamesSeen,
      rows_built: totalRowsBuilt,
      rows_upserted: totalUpserted,
      note:
        "This backfills one FanDuel snapshot/day at 12:00 UTC. For true 'closing', we’ll add a second pass that targets ~10 minutes before commence_time.",
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return json({ ok: false, error: msg }, 500);
  }
});