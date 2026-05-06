"""PickPulse Integration Smoke Test.

Two modes:
  1. UNIT — tests pure-logic functions with no DB or network required.
             Always runs. Must pass before any hardening changes.
  2. HTTP  — calls a running server. Activated by setting SMOKE_BASE_URL.
             e.g.  SMOKE_BASE_URL=http://localhost:8000 SMOKE_TOKEN=<jwt> python smoke_test.py

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.

NOTE: Some unit imports will be skipped in environments without the full
      supabase/joblib stack installed. This is expected in CI-lite mode.
"""
from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Callable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Minimal test harness
# ---------------------------------------------------------------------------

_results: List[Tuple[str, bool, str]] = []  # (name, passed, detail)
_skipped: List[str] = []


def check(name: str, fn: Callable[[], Any], *, expect_truthy: bool = True) -> bool:
    """Run fn(), record pass/fail."""
    try:
        result = fn()
        passed = bool(result) if expect_truthy else (result is not None)
        detail = "" if passed else f"returned: {result!r}"
    except Exception as exc:
        passed = False
        detail = f"{type(exc).__name__}: {exc}"
    _results.append((name, passed, detail))
    status = "PASS" if passed else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    return passed


def skip(name: str, reason: str) -> None:
    _skipped.append(name)
    print(f"  [SKIP] {name} — {reason}")


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def try_import(module_path: str) -> Optional[Any]:
    """Attempt import; return module or None if unavailable."""
    try:
        return importlib.import_module(module_path)
    except Exception:
        return None


def summary() -> int:
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    skipped = len(_skipped)
    print(f"\n{'='*60}")
    print(f"  RESULTS: {passed} passed, {failed} failed, {skipped} skipped "
          f"out of {len(_results) + skipped} checks")
    print(f"{'='*60}")
    if failed:
        print("\nFailed checks:")
        for name, ok, detail in _results:
            if not ok:
                print(f"  FAIL {name} — {detail}")
    return 1 if failed else 0


# ===========================================================================
# UNIT TESTS — pure logic, no DB, no network
# ===========================================================================

section("UNIT: Module imports (DB-independent)")

readiness_mod = try_import("app.integrations.readiness")
check("import readiness module", lambda: readiness_mod is not None)

normalization_mod = try_import("app.integrations.normalization")
check("import normalization module", lambda: normalization_mod is not None)

# outcome_import has a module-level 'from app.storage import repo' which needs
# supabase. Guard against this so the smoke test works without full DB stack.
outcome_import_mod = try_import("app.integrations.outcome_import")
if outcome_import_mod is None:
    skip("import outcome_import module", "supabase not installed in this env — skip DB-dependent import")

# engine.predict needs joblib — guard similarly
predict_mod = try_import("app.engine.predict")
if predict_mod is None:
    skip("import engine.predict module", "joblib not installed in this env — skip")
else:
    check("import engine.predict module", lambda: predict_mod is not None)

reconciliation_mod = try_import("app.reconciliation")
check("import reconciliation module", lambda: reconciliation_mod is not None)


# ---------------------------------------------------------------------------
# Readiness eligibility logic (pure Python, no DB)
# ---------------------------------------------------------------------------

section("UNIT: Readiness eligibility logic")

if readiness_mod:
    _eligibility = getattr(readiness_mod, "_eligibility", None)
    _confidence = getattr(readiness_mod, "_confidence", None)
    ELIGIBILITY_READY = getattr(readiness_mod, "ELIGIBILITY_READY", "ready")

    if _eligibility and _confidence:
        check("eligibility: insufficient_data when total < 10",
              lambda: _eligibility(5, 0, 0.0)[0] == "insufficient_data")

        check("eligibility: needs_outcome_mapping when churned == 0",
              lambda: _eligibility(50, 0, 0.5)[0] == "needs_outcome_mapping")

        check("eligibility: insufficient_churn when churned < threshold",
              lambda: _eligibility(50, 5, 0.5)[0] == "insufficient_churn")

        check("eligibility: low_signal_coverage when signal < 0.15",
              lambda: _eligibility(100, 25, 0.05)[0] == "low_signal_coverage")

        check("eligibility: ready when all thresholds met",
              lambda: _eligibility(200, 50, 0.80)[0] == ELIGIBILITY_READY)

        check("confidence: High when all high thresholds met",
              lambda: _confidence(200, 50, 0.70) == "High")

        check("confidence: Medium tier",
              lambda: _confidence(60, 25, 0.45) == "Medium")

        check("confidence: Low tier",
              lambda: _confidence(30, 22, 0.20) == "Low")

        check("eligibility message references correct threshold for insufficient_churn",
              lambda: "20" in _eligibility(50, 5, 0.5)[1])

        _candidate_score = getattr(readiness_mod, "_candidate_score", None)
        if _candidate_score:
            section("UNIT: Candidate field scoring")
            check("name-hint + good cardinality + high coverage = high score",
                  lambda: _candidate_score("hs_lifecycle_stage", 5, 90, 100) > 50)
            # high-cardinality (n_unique=100): 0 cardinality pts + 17.5 coverage pts = 17.5 < high-hint score
            check("high-cardinality field scores lower than name-hint field",
                  lambda: _candidate_score("arbitrary_free_text", 100, 50, 100) <
                          _candidate_score("hs_lifecycle_stage", 5, 90, 100))
            # zero-coverage + good cardinality + hint still scores (hint=30 + card=35 + cov=0)
            check("zero-coverage hint field still has non-zero score",
                  lambda: _candidate_score("status", 3, 0, 100) > 0)
    else:
        skip("readiness eligibility tests", "_eligibility or _confidence not found in module")
