# PickPulse Intelligence — Demo Talk Track

*Voiceover script for Loom recording. Designed to be read naturally at a conversational pace. Approximate runtime: 5–7 minutes.*

---

## Opening (on Login screen or Overview page)

This is PickPulse Intelligence — a churn prediction and revenue protection platform built for B2B SaaS companies.

The platform takes your customer account data, trains a machine learning model on historical churn patterns, and delivers actionable predictions that help your customer success team protect recurring revenue before it's too late.

Let me walk you through how it works.

---

## Data Sources (navigate to Data Sources)

Everything starts with data. Under Data Sources, you can load your account data in a few different ways.

For this demo, we're using a prebuilt sample dataset — about a thousand accounts with fields like ARR, login activity, support tickets, NPS scores, contract details, and renewal dates. These are the kinds of signals that drive churn.

You can also upload your own CSV, or connect directly to your CRM, billing system, or support tools through the Integrations tab. We support Salesforce, HubSpot, Stripe, Zendesk, and others — with the ability to map fields to our scoring schema automatically.

Once data is loaded, the platform validates it and gives you a summary of what's available — row count, columns detected, and any missing fields or warnings.

---

## Model Training (navigate to Model)

Next, we train the model. Click over to Model, and you'll see two tabs: Train and Performance.

On the Train tab, we run a gradient-boosted classifier against your dataset. The model learns which combinations of account attributes — things like declining login frequency, low NPS, or an upcoming renewal with no auto-renew — are predictive of churn.

Training takes a few seconds. Once it's complete, you get a full evaluation automatically.

### Performance tab

Switch to the Performance tab and you'll see the model's discrimination and calibration metrics.

At the top level: AUC, precision-recall AUC, Brier score, and log loss. These tell you how well the model separates churners from retainers and how well-calibrated the probabilities are.

Below that, you'll see a calibration curve — predicted probabilities on one axis, actual churn rates on the other. A well-calibrated model hugs the diagonal. You'll also see a lift chart showing how much better the model performs versus random selection — in the top decile, we're typically capturing several times the base churn rate.

There's also a tier breakdown — High Risk, Medium Risk, Low Risk — showing how many accounts fall into each bucket and what the actual churn rate is within each tier. And a business impact section showing total value at risk and how much of it concentrates in the top decile.

You can download the full evaluation as a PDF report from the Reports page — useful for board presentations or QBRs.

---

## Accounts — Predictions (navigate to Accounts)

Now let's generate predictions. On the Accounts page, click Generate Predictions.

The platform scores every account in the portfolio and returns a ranked table. Each row shows the account name, churn risk percentage, an urgency score that combines risk with renewal proximity, the renewal window, days until renewal, auto-renew status, ARR, ARR at risk, and a recommended next action.

ARR at Risk is the account's annual recurring revenue weighted by its churn probability — so a two-hundred-thousand-dollar account with a forty percent churn risk shows eighty thousand dollars at risk. This is how you quantify the exposure in dollar terms.

You can sort by any column, filter by risk tier or renewal window, and search for specific accounts. The summary badges at the top give you a quick read — how many accounts are High, Medium, and Low risk, how many are active versus archived, and the total ARR at risk across the portfolio.

### Account Detail Drawer (click on an account row)

Click any account row and a detail drawer slides out from the right. This gives you the full picture for that specific account.

You'll see the risk score, ARR at risk, renewal timeline, and the top risk drivers — the specific factors pushing this account toward churn, like declining login frequency or a low NPS score.

Below that is the retention playbook — a set of recommended actions ranked by priority. For each action, you can draft an outreach email directly from the platform. Choose a tone — friendly, direct, or executive — enter the contact's email, and PickPulse generates a personalized email using the account's risk profile and recommended intervention. You can also add a calendar reminder for the renewal date and log playbook actions.

### Export (click Export CSV)

You can export the full scored dataset as a CSV — with all prediction fields included — for import into Salesforce, HubSpot, or your BI platform.

---

## Overview — Executive Dashboard (navigate to Overview)

The Overview page is designed for leadership. It gives you the portfolio-level view at a glance.

Four hero KPI cards across the top: total ARR at Risk, Accounts Requiring Action — that's the count of high-risk accounts also renewing soon — Potential ARR Protected at your assumed save rate, and High-Risk Renewals coming up in the next ninety days.

Below that is the ARR at Risk by Tier visualization — a stacked bar showing how exposure distributes across High, Medium, and Low risk tiers, both in dollar terms and account counts.

Then the Top Ten Accounts to Save Now — the highest-priority accounts ranked by ARR at risk. Click any row to open the same detail drawer with risk drivers and playbook actions.

The Revenue Recovery Simulation lets you adjust the assumed save rate — slide it from twenty to sixty percent — and see how the projected recoverable ARR changes in real time. This is useful for modeling different intervention scenarios for your board or your CS leadership.

At the bottom, Portfolio Risk Drivers shows which features are most influential across the entire portfolio — not just one account, but the aggregate patterns driving churn across all your customers.

### Executive Brief (click Generate or View Executive Brief)

From the Overview page, you can generate an Executive Brief — a formatted summary of the portfolio risk position designed to be shared with leadership.

Click Generate Executive Brief, and the platform produces an HTML-formatted report with your Portfolio Summary — ARR at Risk, Projected Recoverable, Urgent Accounts, and Renewals in ninety days — plus Risk Distribution by tier, the Top Accounts Requiring Attention table, and Top Risk Drivers.

From the modal, you can click Send Executive Brief to open your default email client with the summary pre-populated, or Copy Summary to paste it into Slack, a document, or wherever your team communicates. The brief is also available from the Accounts page, and it persists as you navigate between pages — you don't lose it.

---

## Reports (navigate to Reports)

The Reports page gives you two export options.

The PDF Churn Risk Report is a board-ready document with model discrimination metrics, lift analysis, calibration curves, risk tier breakdown, and projected business impact. Download it and hand it to your CRO or present it in a QBR.

The Scored Predictions CSV is the complete dataset with every prediction field — churn probabilities, urgency rankings, renewal windows, ARR at risk, recommended actions. Import it directly into your CRM or BI platform.

---

## API (navigate to API)

For teams that want to integrate PickPulse into their existing workflows, we expose a full REST API. The API page documents every endpoint with curl examples — data loading, training, prediction, evaluation, account explanations, and notification settings.

You can also configure Executive Brief recipients here — add email addresses and every generated brief will pre-populate with those recipients.

---

## Closing

That's PickPulse Intelligence. The platform takes your account data, builds a calibrated churn model, scores every customer in your portfolio, and gives your team the tools to act — from the executive dashboard down to individual account playbooks with AI-generated outreach.

The goal is simple: identify which customers are most likely to leave, quantify the revenue at stake, and give your CS team a prioritized action plan before it's too late.

If you'd like to see this on your own data, we can run a pilot in under a week.
