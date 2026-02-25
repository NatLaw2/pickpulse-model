# PEOS Onboarding Playbook

**Timeline:** 21 days from kickoff to go-live
**Objective:** Deliver validated, scored output to the customer's team with auditable performance metrics.

---

## Pre-Kickoff (Before Day 1)

**Internal prep (PEOS team):**
- [ ] Review signed contract and confirm tier (Batch or API) and module(s) (Sales, Churn, or both)
- [ ] Assign onboarding lead and, for API tier, dedicated support contact
- [ ] Prepare customer-specific data template based on their CRM (Salesforce, HubSpot, or generic CSV)
- [ ] Set up project tracking (shared checklist or project board visible to customer)
- [ ] Schedule kickoff call with customer champion and data stakeholder

---

## Day 1: Kickoff Call

**Duration:** 45-60 minutes
**Attendees:** Customer champion, data stakeholder (RevOps, data team, or CRM admin), PEOS onboarding lead

**Agenda:**
1. Introductions and role confirmation
2. Review project timeline and milestones (walk through this playbook)
3. Confirm module(s) and use case: what decisions will be made with the scores?
4. Review data template: walk through each required and optional field
5. Discuss data export logistics: who pulls the data, from which system, in what format
6. Confirm data handling requirements: anonymization, encryption, DPA if needed
7. Set communication channel (email for Batch, Slack/Teams for API)
8. Schedule standing check-ins: Day 5 (data confirmation), Day 9-12 (performance review), Day 18 (UAT review)