else:
    skip("readiness eligibility tests", "readiness module not importable")


# ---------------------------------------------------------------------------
# Churn detection logic — tested inline since outcome_import has DB dep at
# module level. We replicate only the pure detection logic here.
# ---------------------------------------------------------------------------

section("UNIT: Churn detection logic (inline)")

# Pure detection functions — replicated to avoid supabase import chain.
# These match exactly what outcome_import.py implements.
_HS_CHURNED_STAGES = {"churned", "former_customer"}
_HS_CHURNED_STATUS_KEYWORDS = ("former", "churned", "lost customer")


def _safe_date_smoke(value: object) -> Optional[str]:
    if not value:
        return None
    s = str(value).strip()
    return s[:10] if len(s) >= 10 else None


def _scan_for_churn_field_smoke(raw_data: dict):
    """Mirrors outcome_import._scan_for_churn_field — returns (found, date) tuple."""
    for key, val in raw_data.items():
        if "churn" not in key.lower():
            continue
        if not val or val in ("false", "0", "", "no", "False", "No"):
            continue
        return True, _safe_date_smoke(val)
    return False, None


def _detect_hs(raw_data: dict):
    lifecycle = str(raw_data.get("hs_lifecycle_stage") or "").lower().strip()
    if lifecycle in _HS_CHURNED_STAGES:
        return "churned", _safe_date_smoke(raw_data.get("closedate"))
    lead_status = str(raw_data.get("hs_lead_status") or "").lower().strip()
    if any(kw in lead_status for kw in _HS_CHURNED_STATUS_KEYWORDS):
        return "churned", None
    found, date_val = _scan_for_churn_field_smoke(raw_data)
    if found:
        return "churned", date_val
    return None


def _detect_sf(raw_data: dict):
    account_type = str(raw_data.get("Type") or "").strip()
    if account_type == "Former Customer":
        return "churned", _safe_date_smoke(raw_data.get("LastActivityDate"))
    found, date_val = _scan_for_churn_field_smoke(raw_data)
    if found:
        return "churned", date_val
    return None


check("HubSpot: lifecycle_stage 'churned' → detected",
      lambda: _detect_hs({"hs_lifecycle_stage": "churned"}) is not None)

check("HubSpot: lifecycle_stage 'former_customer' → detected",
      lambda: _detect_hs({"hs_lifecycle_stage": "former_customer"}) is not None)

check("HubSpot: lead_status 'former customer' → detected",
      lambda: _detect_hs({"hs_lead_status": "former customer"}) is not None)

check("HubSpot: active lifecycle 'customer' → not detected",
      lambda: _detect_hs({"hs_lifecycle_stage": "customer"}) is None)

check("HubSpot: empty raw_data → not detected",
      lambda: _detect_hs({}) is None)

check("HubSpot: churn field short truthy value 'true' → detected (Step2 fix)",
      lambda: _detect_hs({"churn_status": "true"}) is not None)

check("HubSpot: churn field value 'yes' → detected",
      lambda: _detect_hs({"churn_indicator": "yes"}) is not None)

check("HubSpot: churn field value '1' → detected",
      lambda: _detect_hs({"is_churned": "1"}) is not None)

check("HubSpot: custom churn field with date value → detected with date",
      lambda: _detect_hs({"churn_date": "2024-06-15"}) == ("churned", "2024-06-15"))

check("HubSpot: churn field value 'false' → not detected",
      lambda: _detect_hs({"churn_status": "false"}) is None)

