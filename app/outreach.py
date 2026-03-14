"""AI Outreach Drafts — generate CSM retention emails for at-risk accounts."""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

import openai

from .auth import get_tenant_id

logger = logging.getLogger("pickpulse.outreach")

router = APIRouter(prefix="/api/outreach", tags=["outreach"])

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OUTREACH_AI_MODEL = os.environ.get("OUTREACH_AI_MODEL", "gpt-4o-mini")

RATE_LIMIT_MAX = 20        # requests per window
RATE_LIMIT_WINDOW = 3600   # 1 hour in seconds

VALID_TONES = {"friendly", "direct", "executive"}

# ---------------------------------------------------------------------------
# In-memory rate limiter  (keyed by user_id / sub claim)
# ---------------------------------------------------------------------------
_rate_store: dict[str, list[float]] = {}


def _check_rate_limit(user_id: str) -> None:
    """Raise 429 if user has exceeded RATE_LIMIT_MAX requests in the window."""
    now = time.time()
    timestamps = _rate_store.get(user_id, [])
    # Prune expired entries
    timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(timestamps) >= RATE_LIMIT_MAX:
        retry_after = int(RATE_LIMIT_WINDOW - (now - timestamps[0])) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {RATE_LIMIT_MAX} requests per hour.",
            headers={"Retry-After": str(retry_after)},
        )
    timestamps.append(now)
    _rate_store[user_id] = timestamps


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class DraftEmailRequest(BaseModel):
    account_id: str = Field(..., max_length=200)
    customer_name: Optional[str] = Field(None, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=200)
    contact_email: Optional[str] = Field(None, max_length=200)
    churn_risk_pct: float
    arr: float
    arr_at_risk: float
    days_until_renewal: int
    recommended_action: Optional[str] = Field(None, max_length=500)
    risk_driver_summary: Optional[str] = Field(None, max_length=500)
    tier: Optional[str] = Field(None, max_length=50)
    tone: str = "friendly"

    @field_validator("account_id", "customer_name", "contact_name",
                     "contact_email", "recommended_action",
                     "risk_driver_summary", "tier", "tone", mode="before")
    @classmethod
    def trim_whitespace(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("tone")
    @classmethod
    def validate_tone(cls, v: str) -> str:
        if v not in VALID_TONES:
            raise ValueError(f"tone must be one of: {', '.join(sorted(VALID_TONES))}")
        return v


class DraftEmailResponse(BaseModel):
    subject: str
    body: str
    mailto_url: str


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
TONE_INSTRUCTIONS = {
    "friendly": "Warm and conversational. Use their first name. Light, approachable tone.",
    "direct": "Concise and data-aware. No small talk. Get to the point quickly.",
    "executive": "Formal and strategic. Frame around business impact and partnership value.",
}

SYSTEM_PROMPT = """You are a Customer Success manager writing a retention outreach email.

STRICT RULES — you must follow all of these:
1. Write EXACTLY 4 sentences. No more, no less.
2. Suggest a 15-minute call as the CTA.
3. NEVER use the words: churn, risk, score, at-risk, attrition, or retention.
4. NEVER apologize or use words like "sorry" or "apologize".
5. NEVER overpromise — do not use "guarantee", "promise", or "ensure".
6. If risk signals are provided, reference them obliquely (e.g. "I noticed some shifts in how your team is using the platform") — never state metrics or scores.
7. Focus on product value and partnership.
8. Keep the total body under 120 words.

Return ONLY a JSON object with two keys: "subject" and "body".
Do not include any other text, markdown, or explanation."""


def _build_user_prompt(req: DraftEmailRequest) -> str:
    """Build the user prompt from the request fields."""
    contact = req.contact_name or req.customer_name or req.account_id
    lines = [
        f"Account: {req.customer_name or req.account_id}",
        f"Contact name: {contact}",
        f"ARR: ${req.arr:,.0f}",
        f"Days until renewal: {req.days_until_renewal}",
    ]
    if req.risk_driver_summary:
        lines.append(f"Recent engagement signals: {req.risk_driver_summary}")
    if req.recommended_action:
        lines.append(f"Recommended action: {req.recommended_action}")

    lines.append(f"\nTone: {TONE_INSTRUCTIONS[req.tone]}")
    lines.append("\nGenerate the outreach email as JSON: {\"subject\": \"...\", \"body\": \"...\"}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fallback template
# ---------------------------------------------------------------------------
def _fallback_email(req: DraftEmailRequest) -> dict[str, str]:
    """Return a safe, hardcoded email when AI generation fails."""
    name = req.contact_name or req.customer_name or "there"
    return {
        "subject": "Quick check-in",
        "body": (
            f"Hi {name},\n\n"
            f"I wanted to reach out and see how things are going with the platform. "
            f"We have some updates that I think could be valuable for your team. "
            f"Would you have 15 minutes this week for a quick call? "
            f"I'd love to hear what's working well and where we can help.\n\n"
            f"Best,\n[Your Name]"
        ),
    }


# ---------------------------------------------------------------------------
# Mailto construction
# ---------------------------------------------------------------------------
def build_mailto(to: str | None, subject: str, body: str) -> str:
    """Build a properly encoded mailto: URL."""
    params = {"subject": subject, "body": body}
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    if to:
        return f"mailto:{urllib.parse.quote(to, safe='@.')}?{query}"
    return f"mailto:?{query}"


# ---------------------------------------------------------------------------
# OpenAI call
# ---------------------------------------------------------------------------
def _generate_email(req: DraftEmailRequest) -> dict[str, str]:
    """Call OpenAI and return {subject, body}. Falls back on failure."""
    client = openai.OpenAI(api_key=OPENAI_API_KEY)

    try:
        response = client.chat.completions.create(
            model=OUTREACH_AI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(req)},
            ],
            max_tokens=300,
            temperature=0.7,
        )
        raw = response.choices[0].message.content or ""
    except Exception as e:
        logger.warning("OpenAI call failed: %s", e)
        return _fallback_email(req)

    # Defensive JSON parsing
    try:
        data = json.loads(raw)
        subject = data.get("subject", "").strip()
        body = data.get("body", "").strip()
        if not subject or not body:
            raise ValueError("Missing subject or body in response")
        return {"subject": subject, "body": body}
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to parse OpenAI response: %s — raw: %s", e, raw[:300])
        return _fallback_email(req)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.post("/draft-email", response_model=DraftEmailResponse)
async def draft_outreach_email(
    req: DraftEmailRequest,
    user_id: str = Depends(get_tenant_id),
) -> DraftEmailResponse:
    """Generate a CSM outreach email for an at-risk account."""
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY not configured. Add it to your .env file.",
        )

    _check_rate_limit(user_id)

    email = _generate_email(req)
    mailto_url = build_mailto(req.contact_email, email["subject"], email["body"])

    logger.info(
        "outreach_email_generated",
        extra={
            "user_id": user_id,
            "account_id": req.account_id,
            "churn_risk_pct": req.churn_risk_pct,
            "arr": req.arr,
            "has_recipient_email": req.contact_email is not None,
            "tone": req.tone,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return DraftEmailResponse(
        subject=email["subject"],
        body=email["body"],
        mailto_url=mailto_url,
    )
