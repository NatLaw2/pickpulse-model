#!/usr/bin/env bash
# Smoke-test the integration endpoints against a running API.
# Usage:  ./scripts/integrations_smoke.sh [BASE_URL]
set -euo pipefail

BASE="${1:-http://localhost:8000}"
PASS=0; FAIL=0

check() {
  local label="$1" method="$2" path="$3"
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$BASE$path" \
           -H "Content-Type: application/json" 2>/dev/null || echo "000")
  if [[ "$status" =~ ^2 ]]; then
    echo "  [PASS] $label ($status)"
    ((PASS++))
  else
    echo "  [FAIL] $label ($status)"
    ((FAIL++))
  fi
}

echo "=== Integration Smoke Test ==="
echo "Target: $BASE"
echo ""

check "List connectors"       GET  "/api/integrations"
check "HubSpot status"        GET  "/api/integrations/hubspot/status"
check "Stripe status"         GET  "/api/integrations/stripe/status"
check "List accounts"         GET  "/api/integrations/accounts"
check "Latest scores"         GET  "/api/integrations/scores/latest"
check "Run demo (hubspot)"    POST "/api/integrations/hubspot/run-demo"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
exit $FAIL
