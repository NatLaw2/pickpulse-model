# PEOS Pricing

---

## Tier 1: Batch

**For teams that review pipeline weekly or monthly and want scored exports without infrastructure changes.**

| | |
|---|---|
| **Setup Fee** | $5,000 (one-time) |
| **Monthly Fee** | $2,000/month |
| **Contract Term** | 12 months, paid monthly |

### What's Included

**Setup (covered by setup fee):**
- Kickoff call and data field mapping
- Data validation and enrichment
- Model training on historical outcomes
- Backtesting against verifiable past periods
- Performance review with stakeholder (AUC, lift, calibration walkthrough)
- Integration setup for CSV delivery pipeline
- UAT support and go-live

**Monthly (covered by monthly fee):**
- Monthly scoring run: all active records scored and delivered as CSV
- Monthly PDF performance report: score distributions, model health metrics, top-priority accounts
- Quarterly model retraining with updated calibration metrics
- Feature importance report with each retraining cycle
- Email support with 48-hour SLA

**Volume included:** Up to 10,000 scored records per monthly run. Overage: $0.10/record.

---

## Tier 2: API

**For teams that want real-time scores embedded in their CRM or operational workflows.**

| | |
|---|---|
| **Setup Fee** | $15,000 (one-time) |
| **Monthly Fee** | $5,000/month |
| **Contract Term** | 12 months, paid monthly |

### What's Included

**Setup (covered by setup fee):**
- Everything in Batch setup, plus:
- API provisioning: REST endpoint, API keys, authentication setup
- Webhook configuration (e.g., score threshold alerts to Slack, email, or CRM)
- Integration documentation and technical onboarding for your engineering team
- CRM-specific guidance for Salesforce or HubSpot embedded score display
- Load testing and performance validation

**Monthly (covered by monthly fee):**
- Real-time scoring API: sub-200ms response time per request
- Webhook integrations: trigger actions when scores cross configurable thresholds
- Monthly model retraining with updated calibration metrics
- Monthly PDF performance report
- Feature importance report with each retraining cycle
- Monthly CSV export of all scored records (in addition to real-time API)
- Dedicated support channel (Slack or Teams) with 4-hour SLA during business hours
- Quarterly business review call with model performance deep-dive

**Volume included:** Up to 50,000 API calls per month. Overage: $0.05/call.

---

## Multi-Module Pricing

Run both Sales Module and Churn Module on the same tier:

| | Batch (Both Modules) | API (Both Modules) |
|---|---|---|
| **Setup Fee** | $8,000 (one-time) | $25,000 (one-time) |
| **Monthly Fee** | $3,200/month (20% discount) | $8,000/month (20% discount) |

Each module trains on its own outcome variable (win/loss for Sales, churn/retain for Churn) but shares the data pipeline and delivery infrastructure.

---

## Add-Ons

| Add-On | Price | Description |
|---|---|---|
| **Additional Retraining** | $1,500/cycle | Extra retraining beyond included cadence (e.g., monthly for Batch tier) |
| **Custom Feature Engineering** | $3,000 (one-time) | We build domain-specific derived features beyond our standard enrichment |
| **Historical Backfill** | $2,000 (one-time) | Score all historical records (not just current active) for trend analysis |
| **Executive Dashboard** | $1,000/month | Live web dashboard with score distributions, trends, and drill-downs |
| **Additional Volume (Batch)** | $0.10/record | Beyond 10,000 records per monthly scoring run |
| **Additional Volume (API)** | $0.05/call | Beyond 50,000 API calls per month |
| **Dedicated Account Manager** | $1,500/month | Named point of contact for Batch tier customers (included in API tier) |
| **On-Premise Deployment** | Custom pricing | Model deployed within customer's infrastructure. Requires scoping. |

---

## Contract Terms

**Term length:** 12 months. Month-to-month available at 15% premium on monthly fee.

**Annual prepay discount:** 10% discount on total annual monthly fees if paid upfront.

**Billing:** Setup fee invoiced at contract signing. Monthly fees invoiced on the 1st of each month, net-30 terms.

**Cancellation:** 60-day written notice required before contract renewal. No refund on setup fees. Monthly fees prorated if cancelled mid-month.

**SLA:**
- Batch tier: Scored CSV delivered within 3 business days of receiving updated data. Email support within 48 hours.
- API tier: 99.5% uptime SLA. Dedicated support within 4 business hours.

**Data retention:** Customer data retained for the duration of the contract plus 30 days. Data deleted upon written request or 30 days after contract termination.

**Intellectual property:** Models trained on customer data are customer-specific and not shared. Customer retains full ownership of their data. Model weights and scoring logic are proprietary to PEOS.

---

## Pricing FAQ

**Is there per-seat pricing?**
No. Pricing is per-module, not per-user. Your entire team can use the scored outputs.

**What if the model doesn't perform well on our data?**
The performance review at Day 9-12 is the checkpoint. If AUC falls below 0.72 or calibration is poor, we will tell you and discuss options (additional feature engineering, more data, or a mutual decision not to proceed). The setup fee covers the training and evaluation work regardless of outcome.

**Can we start with Batch and upgrade to API later?**
Yes. The upgrade fee is the difference in setup costs ($10,000) and the monthly fee adjusts at the next billing cycle.

**What CRM integrations are supported?**
Salesforce and HubSpot have pre-built export templates. Any CRM that can export to CSV works. API tier customers can push data from any system that can make HTTP requests.

**Do you offer a pilot or proof of concept?**
The 21-day implementation is effectively a proof of concept. You see model performance on your data at Day 9-12, before go-live. There is no separate pilot program — the standard implementation is designed to prove value quickly.