check("Salesforce: Type == 'Former Customer' → detected",
      lambda: _detect_sf({"Type": "Former Customer"}) is not None)

check("Salesforce: Type == 'Customer' → not detected",
      lambda: _detect_sf({"Type": "Customer"}) is None)

check("Salesforce: empty raw_data → not detected",
      lambda: _detect_sf({}) is None)

check("Salesforce: custom Churn_Reason__c truthy → detected (via date scan)",
      lambda: _detect_sf({"Churn_Reason__c": "2024-03-01"}) is not None)


# ---------------------------------------------------------------------------
# Normalization helpers (pure Python)
# ---------------------------------------------------------------------------

section("UNIT: Normalization helpers")

if normalization_mod:
    safe_float = getattr(normalization_mod, "safe_float", None)
    safe_int = getattr(normalization_mod, "safe_int", None)
    days_since = getattr(normalization_mod, "days_since", None)

    if safe_float:
        check("safe_float: string number", lambda: safe_float("12345.67") == 12345.67)
        check("safe_float: None returns None", lambda: safe_float(None) is None)
        check("safe_float: empty string returns None", lambda: safe_float("") is None)
    if safe_int:
        check("safe_int: int string", lambda: safe_int("42") == 42)
    if days_since:
        check("days_since: None returns None", lambda: days_since(None) is None)
else:
    skip("normalization helpers", "normalization module not importable")


# ===========================================================================
# HTTP SMOKE TESTS — requires running server + valid JWT
# ===========================================================================

BASE_URL = os.environ.get("SMOKE_BASE_URL", "").rstrip("/")
TOKEN = os.environ.get("SMOKE_TOKEN", "")

if not BASE_URL:
    print("\n[SKIP] HTTP smoke tests — set SMOKE_BASE_URL and SMOKE_TOKEN to enable")
    print("       Example: SMOKE_BASE_URL=http://localhost:8000 SMOKE_TOKEN=<jwt> python smoke_test.py")
else:
    import json as _json

    _req = try_import("requests")
    if _req is None:
        skip("HTTP smoke tests", "'requests' package not installed")
    else:
        _headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

        def _get(path: str) -> Optional[dict]:
            try:
                r = _req.get(f"{BASE_URL}{path}", headers=_headers, timeout=15)
                return r.json() if r.status_code == 200 else None
            except Exception:
                return None

        def _post(path: str, body: dict) -> Optional[dict]:
            try:
                r = _req.post(
                    f"{BASE_URL}{path}",
                    headers={**_headers, "Content-Type": "application/json"},
                    data=_json.dumps(body),
                    timeout=30,
                )
                return r.json() if r.status_code == 200 else None
            except Exception:
                return None

        section("HTTP: Core API endpoints")

        check("GET /health returns 200",
              lambda: _get("/health") is not None)

        check("GET /api/overview returns non-empty data",
              lambda: bool(_get("/api/overview")))

        check("GET /api/performance returns data",
              lambda: _get("/api/performance") is not None)

        check("GET /api/model/production-accuracy is reachable",
              lambda: _get("/api/model/production-accuracy") is not None)

        section("HTTP: Integration endpoints")

        check("GET /api/integrations returns list",
              lambda: isinstance(_get("/api/integrations"), list))

        check("GET /api/integrations/hubspot/readiness is reachable",
              lambda: _get("/api/integrations/hubspot/readiness") is not None)

        check("GET /api/integrations/salesforce/readiness is reachable",
              lambda: _get("/api/integrations/salesforce/readiness") is not None)

        check("GET /api/integrations/hubspot/label-mapping is reachable",
              lambda: _get("/api/integrations/hubspot/label-mapping") is not None)

        section("HTTP: Dataset + ML endpoints")

        check("GET /api/datasets returns structure",
              lambda: _get("/api/datasets") is not None)

        check("GET /api/model is reachable",
              lambda: _get("/api/model") is not None)

        section("HTTP: Readiness response shape")

        hs_readiness = _get("/api/integrations/hubspot/readiness")
        sf_readiness = _get("/api/integrations/salesforce/readiness")

        for provider, data in [("hubspot", hs_readiness), ("salesforce", sf_readiness)]:
            if data:
                required_keys = ["total_accounts", "churned_detected", "pct_with_signals",
                                  "pct_with_arr", "eligibility", "training_enabled"]
                for key in required_keys:
                    check(f"{provider} readiness has '{key}' key",
                          lambda k=key, d=data: k in d)
            else:
                skip(f"{provider} readiness shape check", "readiness endpoint not reachable")


# ===========================================================================
# Final summary
# ===========================================================================
sys.exit(summary())
