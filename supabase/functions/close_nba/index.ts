import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

type OddsApiEvent = {
  id: string;
  sport_key: string;
  sport_title: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  bookmakers: Array<{
    key: string;
    title: string;
    markets: Array<{
      key: string; // h2h, spreads, totals
      outcomes: Array<{
        name: string;
        price: number; // american odds (int)
        point?: number; // spread/total point
      }>;
    }>;
  }>;
};

function nowIso() {
  return new Date().toISOString();
}

function minutesFromNow(iso: string) {
  const t = new Date(iso).getTime();
  return Math.round((t - Date.now()) / 60000);
}

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    const ODDS_API_KEY = Deno.env.get("ODDS_API_KEY");
    const CLOSE_WINDOW_MINUTES = Number(Deno.env.get("CLOSE_WINDOW_MINUTES") || "15");

    if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
      throw new Error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in secrets");
    }
    if (!ODDS_API_KEY) {
      throw new Error("Missing ODDS_API_KEY in secrets");
    }

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // Fetch NBA odds
    const apiUrl =
      `https://api.the-odds-api.com/v4/sports/basketball_nba/odds/?apiKey=${ODDS_API_KEY}` +
      `&regions=us&markets=h2h,spreads&oddsFormat=american&dateFormat=iso`;

    const oddsRes = await fetch(apiUrl);
    if (!oddsRes.ok) {
      const body = await oddsRes.text();
      return new Response(
        JSON.stringify({ ok: false, error: "Odds API error", status: oddsRes.status, body }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    const events: OddsApiEvent[] = await oddsRes.json();

    // Filter games starting soon
    const startingSoon = events.filter((e) => {
      const mins = minutesFromNow(e.commence_time);
      return mins >= 0 && mins <= CLOSE_WINDOW_MINUTES;
    });

    // If you temporarily use a big window (1440), this will grab "today-ish" games too.
    const captured_at = nowIso();

    let inserted = 0;
    let skipped = 0;

    for (const e of startingSoon) {
      // Prefer FanDuel if present, else first
      const preferredBook =
        e.bookmakers.find((b) => b.key === "fanduel") ?? e.bookmakers[0];

      if (!preferredBook) {
        skipped++;
        continue;
      }

      const h2h = preferredBook.markets.find((m) => m.key === "h2h");
      const spreads = preferredBook.markets.find((m) => m.key === "spreads");

      // Build ML columns
      let ml_home: number | null = null;
      let ml_away: number | null = null;

      if (h2h) {
        const ho = h2h.outcomes.find((o) => o.name === e.home_team);
        const ao = h2h.outcomes.find((o) => o.name === e.away_team);
        ml_home = ho?.price ?? null;
        ml_away = ao?.price ?? null;
      }

      // Build spread columns (store the line + price for each side)
      let spread_home_point: number | null = null;
      let spread_home_price: number | null = null;
      let spread_away_point: number | null = null;
      let spread_away_price: number | null = null;

      if (spreads) {
        const ho = spreads.outcomes.find((o) => o.name === e.home_team);
        const ao = spreads.outcomes.find((o) => o.name === e.away_team);

        if (ho?.point !== undefined) spread_home_point = ho.point;
        if (ho?.price !== undefined) spread_home_price = ho.price;

        if (ao?.point !== undefined) spread_away_point = ao.point;
        if (ao?.price !== undefined) spread_away_price = ao.price;
      }

      // --- Row A: "summary" row (optional but useful) ---
      // This row is the one that makes your table readable at a glance.
      // It uses market='summary' and outcome_name='summary' to avoid clashing with your unique index for real markets.
      const summaryRow = {
        sport: "nba",
        event_id: e.id,
        start_time: null,                 // keep nullable
        commence_time: e.commence_time,    // store the API commence time
        captured_at,
        home_team: e.home_team,
        away_team: e.away_team,
        ml_home,
        ml_away,
        spread_home_point,
        spread_home_price,
        spread_away_point,
        spread_away_price,
        bookmaker: preferredBook.title ?? null,
        bookmaker_key: preferredBook.key ?? null,
        bookmaker_title: preferredBook.title ?? null,
        market: "summary",
        outcome_name: "summary",
        price: null,
        point: null,
      };

      // --- Rows B: "market snapshots" (h2h + spreads) ---
      // These are what your unique index is protecting (to prevent duplicates).
      const marketRows: any[] = [];

      if (h2h) {
        for (const o of h2h.outcomes) {
          marketRows.push({
            sport: "nba",
            event_id: e.id,
            start_time: null,
            commence_time: e.commence_time,
            captured_at,
            home_team: e.home_team,
            away_team: e.away_team,
            ml_home,
            ml_away,
            spread_home_point,
            spread_home_price,
            spread_away_point,
            spread_away_price,
            bookmaker: preferredBook.title ?? null,
            bookmaker_key: preferredBook.key ?? null,
            bookmaker_title: preferredBook.title ?? null,
            market: "h2h",
            outcome_name: o.name,
            price: o.price,
            point: null,
          });
        }
      }

      if (spreads) {
        for (const o of spreads.outcomes) {
          marketRows.push({
            sport: "nba",
            event_id: e.id,
            start_time: null,
            commence_time: e.commence_time,
            captured_at,
            home_team: e.home_team,
            away_team: e.away_team,
            ml_home,
            ml_away,
            spread_home_point,
            spread_home_price,
            spread_away_point,
            spread_away_price,
            bookmaker: preferredBook.title ?? null,
            bookmaker_key: preferredBook.key ?? null,
            bookmaker_title: preferredBook.title ?? null,
            market: "spreads",
            outcome_name: o.name,
            price: o.price,
            point: o.point ?? null,
          });
        }
      }

      // Upsert summary row (conflict key includes point coalesce in index, so summary won't collide since market/outcome are 'summary')
      {
        const { error } = await supabase
          .from("closing_lines")
          .upsert(summaryRow, {
            onConflict: "sport,event_id,bookmaker_key,market,outcome_name,point",
          });

        if (error) {
          console.log("[close_nba] summary upsert error", e.id, error.message);
          skipped++;
          continue;
        }
      }

      // Upsert market rows (this is the important part — duplicates become updates, not failures)
      if (marketRows.length > 0) {
        const { error, data } = await supabase
          .from("closing_lines")
          .upsert(marketRows, {
            onConflict: "sport,event_id,bookmaker_key,market,outcome_name,point",
          });

        if (error) {
          console.log("[close_nba] market upsert error", e.id, error.message);
          skipped++;
          continue;
        }

        // Supabase upsert doesn't reliably return per-row inserted vs updated counts,
        // so we treat successful upsert as "captured".
        inserted++;
      } else {
        skipped++;
      }
    }

    return new Response(
      JSON.stringify({
        ok: true,
        window_minutes: CLOSE_WINDOW_MINUTES,
        found_starting_soon: startingSoon.length,
        inserted,
        skipped,
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return new Response(JSON.stringify({ ok: false, error: message }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});