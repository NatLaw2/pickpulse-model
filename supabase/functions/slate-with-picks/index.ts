// supabase/functions/slate-with-picks/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";

const VERSION = "slate-with-picks@events_upsert_v1";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
};

type SlateTeam = { name?: string; abbreviation?: string };
type SlateGame = {
  id: string;
  sport?: string;
  startTime?: string;
  homeTeam?: SlateTeam;
  awayTeam?: SlateTeam;
};

function sha1Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  return crypto.subtle.digest("SHA-1", data).then((buf) => {
    const bytes = new Uint8Array(buf);
    return Array.from(bytes).map((b) => b.toString(16).padStart(2, "0")).join("");
  });
}

function teamName(t?: SlateTeam): string | null {
  const n = t?.name?.trim();
  if (n) return n;
  const a = t?.abbreviation?.trim();
  if (a) return a;
  return null;
}

function teamAbbr(t?: SlateTeam): string | null {
  const a = t?.abbreviation?.trim();
  return a ? a : null;
}

function leagueFromKey(key: string): string {
  const map: Record<string, string> = {
    nba: "NBA",
    mlb: "MLB",
    nhl: "NHL",
    ncaab: "NCAAB",
    ncaaf: "NCAAF",
    nfl: "NFL",
  };
  return map[key] || key.toUpperCase();
}

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  try {
    // Allow both POST body { day: "today" } and query param ?day=today
    let day = "today";
    const url = new URL(req.url);
    const qpDay = url.searchParams.get("day");
    if (qpDay) day = qpDay;

    const debug = url.searchParams.get("debug") === "1";

    if (req.method === "POST") {
      const ct = req.headers.get("content-type") || "";
      if (ct.includes("application/json")) {
        const body = await req.json().catch(() => ({}));
        if (body?.day) day = body.day;
      }
    }

    // Forward to the existing "slate" function (same as before)
    const slateUrl = new URL(`${url.origin}/functions/v1/slate`);
    slateUrl.searchParams.set("day", day);

    // Add a cache buster so different days don’t accidentally share cached results
    if (debug) slateUrl.searchParams.set("_debug", String(Date.now()));
    else slateUrl.searchParams.set("_nocache", `${Date.now()}-${crypto.randomUUID()}`);

    const forwardHeaders: Record<string, string> = {
      "Content-Type": "application/json",
    };
    const auth = req.headers.get("authorization");
    const apikey = req.headers.get("apikey");
    if (auth) forwardHeaders["authorization"] = auth;
    if (apikey) forwardHeaders["apikey"] = apikey;

    const resp = await fetch(slateUrl.toString(), {
      method: "GET",
      headers: forwardHeaders,
    });

    const text = await resp.text();
    const payloadSha1 = debug ? await sha1Hex(text) : undefined;

    // If slate failed, return exactly what it returned (don’t try to upsert)
    if (!resp.ok) {
      return new Response(
        debug
          ? JSON.stringify({
              error: "slate call failed",
              status: resp.status,
              forwarded_to: slateUrl.toString(),
              payload_sha1: payloadSha1,
              raw: text,
            })
          : text,
        {
          status: resp.status,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      );
    }

    // Try to parse slate payload (expected JSON)
    let json: any = null;
    try {
      json = JSON.parse(text);
    } catch {
      // If parse fails, still return the text (but we can’t upsert)
      return new Response(
        debug
          ? JSON.stringify({
              ok: true,
              version: VERSION,
              note: "Could not JSON.parse slate payload; skipping events upsert",
              forwarded_to: slateUrl.toString(),
              payload_sha1: payloadSha1,
            })
          : text,
        {
          status: 200,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      );
    }

    // --- NEW: upsert events into DB ---
    // Use service role for DB writes (bypasses RLS).
    const SUPABASE_URL =
      Deno.env.get("SUPABASE_URL") || Deno.env.get("PP_SUPABASE_URL");
    const SERVICE_ROLE_KEY =
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ||
      Deno.env.get("PP_SERVICE_ROLE_KEY") ||
      Deno.env.get("SERVICE_ROLE_KEY");

    let upserted = 0;
    let upsert_error: string | null = null;

    if (SUPABASE_URL && SERVICE_ROLE_KEY) {
      const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
        auth: { persistSession: false },
      });

      const rows: any[] = [];

      for (const [key, arr] of Object.entries(json || {})) {
        if (key === "topPicks") continue;
        if (!Array.isArray(arr)) continue;

        const league = leagueFromKey(key);

        for (const g of arr as SlateGame[]) {
          if (!g?.id) continue;
          rows.push({
            event_id: g.id,
            sport: (g as any)?.sport ?? key,
            league,
            start_time: (g as any)?.startTime ?? null,
            home_team: teamName((g as any)?.homeTeam),
            away_team: teamName((g as any)?.awayTeam),
            home_abbr: teamAbbr((g as any)?.homeTeam),
            away_abbr: teamAbbr((g as any)?.awayTeam),
          });
        }
      }

      // Batch upsert (only if we have anything)
      if (rows.length > 0) {
        const { error } = await supabase
          .from("events")
          .upsert(rows, { onConflict: "event_id" });

        if (error) upsert_error = error.message;
        else upserted = rows.length;
      }
    } else {
      upsert_error =
        "Missing SUPABASE_URL and/or SUPABASE_SERVICE_ROLE_KEY in function environment";
    }

    // In debug mode, wrap the response so you can see what happened.
    // In normal mode, return the original slate payload exactly as before.
    if (debug) {
      return new Response(
        JSON.stringify({
          ok: true,
          version: VERSION,
          resolved_day: day,
          forwarded_to: slateUrl.toString(),
          payload_sha1: payloadSha1,
          events_upserted: upserted,
          events_upsert_error: upsert_error,
          // still return the actual data so you can inspect it
          data: json,
        }),
        { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    return new Response(text, {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return new Response(JSON.stringify({ error: msg }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});