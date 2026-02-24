# PickPulse Pilot Proposal

**Client:** {{Client Name}}
**Date:** {{Date}}
**Prepared by:** {{PickPulse Contact}}
**Valid through:** {{Expiration Date}}

---

## Executive Summary

{{Client Name}} faces the challenge common to all subscription businesses: identifying at-risk accounts before they churn. Traditional indicators—late payments, support ticket volume, declining usage—are lagging signals. By the time they surface, the customer relationship may already be unsalvageable. PickPulse addresses this gap by building a predictive churn model calibrated specifically to your business, trained on your historical data, and designed to surface risk 30-90 days before renewal.

This pilot engagement will prove PickPulse's ability to accurately identify churn risk within your portfolio. We will ingest your account data, train a gradient-boosted classification model on historical renewals, and validate performance against a held-out test set. The output is a ranked list of at-risk accounts with predicted churn probabilities, urgency scores, and estimated ARR exposure—delivered through executive dashboards, exportable reports, and a REST API.

The pilot is structured as a 4-6 week engagement with clear milestones, success criteria, and a defined path to production deployment. Upon successful validation, {{Client Name}} will have a proven system to prioritize customer success interventions, recover at-risk revenue, and improve gross retention.

---

## Objective

The pilot will demonstrate that PickPulse can:

- **Accurately predict account-level churn** within {{Client Name}}'s customer base using historical renewal outcomes and behavioral signals
- **Outperform baseline methods** (random selection, manual risk scoring) by measurable margins on held-out data
- **Quantify revenue exposure** by mapping churn probabilities to ARR at risk across the portfolio
- **Provide actionable insights** through executive dashboards, urgency scoring, and export/integration capabilities
- **Establish calibration confidence** by producing well-calibrated probability estimates suitable for business decision-making

Success means {{Client Name}} can confidently deploy PickPulse to guide customer success resource allocation and retention strategy.

---

## Scope

### In Scope

- **Data ingestion** from {{Client Name}}'s systems (CRM, billing, product analytics, support ticketing)
- **Historical data preparation** including feature engineering, cohort construction, and train/test splits
- **Model training** using gradient-boosted trees with hyperparameter tuning and cross-validation
- **Calibration** to ensure predicted probabilities reflect true churn rates
- **Validation** on held-out test data with performance reporting (AUC, precision/recall, calibration curves, lift charts)
- **Dashboard deployment** with account-level risk scores, urgency rankings, and ARR-at-risk summaries
- **PDF executive reports** and CSV exports for offline analysis
- **REST API** for programmatic access to predictions
- **Revenue recovery simulation** tool with adjustable save rate assumptions
- **Knowledge transfer** session to walk through model performance, feature importance, and deployment

### Out of Scope

- Integration into {{Client Name}}'s internal workflows (e.g., automatic Salesforce field updates, Slack alerting) — available post-pilot
- Real-time prediction updates — pilot operates on batch refresh cadence (daily or weekly)
- Multi-model ensembles or A/B testing infrastructure — available in full deployment
- Custom feature development beyond standard data sources listed in Data Requirements

---

## Timeline

The pilot follows a phased 4-6 week plan:

| **Phase** | **Duration** | **Activities** | **Deliverables** |
|-----------|--------------|----------------|------------------|
| **1. Data Ingestion & Preparation** | Week 1 | Data transfer, schema mapping, exploratory analysis, feature engineering | Data quality report, feature catalog |
| **2. Model Training & Tuning** | Week 2-3 | Train gradient-boosted classifier, hyperparameter optimization, cross-validation, calibration | Trained model, internal validation metrics |
| **3. Validation & Reporting** | Week 4 | Held-out test evaluation, performance metrics, calibration analysis, lift curves, feature importance | Validation report with success metric scorecard |
| **4. Deployment & Handoff** | Week 5-6 | Dashboard setup, API endpoint provisioning, user access configuration, knowledge transfer session | Live dashboard, API credentials, user documentation |

Timing assumes data availability by **{{Data Ready Date}}**. Delays in data delivery will shift the timeline accordingly.

---

## Deliverables

Upon pilot completion, {{Client Name}} receives:

- **Calibrated churn prediction model** trained on {{Client Name}} historical data
- **Executive dashboard** displaying:
  - Account-level churn probabilities and urgency scores
  - ARR-at-risk segmentation (high/medium/low risk tiers)
  - Time-to-renewal urgency indicators
  - Feature importance and top risk drivers by account
- **PDF executive report** summarizing model performance, key findings, and highest-risk accounts
- **CSV export** of all account predictions with probability scores, risk tiers, and renewal dates
- **REST API endpoint** for programmatic access to predictions (authentication included)
- **Revenue recovery simulation tool** allowing scenario planning with adjustable save rates
- **Model validation report** documenting:
  - Performance metrics (AUC, precision/recall@k, calibration error, lift curves)
  - Feature importance rankings
  - Comparison to baseline methods
  - Recommendations for production deployment
