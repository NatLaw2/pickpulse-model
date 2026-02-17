// supabase/functions/snap-odds-nba/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";

const VERSION = "snap-odds-nba@2026-02-08_v3_moneyline_fallback_any_book";
const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

// ---- Config ----
// If you're using The Odds API, set ODDS_API_KEY in Supabase Function secrets.
const ODDS_API_KEY =
  Deno.env.get("ODDS_API_KEY") ||
  Deno.env.get("THE_ODDS_API_KEY") ||
  Deno.env.get("ODDSAPI_KEY");

// NBA sport key for The Odds API
const ODDS_SPORT_KEY = Deno.env.get("ODDS_SPORT_KEY") || "basketball_nba";

// Regions (The Odds API). Common: us
const ODDS_REGIONS = Deno.env.get("ODDS_REGIONS") || "us";

// IMPORTANT: include h2h so moneyline comes through
const ODDS_MARKETS = Deno.env.get("ODDS_MARKETS") || "h2h,spreads,totals";

// Prefer this book when present; you can override by query param `book=fanduel`
const DEFAULT_BOOK = (Deno.env.get("ODDS_PREFERRED_BOOK") || "fanduel").toLowerCase();

// Table names
const ODDS_TABLE = "odds_snapshots_nba";

function isoNow() {
  return new Date().toISOString();
}

