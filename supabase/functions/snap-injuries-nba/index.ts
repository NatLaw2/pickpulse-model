// supabase/functions/snap-injuries-nba/index.ts
import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const ESPN_URL =
  "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries";

function json(res: unknown, status = 200) {
  return new Response(JSON.stringify(res), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

serve(async (req) => {
  try {
    // Optional gate: allow anon JWT calls (like your odds function) OR require secret
    // For now, we’ll just allow anon calls.
    const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

    if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
      return json(
        {
          ok: false,
          error:
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in function env vars",
        },
        500,
      );
    }

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // Fetch ESPN injuries
    const resp = await fetch(ESPN_URL, {
      headers: {
        "user-agent": "pickpulse/1.0",
        accept: "application/json",
      },
    });

    if (!resp.ok) {
      const text = await resp.text();
      return json(
        { ok: false, error: "ESPN fetch failed", status: resp.status, text },
        502,
      );
    }

    const data = await resp.json();
    const pulledAt = new Date().toISOString();

    const injuries = data?.injuries ?? [];
    const rows: any[] = [];

    for (const teamBlock of injuries) {
      const teamId = String(teamBlock?.id ?? "");
      const teamName = String(teamBlock?.displayName ?? "");

      const list = teamBlock?.injuries ?? [];
      for (const item of list) {
        const athlete = item?.athlete ?? {};
        const athleteId = athlete?.id ? String(athlete.id) : null;
        const athleteName = athlete?.displayName
          ? String(athlete.displayName)
          : null;

        rows.push({
          pulled_at: pulledAt,
          team_id: teamId || null,
          team_name: teamName || null,
          athlete_id: athleteId,
          athlete_name: athleteName,
          status: item?.status ? String(item.status) : null,
          date: item?.date ? String(item.date) : null,
          short_comment: item?.shortComment ? String(item.shortComment) : null,
          long_comment: item?.longComment ? String(item.longComment) : null,
          raw: item,
        });
      }
    }

    // If no injuries (rare), still return ok and write nothing
    if (rows.length === 0) {
      return json({
        ok: true,
        pulled_at: pulledAt,
        teams_seen: injuries.length,
        injuries_written: 0,
        note: "No injuries found in payload",
      });
    }

    // Insert
    const { error } = await supabase
      .from("injury_snapshots_nba")
      .insert(rows);

    if (error) {
      return json({ ok: false, error }, 500);
    }

    return json({
      ok: true,
      pulled_at: pulledAt,
      teams_seen: injuries.length,
      injuries_written: rows.length,
    });
  } catch (e) {
    return json({ ok: false, error: String(e) }, 500);
  }
});