**Deliverables sent to customer after kickoff:**
- [ ] Data template (spreadsheet with field names, descriptions, data types, and CRM field mapping)
- [ ] Sample anonymized scored output (so customer knows what they'll receive)
- [ ] Secure file transfer instructions (SFTP, encrypted upload link, or API push details)
- [ ] Project timeline document with dates and owners

---

## Day 2-5: Data Received, Validation, Enrichment

### Day 2-3: Data Receipt and Initial Validation

**Customer responsibility:**
- Export historical data per the template and upload via secure channel
- Minimum requirements:
  - **Sales Module:** 500+ closed opportunities with outcome (won/lost), deal attributes, and dates
  - **Churn Module:** 500+ customers with outcome (churned/retained over a defined window), account attributes, and engagement metrics

**PEOS team actions:**
- [ ] Confirm data received and acknowledge to customer within 4 hours
- [ ] Run automated schema validation:
  - Required fields present
  - Data types correct (dates are dates, numbers are numbers)
  - Outcome variable properly encoded
  - No data leakage (features that wouldn't be available at prediction time)
- [ ] Generate data quality report:
  - Field completeness percentages
  - Distribution summaries for key fields
  - Outcome class balance (win rate, churn rate)
  - Record volume by time period
- [ ] Flag issues and send to customer with specific questions

### Day 4-5: Enrichment and Feature Engineering

**PEOS team actions:**
- [ ] Resolve any data quality issues with customer (missing fields, ambiguous values)
- [ ] Compute derived features:
  - Stage velocity (days between stage transitions)
  - Activity recency and frequency (days since last activity, activity count per period)
  - Engagement decay (trend in activity over time)
  - Tenure-based features (for Churn module)
  - Amount/size-based percentile ranks
- [ ] Finalize training dataset
- [ ] Confirm with customer: "Data is validated and ready for training. Proceeding on Day 6."

**Day 5 milestone:** Data confirmation check-in with customer (15-minute call or async message).

---

## Day 6-8: Model Training and Backtesting

### Day 6-7: Model Training

**PEOS team actions:**
- [ ] Split data into training and holdout sets (time-based split preferred: train on older data, validate on more recent)
- [ ] Train gradient-boosted model with cross-validation
- [ ] Compute evaluation metrics on holdout set:
  - AUC (target: 0.72+)
  - Lift by decile (target: 2x+ in top decile)
  - Calibration plot (predicted vs. observed probabilities)
  - Precision-recall curve
- [ ] Generate feature importance rankings
- [ ] Internal quality review: does the model meet our bar?

### Day 8: Backtesting

**PEOS team actions:**
- [ ] Run backtest against a historical period the customer can verify
  - Example: train on data before Q3, predict Q3 outcomes, compare to actuals
- [ ] Document backtest results with the same metric suite (AUC, lift, calibration)
- [ ] Prepare stakeholder review deck:
  - One-page summary of model performance
  - Calibration chart
  - Lift chart with decile breakdown
  - Feature importance (top 10 features with direction of effect)
  - Backtest results
  - Any caveats or recommendations

---

## Day 9-12: Performance Review with Stakeholder

### Day 9 or 10: Performance Review Meeting

**Duration:** 45-60 minutes
**Attendees:** Customer champion, executive sponsor (if available), PEOS onboarding lead, PEOS data lead

**Agenda:**
1. Walk through model performance metrics (AUC, lift, calibration)
2. Review feature importance: "These are the variables that most influence the score. Does this align with your team's intuition?"
3. Show backtest results: "Here's how the model would have scored deals last quarter. Here's how those deals actually turned out."
4. Discuss calibration: "A score of X means Y probability. Here's the evidence."
5. Address questions and concerns
6. Decision point: proceed to integration, or adjust (more features, more data, retraining)?

**Possible outcomes:**
- **Green light:** Metrics meet bar, customer approves. Proceed to Day 13.
- **Adjust and retrain:** Customer wants to add features or we identify data improvements. Retrain by Day 12, re-review Day 12. This consumes buffer days but stays within 21-day timeline.
- **No-go:** Metrics below bar and no clear path to improvement. Honest conversation about whether to proceed. (Rare — see pricing FAQ on this scenario.)

### Day 11-12: Buffer / Adjustment

- Reserved for retraining if needed
- If green-lighted on Day 9/10, use these days to begin integration prep early

---

## Day 13-15: Integration Setup

### Batch Tier

**PEOS team actions:**
- [ ] Set up secure CSV delivery pipeline:
  - Automated scoring run triggered by customer data upload
  - Scored CSV output delivered to designated SFTP, S3 bucket, or email
  - PDF report generated and attached
- [ ] Provide customer with delivery schedule (e.g., "Upload by the 1st, scored output by the 3rd")
- [ ] Test delivery pipeline with sample run
- [ ] Document the process for customer's team

### API Tier

**PEOS team actions:**
- [ ] Provision API endpoint and generate API keys
- [ ] Configure authentication (API key or OAuth, per customer requirement)
- [ ] Set up webhook integrations (score threshold alerts, new score notifications)
- [ ] Provide API documentation:
  - Endpoint URL, authentication method
  - Request format (JSON schema with field descriptions)
  - Response format (score, confidence interval, top feature drivers)
  - Error codes and rate limits
  - Code examples (Python, cURL, JavaScript)
- [ ] Share Postman collection or equivalent for customer's engineering team
- [ ] Load test: confirm sub-200ms response time under expected volume

### Both Tiers

- [ ] Walk customer's technical contact through the integration
- [ ] Confirm customer can successfully receive/call the scoring output

---

## Day 16-18: UAT and Tuning

### Day 16-17: User Acceptance Testing

**Customer responsibility:**
- Score a batch of current records (or send live records through API)
- Review scored output against known outcomes or team intuition
- Flag any scores that seem significantly off ("We know this deal is dead but it's scored at 80%")
- Test delivery pipeline end-to-end (upload, receive scored output, verify format)

**PEOS team actions:**
- [ ] Support customer through UAT: answer questions, explain individual scores
- [ ] Investigate flagged scores: explain which features are driving them
- [ ] Document UAT findings

### Day 18: Tuning Pass (If Needed)

**PEOS team actions:**
- [ ] If UAT reveals systematic issues, make targeted adjustments:
  - Feature corrections
  - Threshold adjustments for webhook alerts
  - Output format changes
- [ ] Re-run scoring on UAT data to confirm fix
- [ ] Get customer sign-off: "Scores look right, integration works, ready for go-live."

**Day 18 milestone:** UAT review call (15-30 minutes). Confirm go-live for Day 19-21.

---

## Day 19-21: Go-Live and Handoff

### Day 19: Go-Live

**PEOS team actions:**
- [ ] Execute first production scoring run (Batch) or confirm API is live for production traffic (API)
- [ ] Deliver first production scored output to customer
- [ ] Generate and deliver first monthly performance report (PDF):
  - Score distribution
  - Model health metrics
  - Top-priority records
  - Feature importance summary

### Day 20: Handoff

**PEOS team actions:**
- [ ] Handoff meeting with customer (30 minutes):
  - Review go-live output together
  - Walk through the monthly performance report
  - Explain retraining cadence and what to expect
  - Confirm support channel and SLA
  - Introduce ongoing support contact (API tier: dedicated; Batch tier: email)
- [ ] Deliver handoff documentation:
  - [ ] Summary of model: features used, target variable, performance metrics
  - [ ] Data refresh instructions: how and when to send updated data
  - [ ] Integration guide: how to access scored output (CSV path or API docs)
  - [ ] Support escalation path
  - [ ] Retraining schedule

### Day 21: Buffer / Cleanup

- Address any remaining items from go-live
- Ensure customer has everything they need
- Close out onboarding project tracker

---

## Monthly Cadence After Go-Live

### Every Month (Both Tiers)

| Activity | Owner | Timing |
|---|---|---|
| Customer sends updated data (Batch) or data flows via API | Customer | By the 1st of the month |
| Scoring run executed | PEOS | Within 3 business days (Batch) or continuous (API) |
| Scored output delivered | PEOS | With scoring run |
| Monthly performance report (PDF) | PEOS | By the 5th of the month |
| Review report, flag questions | Customer | By the 10th |

### Monthly Retraining (API Tier)

| Activity | Owner | Timing |
|---|---|---|
| Collect latest outcome data for retraining | Customer / PEOS | Mid-month |
| Retrain model on updated data | PEOS | Within 5 business days |
| Validate retrained model (AUC, lift, calibration) | PEOS | With retraining |
| Publish updated model to production | PEOS | After validation |
| Send retraining summary to customer | PEOS | With publication |

### Quarterly Retraining (Batch Tier)

Same as monthly retraining, but executed every 3 months (Q1: January, Q2: April, Q3: July, Q4: October).

### Quarterly Business Review (API Tier)

**Duration:** 30-45 minutes
**Attendees:** Customer champion, executive sponsor (optional), PEOS account lead

**Agenda:**
1. Review model performance trends over the quarter
2. Compare current AUC, lift, calibration to baseline (initial go-live metrics)
3. Discuss any data changes (new CRM fields, process changes, market shifts)
4. Review feature importance changes: are the same variables driving scores, or has the model adapted?
5. Discuss expansion opportunities: additional modules, higher volume, new use cases
6. Gather feedback on output usability and team adoption

---

## Escalation Procedures

| Situation | Action | Timeline |
|---|---|---|
| Data quality issue blocks training | Notify customer with specific fields/records affected, propose resolution | Within 24 hours |
| Model performance below bar (AUC < 0.72) | Honest assessment to customer, propose remediation (more data, features) or mutual no-go | At Day 9-12 review |
| API downtime | Notify customer, provide status updates every 30 minutes, post-mortem within 48 hours | Immediate |
| Customer misses data delivery window | Reminder at +1 day, escalate to champion at +3 days | Automated |
| Score drift detected (performance degradation between retraining cycles) | Trigger off-cycle retraining, notify customer | Within 5 business days |

---

## Onboarding Success Criteria

The onboarding is considered complete when:

- [ ] Model is trained and validated with AUC >= 0.72 and acceptable calibration
- [ ] Customer has received at least one production scored output
- [ ] Integration is working end-to-end (customer can receive/access scores)
- [ ] Customer champion confirms scores are being reviewed by the team
- [ ] Handoff documentation delivered
- [ ] Monthly cadence is scheduled and understood by both parties
- [ ] Support channel is active and tested