function num(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

type OddsApiOutcome = {
  name: string;
  price: number;
  point?: number;
};

type OddsApiMarket = {
  key: string; // "h2h" | "spreads" | "totals"
  outcomes: OddsApiOutcome[];
};

type OddsApiBookmaker = {
  key: string; // e.g. "fanduel"
  title?: string;
  last_update?: string;
  markets: OddsApiMarket[];
};

type OddsApiEvent = {
  id: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  bookmakers: OddsApiBookmaker[];
};

function findMarket(book: OddsApiBookmaker, key: string): OddsApiMarket | null {
  const m = (book.markets || []).find((x) => (x?.key || "").toLowerCase() === key.toLowerCase());
  return m || null;
}

function normalizeTeamName(s: string) {
  return (s || "").trim().toLowerCase();
}

function pickOutcomeByTeam(outcomes: OddsApiOutcome[], teamName: string): OddsApiOutcome | null {
  const t = normalizeTeamName(teamName);
  return outcomes.find((o) => normalizeTeamName(o.name) === t) || null;
}

function pickTotals(outcomes: OddsApiOutcome[]) {
  // totals outcomes are usually name: "Over"/"Under" with point & price
  const over = outcomes.find((o) => normalizeTeamName(o.name) === "over") || null;
  const under = outcomes.find((o) => normalizeTeamName(o.name) === "under") || null;
  return { over, under };
}

type InsertRow = {
  event_id: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  book: string;
  pulled_at: string;

  ml_home: number | null;
  ml_away: number | null;

  spread_home_point: number | null;
  spread_home_price: number | null;
  spread_away_point: number | null;
  spread_away_price: number | null;

  total_point: number | null;
  over_price: number | null;
  under_price: number | null;
};

async function fetchOddsFromTheOddsApi(): Promise<OddsApiEvent[]> {
  if (!ODDS_API_KEY) throw new Error("Missing ODDS_API_KEY (or THE_ODDS_API_KEY) in function secrets");

  // The Odds API endpoint shape:
  // https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?apiKey=...&regions=us&markets=h2h,spreads,totals&oddsFormat=american
  const url =
    `https://api.the-odds-api.com/v4/sports/${encodeURIComponent(ODDS_SPORT_KEY)}/odds/` +
    `?apiKey=${encodeURIComponent(ODDS_API_KEY)}` +
    `&regions=${encodeURIComponent(ODDS_REGIONS)}` +
    `&markets=${encodeURIComponent(ODDS_MARKETS)}` +
    `&oddsFormat=american`;

  const res = await fetch(url, { method: "GET" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Odds API failed: ${res.status} ${text}`);
  }
  return (await res.json()) as OddsApiEvent[];
}

function buildRowForBook(ev: OddsApiEvent, book: OddsApiBookmaker, pulledAtIso: string): InsertRow {
  const home = ev.home_team;
  const away = ev.away_team;

  // ---- Moneyline (h2h) ----
  const h2h = findMarket(book, "h2h");
  const mlHome = h2h ? pickOutcomeByTeam(h2h.outcomes || [], home) : null;
  const mlAway = h2h ? pickOutcomeByTeam(h2h.outcomes || [], away) : null;

  // ---- Spreads ----
  const spreads = findMarket(book, "spreads");
  const spHome = spreads ? pickOutcomeByTeam(spreads.outcomes || [], home) : null;
  const spAway = spreads ? pickOutcomeByTeam(spreads.outcomes || [], away) : null;

  // ---- Totals ----
  const totals = findMarket(book, "totals");
  const tot = totals ? pickTotals(totals.outcomes || []) : { over: null, under: null };

  // totals point should match on over/under; prefer over.point then under.point
  const totalPoint = num(tot.over?.point ?? tot.under?.point ?? null);

  return {
    event_id: ev.id,
    commence_time: ev.commence_time,
    home_team: home,
    away_team: away,
    book: (book.key || "").toLowerCase(),
    pulled_at: pulledAtIso,

    ml_home: num(mlHome?.price ?? null),
    ml_away: num(mlAway?.price ?? null),

    spread_home_point: num(spHome?.point ?? null),
    spread_home_price: num(spHome?.price ?? null),
    spread_away_point: num(spAway?.point ?? null),
    spread_away_price: num(spAway?.price ?? null),

    total_point: totalPoint,
    over_price: num(tot.over?.price ?? null),
    under_price: num(tot.under?.price ?? null),
  };
}

/**
 * Finds ANY book in the list that has BOTH ML outcomes for home+away.
 * Returns the prices, and which book provided them (for debug only).
 */
function findMoneylineFromAnyBook(
  ev: OddsApiEvent,
  books: OddsApiBookmaker[],
): { ml_home: number; ml_away: number; book_key: string } | null {
  const home = ev.home_team;
  const away = ev.away_team;

  for (const b of books) {
    const h2h = findMarket(b, "h2h");
    if (!h2h) continue;

    const mlHome = pickOutcomeByTeam(h2h.outcomes || [], home);
    const mlAway = pickOutcomeByTeam(h2h.outcomes || [], away);

    const homePrice = num(mlHome?.price ?? null);
    const awayPrice = num(mlAway?.price ?? null);

    if (homePrice !== null && awayPrice !== null) {
      return { ml_home: homePrice, ml_away: awayPrice, book_key: (b.key || "").toLowerCase() };
    }
  }

  return null;
}

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const url = new URL(req.url);
    const debug = url.searchParams.get("debug") === "1";
    const bookFilter = (url.searchParams.get("book") || DEFAULT_BOOK).toLowerCase();
    const includeAllBooks = url.searchParams.get("all_books") === "1"; // optional: store every book
    const limitEvents = Number(url.searchParams.get("limit") || "0");

    // If 1, we will backfill ML from any other book when preferred book ML is missing.
    // Default ON (because this is the core fix you want).
    const mlFallbackAnyBook = url.searchParams.get("ml_fallback_any_book") !== "0";

    const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
    const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || Deno.env.get("SERVICE_ROLE_KEY");

    if (!SUPABASE_URL) throw new Error("Missing SUPABASE_URL");
    if (!SERVICE_ROLE_KEY) throw new Error("Missing SUPABASE_SERVICE_ROLE_KEY (or SERVICE_ROLE_KEY)");

    const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
      auth: { persistSession: false },
    });

    const pulledAt = isoNow();

    const events = await fetchOddsFromTheOddsApi();
    const eventsLimited = limitEvents > 0 ? events.slice(0, limitEvents) : events;

    const rows: InsertRow[] = [];
    let eventsSeen = 0;
    let booksSeen = 0;
    let rowsWithMl = 0;

    // Diagnostics counters (helpful for you later)
    let preferredMissing = 0;
    let mlFallbackApplied = 0;
    let mlStillMissingAfterFallback = 0;
    const mlFallbackBookCounts: Record<string, number> = {};

    for (const ev of eventsLimited) {
      eventsSeen++;

      const books = Array.isArray(ev.bookmakers) ? ev.bookmakers : [];

      if (includeAllBooks) {
        for (const b of books) {
          booksSeen++;
          const r = buildRowForBook(ev, b, pulledAt);
          if (r.ml_home !== null && r.ml_away !== null) rowsWithMl++;
          rows.push(r);
        }
        continue;
      }

      // only store the preferred book if available, else store the first book
      const preferred = books.find((b) => (b?.key || "").toLowerCase() === bookFilter) || books[0];
      if (!preferred) continue;

      if ((preferred.key || "").toLowerCase() !== bookFilter) preferredMissing++;

      booksSeen++;
      const r = buildRowForBook(ev, preferred, pulledAt);

      // If the preferred book doesn't have ML, optionally fill ML from any other book
      if (mlFallbackAnyBook && (r.ml_home === null || r.ml_away === null)) {
        const fallback = findMoneylineFromAnyBook(ev, books);
        if (fallback) {
          // Patch only ML fields; keep spreads/totals from preferred book
          r.ml_home = fallback.ml_home;
          r.ml_away = fallback.ml_away;

          mlFallbackApplied++;
          mlFallbackBookCounts[fallback.book_key] = (mlFallbackBookCounts[fallback.book_key] || 0) + 1;
        } else {
          mlStillMissingAfterFallback++;
        }
      }

      if (r.ml_home !== null && r.ml_away !== null) rowsWithMl++;
      rows.push(r);
    }

    // Insert snapshots (append-only)
    let inserted = 0;
    if (rows.length > 0) {
      const { error } = await supabase.from(ODDS_TABLE).insert(rows);
      if (error) throw new Error(error.message);
      inserted = rows.length;
    }

    return new Response(
      JSON.stringify(
        {
          ok: true,
          version: VERSION,
          pulled_at: pulledAt,
          preferred_book: bookFilter,
          all_books: includeAllBooks,
          ml_fallback_any_book: mlFallbackAnyBook,
          events_seen: eventsSeen,
          books_seen: booksSeen,
          rows_built: rows.length,
          inserted,
          rows_with_moneyline: rowsWithMl,
          debug: debug
            ? {
                markets_requested: ODDS_MARKETS,
                regions: ODDS_REGIONS,
                sport_key: ODDS_SPORT_KEY,
                preferred_missing_count: preferredMissing,
                ml_fallback_applied: mlFallbackApplied,
                ml_still_missing_after_fallback: mlStillMissingAfterFallback,
                ml_fallback_book_counts: mlFallbackBookCounts,
                sample_row: rows[0] ?? null,
              }
            : undefined,
        },
        null,
        2,
      ),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (err) {
    return new Response(
      JSON.stringify({
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});