- **Knowledge transfer session** (90 minutes) covering model interpretation, dashboard usage, and integration options

---

## Data Requirements

To train and validate the churn model, PickPulse requires the following data:

### **Account Master Data**
- Account ID (unique identifier)
- Company name
- Current ARR or MRR
- Contract start date
- Contract end / renewal date
- Account tier or segment (Enterprise, Mid-Market, SMB, etc.)
- Industry vertical (optional but recommended)
- Account owner / CSM assignment

### **Renewal History**
- Historical renewal outcomes (renewed vs. churned) for past {{X}} months
- Churn date (if applicable)
- Churn reason / category (optional but valuable)

### **Usage & Engagement Data**
- Monthly or weekly active users (MAU/WAU)
- Login frequency
- Feature adoption metrics (number of features used, depth of usage)
- Data volume or transaction counts processed
- API call volume (if applicable)

### **Support & Service Data**
- Support ticket count by severity (past 90 days, past 180 days)
- Average ticket resolution time
- NPS or CSAT scores (if available)
- Professional services or onboarding completion status

### **Payment & Billing Data**
- Payment method on file (credit card vs. invoice)
- Days sales outstanding (DSO) or late payment history
- Number of seats or licenses purchased
- Expansion revenue history (upsells, cross-sells)

### **Format & Volume**
- Preferred format: CSV, Parquet, or direct database access (Snowflake, Redshift, BigQuery)
- Minimum historical depth: 12-24 months of renewal history
- Expected volume: {{Estimated Number of Accounts}} accounts

Data will be transferred via secure S3 bucket, SFTP, or direct read-only database credentials. All data handling follows SOC 2 Type II compliance standards.

---

## Success Metrics

The pilot will be evaluated against the following quantitative thresholds:

| **Metric** | **Target** | **Definition** |
|------------|------------|----------------|
| **AUC (Area Under ROC Curve)** | ≥ 0.75 | Discrimination ability: model's capacity to rank churners higher than non-churners |
| **Calibration Error** | ≤ 0.05 | Average absolute difference between predicted probabilities and observed churn rates |
| **Precision @ Top 10%** | ≥ 40% | Of the top 10% riskiest accounts, what percentage actually churn |
| **Lift @ Top 10%** | ≥ 2.5x | How much better than random selection at identifying churners in the top decile |
| **Recall @ Top 20%** | ≥ 60% | Percentage of all churners captured in the top 20% riskiest accounts |

Meeting or exceeding these thresholds demonstrates the model is production-ready and capable of driving meaningful business impact.

**Business Impact Validation:**
If {{Client Name}} has an average save rate of {{X%}} on targeted interventions, we will model expected revenue recovery based on prioritizing the top-risk decile versus current practices.

---

## Investment Options

### **Pilot Engagement**
- **Investment:** {{Pilot Price}} (one-time)
- **Duration:** 4-6 weeks
- **Included:** Full scope as outlined above
- **Payment terms:** {{Payment Terms}}

### **Post-Pilot Production Deployment**
- **Annual Subscription:** {{Annual Subscription Price}}
- **Includes:**
  - Real-time prediction updates (daily refresh)
  - Unlimited dashboard users
  - API access with {{X}} requests/month
  - Quarterly model retraining
  - Integration support (Salesforce, Slack, etc.)
  - Dedicated customer success manager
  - SLA: 99.5% uptime
- **Optional Add-Ons:**
  - Advanced workflow automation: {{Add-On Price}}
  - Multi-model A/B testing framework: {{Add-On Price}}
  - White-label reporting: {{Add-On Price}}

Pilot investment is **fully credited** toward Year 1 subscription upon conversion within {{X}} days of pilot completion.

---

## Expansion Path

Upon successful pilot validation, {{Client Name}} can move to full production deployment with:

1. **Real-time integration** into existing workflows (CRM field updates, alerting, task assignment)
2. **Continuous learning** via quarterly model retraining as new renewal outcomes are observed
3. **Expanded use cases** such as upsell/cross-sell propensity modeling, health scoring, or executive retention forecasting
4. **Multi-product support** if {{Client Name}} operates multiple product lines or business units
5. **Advanced analytics** including cohort analysis, intervention effectiveness measurement, and closed-loop feedback on save rate performance

PickPulse becomes the engine driving proactive retention strategy across the customer lifecycle.

---

## Acceptance / Signature

By signing below, both parties agree to the terms outlined in this pilot proposal.

**{{Client Name}}**

Signature: ___________________________
Printed Name: ___________________________
Title: ___________________________
Date: ___________________________

**PickPulse**

Signature: ___________________________
Printed Name: {{PickPulse Contact}}
Title: {{PickPulse Title}}
Date: ___________________________

---

**Questions or modifications?** Contact {{PickPulse Contact}} at {{Email}} or {{Phone}}.
