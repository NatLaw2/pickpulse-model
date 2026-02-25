# PEOS Pitch Deck Outline

**Target length:** 10-12 slides | **Target time:** 20 minutes + 10 min Q&A

---

## Slide 1: Title

- **Predictive Engine OS**
- Scored priorities. Measurable lift. 21 days to production.
- Tagline: "Your data in, calibrated scores out."
- Company logo, presenter name, date

---

## Slide 2: The Problem

- Sales teams rely on gut feel and CRM stage labels to prioritize pipeline. Stage labels (e.g., "Negotiation") reflect process steps, not actual probability.
- CS teams find out about churn when the customer cancels. Reactive retention is 3-5x more expensive than proactive intervention.
- Existing forecasting is based on rep self-reporting, which consistently inflates pipeline by 20-40%.
- **The cost:** Reps waste cycles on deals that were never going to close. CS misses the customers who needed attention three months ago.

---

## Slide 3: The Solution — PEOS

- A predictive decision engine that connects to your existing data and outputs calibrated probability scores.
- Two modules:
  - **Sales Module:** Deal Close Probability (0-100 score per opportunity)
  - **Churn Module:** Customer Churn Risk (0-100 risk score per account)
- Not a dashboard. Not a BI tool. A scoring engine that tells your team exactly where to focus, with proof that the scores work.
- Integrates via CSV batch or real-time REST API. No rip-and-replace.

---

## Slide 4: How It Works

- **Step 1 — Data In:** Export from your CRM (Salesforce, HubSpot, or flat CSV). Standard fields: deal stage, amount, close date, activity history, tenure, usage.
- **Step 2 — Validation & Enrichment:** We validate schema, flag missing values, compute derived features (velocity, engagement decay, etc.).
- **Step 3 — Model Training:** Gradient-boosted model trained on your historical win/loss or churn/retain outcomes. Holdout validation. Backtest against verifiable past periods.
- **Step 4 — Scores Out:** Every record gets a score. Delivered as CSV, PDF report, or real-time API response.
- **Step 5 — Retraining:** Models are retrained on your cadence (monthly or quarterly) to stay calibrated as your business changes.

---

## Slide 5: Demo Flow

- Walk through the end-to-end workflow live:
  1. Upload a sample dataset (anonymized)
  2. Show data validation output (field mapping, completeness report)
  3. Trigger model training, show training log
  4. Display evaluation results: AUC, lift chart, calibration plot
  5. Generate scored predictions on new data
  6. Show API endpoint returning a score in real time
- **Key point:** This is the same workflow your data runs through. No black box.

---

## Slide 6: Sales Module Deep Dive

- **Input:** Historical opportunity data — stage, amount, close date, days in stage, activity counts, rep, lead source, account firmographics
- **Output:** Calibrated close probability per opportunity
- **What "calibrated" means:** If 100 deals are scored at 60%, approximately 60 of them close. We show the calibration chart to prove it.
- **Use cases:**
  - Rep prioritization: Focus time on highest-probability deals
  - Forecast accuracy: Replace gut with math. Roll up scores for bottoms-up forecast.
  - Manager coaching: Identify deals where model and rep disagree — those are coaching moments.
- **Feature importance:** See which variables (e.g., "days since last activity," "number of stakeholders") move the needle, so reps learn what actually correlates with winning.

---

## Slide 7: Churn Module Deep Dive

- **Input:** Customer data — tenure, contract value, usage/engagement metrics, support tickets, NPS, billing history
- **Output:** Churn risk score (0-100) per account
- **Use cases:**
  - Proactive outreach: CS team gets a prioritized list of at-risk accounts, not just the ones who already complained
  - QBR targeting: Focus executive reviews on accounts with rising risk
  - Expansion signals: Low-risk, high-usage accounts are expansion candidates — model flags both ends
- **Feature importance:** Understand which behaviors predict churn (e.g., "login frequency dropped 40% in last 30 days") so CS can address root causes, not symptoms.

---

## Slide 8: Metrics We Deliver

- **AUC (Area Under Curve):** Measures the model's ability to rank-order outcomes. Typical PEOS models: 0.78-0.88 AUC. Random guessing = 0.50.
- **Lift:** Top-decile lift shows how much better the model's top-scored records perform vs. the average. Typical: 2.5-4x lift in top decile.
- **Calibration:** A calibration plot shows predicted probabilities vs. observed outcomes. We publish this with every scoring run.
- **Why this matters:** These are not vanity metrics. They are auditable proof that the model works on your data, delivered before you go live and with every retraining cycle.
- Show sample calibration chart, lift chart, and AUC curve (use actual backtest visuals from platform).

---

## Slide 9: Implementation Timeline — 21 Days

- **Day 1:** Kickoff call. Data template delivered. Fields mapped.
- **Day 2-5:** Customer sends data. We validate, enrich, and confirm readiness.
- **Day 6-8:** Model training and backtesting. Internal quality review.
- **Day 9-12:** Performance review meeting with stakeholder. Walk through AUC, lift, calibration. Adjust if needed.
- **Day 13-15:** Integration setup — CSV delivery pipeline or API provisioning.
- **Day 16-18:** UAT. Customer validates scores against known outcomes. Tuning pass if needed.
- **Day 19-21:** Go-live. First scored output delivered. Handoff documentation.
- **After go-live:** Monthly (API) or quarterly (Batch) retraining. Monthly performance report.

---

## Slide 10: Pricing

| | Batch Tier | API Tier |
|---|---|---|
| Setup | $5,000 | $15,000 |
| Monthly | $2,000/mo | $5,000/mo |
| Delivery | Monthly CSV + PDF report | Real-time REST API + webhooks |
| Retraining | Quarterly | Monthly |
| Support | Email (48hr SLA) | Dedicated Slack (4hr SLA) |

- **Multi-module discount:** Run both Sales + Churn modules at 20% off combined monthly.
- **Annual commitment:** 12-month contract, paid monthly or upfront (10% discount on annual prepay).
- No per-seat pricing. No per-record pricing below 50K records/month.

---

## Slide 11: Case Studies (Placeholder)

- **Case Study 1 — [B2B SaaS Company]:**
  - Problem: 35% forecast accuracy, reps spending equal time on all deals
  - Result: AUC 0.83, top-decile lift 3.2x, forecast accuracy improved to 72%
  - Timeline: Live in 18 days

- **Case Study 2 — [Subscription Business]:**
  - Problem: 14% annual churn, CS team reactive
  - Result: AUC 0.81, identified 62% of churners in top-risk quintile, churn reduced to 9% after two quarters
  - Timeline: Live in 21 days

- **Case Study 3 — [Mid-Market Company]:**
  - Problem: No data science team, needed scoring without hiring
  - Result: Both modules deployed, integrated via CSV. Team uses scored exports in weekly pipeline reviews.
  - Timeline: Live in 14 days

*[Replace with real case studies as they become available]*

---

## Slide 12: Call to Action

- **Next step:** 30-minute technical walkthrough
  - We will review a scored output sample
  - Map your CRM fields to our model inputs
  - Confirm scope and 21-day timeline
- **What we need from you:** A CRM export (or description of available fields) and 30 minutes with someone who owns pipeline or retention data
- **Contact:** [sales@pickpulse.com] | [calendly link]
- "No 6-month implementation. No new tooling to learn. Data in, scores out, 21 days."
