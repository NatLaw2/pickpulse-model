# PEOS Demo Talk Track

**Total time:** 10 minutes | **Format:** Screen share with live platform walkthrough

---

## Intro (0:00 - 0:30)

> "Thanks for taking the time. I'm going to show you exactly how Predictive Engine OS works — from raw data to scored output — in about 10 minutes. No slides. We'll use the live platform so you can see what your team would actually interact with."

> "Quick context: PEOS is a predictive scoring engine. You give it your sales or customer data, it gives you calibrated probability scores — deal close probability or churn risk — that your team uses to prioritize. I'll show you the full workflow and the metrics that prove the scores work."

---

## Problem Statement (0:30 - 1:30)

> "Let me frame why this matters. Most sales teams prioritize pipeline using CRM stage labels. 'Negotiation' sounds good, but it's a process step, not a probability. Two deals can both be in Negotiation — one is a slam dunk, the other is going nowhere. Stage labels don't tell you which is which."

> "On the churn side, CS teams usually find out a customer is at risk when they get a cancellation notice or a bad NPS score. By then, you're in recovery mode, not prevention mode."

> "The cost is real. Reps waste cycles on low-probability deals. CS loses accounts they could have saved with a conversation three months earlier. And your forecast is built on rep self-reporting, which typically inflates pipeline 20-40%."

> "PEOS fixes this by scoring every record with a calibrated probability, so your team knows exactly where to focus — and you can verify the scores are accurate before you act on them."

---

## Solution Overview (1:30 - 2:30)

> "Here's how it works at a high level. You send us your data — a CRM export, CSV, or push it through our API. We validate the schema, enrich the features, and train a model on your historical outcomes. Every record gets a score between 0 and 100."

> "The key word is 'calibrated.' If we score 100 deals at 70%, roughly 70 of them should close. We prove this with a calibration chart before go-live, and we republish it with every retraining cycle. You never have to take the scores on faith."

> "Two modules: Sales Module for deal close probability, Churn Module for customer risk. Same engine, same workflow, different outcome variable. You can run one or both."

---

## Live Demo Walkthrough (2:30 - 7:30)

### Step 1: Upload Data (2:30 - 3:15)

> "Let me show you the platform. I'm going to upload a sample dataset — this is anonymized historical opportunity data. [Click upload] You can see the fields: deal stage, amount, close date, days in stage, number of activities, lead source, rep name."

> "In production, you'd either upload a CSV on your cadence or push data through the API. Either way, this is the starting point."

> "The system runs automatic validation: checks for required fields, flags missing values, confirms data types. [Show validation output] You can see here it found 98.2% completeness, flagged three records with missing close dates, and auto-mapped fields to our schema."

### Step 2: Train the Model (3:15 - 4:15)

> "Now I'll trigger training. [Click train] The model is training on your historical win/loss outcomes. Under the hood, this is a gradient-boosted model — same family of algorithms used in production at large fintech and insurance companies for credit scoring and risk modeling."

> "Training takes anywhere from 30 seconds to a few minutes depending on data volume. [Show training log] You can see the training log here — number of records, feature count, cross-validation folds. No black box. Everything is logged."

### Step 3: Evaluate (4:15 - 5:30)

> "This is the part that matters most. [Show evaluation screen] Three metrics I want you to look at:"

> "First, AUC — 0.84 on this dataset. This measures how well the model rank-orders deals. 0.50 is random, 1.0 is perfect. 0.84 means the model puts winning deals above losing deals 84% of the time."

> "Second, the lift chart. [Point to chart] The top decile — the 10% of deals the model is most confident about — closes at 3.4x the base rate. That means if your overall win rate is 25%, the top-scored deals win at 85%. That's where your reps should spend their time."

> "Third, the calibration plot. [Point to chart] This is the proof. Each dot represents a score bucket. The x-axis is what we predicted, the y-axis is what actually happened. They should line up along the diagonal, and here they do. The model isn't overconfident or underconfident."

> "We review these charts with you before go-live. If the numbers don't clear our quality bar, we retrain or adjust before we ship scores."

### Step 4: Generate Predictions (5:30 - 6:15)

> "Now let's score new data. [Upload new records] These are current open opportunities that the model hasn't seen. [Click predict] Each one now has a score."

> "[Show scored output] You can see deal #1247 is scored at 82% — high priority. Deal #1183 is at 23% — your rep might want to deprioritize or disqualify. Deal #1302 is at 51% — worth a conversation about what's stalling it."

> "This is the output your team uses. CSV download, or if you're on the API tier, this comes back as a JSON response in real time."

### Step 5: API Demo (6:15 - 7:30)

> "For API tier customers, let me show you the endpoint. [Switch to API console] I'm going to send a single record via POST request."

> "[Send request, show response] Response time: 120ms. You get back the score, the confidence interval, and the top three features driving this particular score. So for this deal, the model is saying: 'Score is 74%, and the main drivers are high activity count, short time in stage, and multiple stakeholders involved.'"

