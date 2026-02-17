#!/usr/bin/env bash
set -euo pipefail
if [ -f .env.local ]; then
  set -a; source .env.local; set +a
fi
echo "VITE_SUPABASE_URL=${VITE_SUPABASE_URL:-<missing>}"
echo "KEY_LEN=$(echo -n "${VITE_SUPABASE_PUBLISHABLE_KEY:-}" | wc -c)"
echo "Calling performance-summary..."
curl -sS -i \
  -H "apikey: ${VITE_SUPABASE_PUBLISHABLE_KEY}" \
  -H "Authorization: Bearer ${VITE_SUPABASE_PUBLISHABLE_KEY}" \
  "${VITE_SUPABASE_URL}/functions/v1/performance-summary?mode=live&range=season" | head -120
