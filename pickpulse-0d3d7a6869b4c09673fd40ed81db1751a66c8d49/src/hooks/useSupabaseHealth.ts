import { useEffect, useState } from "react";

type HealthStatus = { ok: true } | { ok: false; reason: string; detail?: string };

export function useSupabaseHealth() {
  const [status, setStatus] = useState<HealthStatus>({ ok: true });

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const baseUrl = import.meta.env.VITE_SUPABASE_URL;
        const anonKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

        if (!baseUrl || !anonKey) {
          throw new Error("Missing Supabase env vars");
        }

        const res = await fetch(`${baseUrl}/functions/v1/decision-slate?day=today`, {
          headers: {
            apikey: anonKey,
            authorization: `Bearer ${anonKey}`,
          },
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }

        if (!cancelled) setStatus({ ok: true });
      } catch (err: any) {
        if (!cancelled) {
          setStatus({
            ok: false,
            reason: "Picks service unavailable",
            detail: err?.message,
          });
        }
      }
    }

    check();
    return () => {
      cancelled = true;
    };
  }, []);

  return status;
}