> "This means your CRM can call our API whenever a deal updates, and the score refreshes automatically. No batch lag. Your reps see the current score right in Salesforce or HubSpot."

> "You can also set up webhooks — for example, 'notify the CS team in Slack whenever an account's churn score crosses 75.' We handle the infrastructure."

---

## Implementation (7:30 - 8:30)

> "Implementation is 21 days, not 21 weeks. Here's the timeline:"

> "Day 1, we do a kickoff call and send you a data template — it's a spreadsheet that maps your CRM fields to our model inputs. Day 2 through 5, you send us the data, we validate and enrich it. Day 6 through 8, we train the model and run backtests. Day 9 through 12, we review performance with you — we walk through the same AUC, lift, and calibration charts I just showed you, but on your data."

> "Day 13 through 15, we set up your delivery method — either a secure CSV pipeline or API provisioning with keys and documentation. Day 16 through 18 is UAT — your team validates the scores against deals they know. Day 19 through 21, we go live and deliver your first scored output."

> "After go-live, we retrain on your cadence — monthly for API tier, quarterly for Batch — and deliver a performance report every month so you can track model health."

---

## Pricing (8:30 - 9:00)

> "Two tiers. Batch tier is $5K setup, $2K a month. You get monthly CSV scoring, PDF reports, and quarterly retraining. This works well for teams that do weekly or monthly pipeline reviews."

> "API tier is $15K setup, $5K a month. You get real-time scoring, webhook integrations, monthly retraining, and a dedicated support channel. This is for teams that want scores embedded in their CRM workflow."

> "If you run both modules — Sales and Churn — we discount 20% on the combined monthly. Annual contracts, paid monthly, with a 10% discount if you prepay."

---

## Q&A Setup (9:00 - 10:00)

> "That's the full workflow — data in, model trains, scores out, metrics that prove it works, 21 days to production."

> "Before we open up for questions, let me leave you with the key takeaway: this is not a dashboard or a BI layer. It's a scoring engine. Your team gets a prioritized list backed by verifiable metrics, and the model stays current with regular retraining."

> "What questions do you have?"

---

## Common Objections and Responses

### 1. "We already have a data science team / We're building this internally."

> "That's great — having internal data science capability is a real asset. The question is whether this particular use case is the best use of their time. Building a production scoring pipeline — with retraining, monitoring, calibration, and delivery infrastructure — typically takes a data science team 3-6 months and ongoing maintenance. PEOS gets you to production in 21 days, and your data science team can focus on problems that are more specific to your business. We've had customers who started with PEOS and later brought the capability in-house using our model as a benchmark."

### 2. "How do we know the model will work on our data?"

> "Fair question, and the honest answer is: we don't know until we train on your data. That's why the implementation includes a performance review at Day 9-12 where we show you AUC, lift, and calibration on your actual historical records. If the model doesn't meet our quality bar — generally AUC above 0.72 and well-calibrated — we'll tell you, and we won't ship scores we don't trust. The setup fee covers the training and evaluation work regardless of outcome, but we've never had a dataset with reasonable volume and outcome labels where we couldn't build a useful model."

### 3. "Our data is messy / We don't have clean CRM data."

> "Most CRM data is messy — that's normal. Our validation step flags issues, and our enrichment step computes derived features that are often more predictive than raw fields. For example, 'days since last activity' and 'velocity through stages' are derived features that don't require perfectly clean source data. We do need a minimum volume — roughly 500 closed-won and closed-lost outcomes for the Sales Module — but we're flexible on field completeness. We'll tell you in the first week if the data isn't sufficient."

### 4. "What about data security? We can't share customer data externally."

> "We handle this a few ways. First, the model only needs behavioral and transactional fields — deal stage, amounts, dates, activity counts. We don't need PII like customer names, emails, or phone numbers. You can anonymize or pseudonymize identifiers before sending. Second, all data is encrypted in transit and at rest. Third, we can work with your security team during the kickoff to align on data handling requirements. We've completed security reviews with [reference customers] and can share our data processing addendum upfront."

### 5. "This is expensive. What's the ROI?"

> "Let's do the math on your numbers. If your average deal size is $50K and your reps close 20% of pipeline, a 10% improvement in win rate on rep-prioritized deals adds significant revenue. Say your team works 200 opportunities per quarter — even moving 5 additional deals from loss to win at $50K each is $250K per quarter. The API tier costs $75K per year. The question isn't whether $5K/month is expensive in isolation — it's whether a 2.5-4x lift in your top-priority deals is worth the investment. We can build a specific ROI model for your pipeline during the next call."

---

## Post-Demo Checklist

After the demo, confirm:

- [ ] Which module(s) the prospect is interested in (Sales, Churn, or both)
- [ ] What CRM they use and how data would be exported
- [ ] Approximate data volume (number of historical records, number of records to score)
- [ ] Who the internal champion is (VP Sales, VP CS, RevOps)
- [ ] Next step: technical walkthrough or data readiness assessment
- [ ] Timeline: when does the prospect want to be live?
