# PickPulse Intelligence — Churn Risk Module Demo Script

**Duration:** 8-10 minutes | **Audience:** VP CS, CRO, RevOps | **URL:** demo.pickpulse.co

---

## Opening (30 seconds)

> "PickPulse Intelligence is a decision ranking engine. Our first module predicts which accounts will churn, quantifies the ARR at risk, and tells you exactly where to focus your team's time. Let me show you what that looks like."

---

## Demo Flow (7 minutes)

### Screen 1: Executive Overview (Dashboard) — 2 min

Navigate to **/** (Dashboard).

**Talk through:**
- "This is the executive view. Four KPIs at the top — ARR at Risk, accounts renewing within 90 days, high-risk accounts in the renewal window, and model health."
- "ARR at Risk is probability-weighted — it is not just a count. Every account's revenue is multiplied by its churn probability."
- Point to the **Revenue Recovery Simulation** slider: "This lets you model what happens at different save rates. If your CS team retains 35% of at-risk accounts through proactive outreach, here is the projected recoverable ARR."
- Move the slider to show how the number changes.
- Scroll to the **Highest-Value Accounts at Risk** table: "These are your top 10 accounts sorted by ARR exposure. Each has a risk percentage, days until renewal, and a recommended action."

**Key message:** *"This is the daily view for your VP of CS. One screen, prioritized by dollars."*

### Screen 2: Account Scoring (Predict) — 3 min

Navigate to **/predict** and click **Generate Predictions**.

**Talk through:**
- "This scores every account in the portfolio. Each row shows the churn probability, an urgency score, renewal window, ARR, ARR at risk, and a recommended action."
- Point to the **risk badges** (High/Medium/Low): "Accounts are tiered automatically. High risk is 70%+ probability."
- Use the **risk filter** dropdown to show only High risk accounts.
- Point to the **urgency score**: "This combines churn probability with how soon the renewal is. A high-risk account renewing in 15 days scores higher than one renewing in 200 days."
- Mention the **Export CSV** button: "One click to push this into Salesforce, HubSpot, or your BI tool."
- Mention the **search bar**: "Your CSM can look up any specific account."

**Key message:** *"This is the operational view. Your team opens this every morning."*

### Screen 3: Reports — 1 min

Navigate to **/reports**.

**Talk through:**
- "Two export options. The PDF report is designed for board presentations — it includes model accuracy, lift analysis, calibration, and business impact in a format leadership expects."
- "The CSV export is the raw scored data. Import it into any tool."

**Key message:** *"Board-ready reporting without touching a spreadsheet."*

### Screen 4: Model Performance (Evaluate) — 1 min

Navigate to **/evaluate** (optional — show if audience is analytical).

**Talk through:**
- "For the data-minded: here are the model's discrimination metrics. AUC tells you how well we separate churners from non-churners. Lift at top 10% shows how much better than random targeting."
- "Calibration chart shows that when we say 60% risk, approximately 60% of those accounts actually churn. The probabilities are real."
- Point to the **Risk Tier Breakdown**: "This shows the actual churn rate in each tier against the predicted rate."

**Key message:** *"This is not a black box. The numbers are auditable."*

---

## Common Objections

| Objection | Response |
|-----------|----------|
| **"We already have health scores."** | "Health scores are weighted averages of usage metrics — they tell you who is unhappy today. PickPulse is a supervised model trained on actual churn outcomes. It predicts who will leave, with calibrated probabilities you can act on." |
| **"How long does setup take?"** | "Two to four weeks. You provide account data — ARR, renewal dates, usage signals, support tickets. We handle feature engineering, model training, and validation. Most clients are live inside of a month." |
| **"What if our churn patterns change?"** | "The model retrains on a regular cadence — monthly or quarterly. As your product evolves or cohort behavior shifts, the model adapts automatically." |

---

## Close (30 seconds)

> "What I'd suggest is a 4-6 week pilot. We train the model on your data, validate it against historical churn, and deliver a full dashboard with scored predictions. If the model hits our benchmarks — AUC above 0.75, lift above 2.5x — we move to production. No risk, clear success criteria. Want to set up a data call this week?"

---

*Prepared for PickPulse Intelligence sales team. Keep this document confidential.*
