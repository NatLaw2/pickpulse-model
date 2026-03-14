"""
Salesforce CRM alias pack.

Covers standard Salesforce object exports (Account, Opportunity, Contract)
including both native API field names (PascalCase) and common custom fields
(__c suffix).

IMPORTANT product rules:
- StageName, IsClosed, and IsWon are AMBIGUOUS — they never auto-map to
  churned.  They appear here with requires_confirmation=True so the UI shows
  them as suggestions that require explicit user confirmation.
- IsClosed alone is NOT churn.  IsWon alone is NOT churn.
- Churned__c / Is_Churned__c / Cancelled__c ARE direct churn flags and do
  NOT require confirmation.
"""
from ._base import AliasEntry, CrmPack

SALESFORCE_PACK = CrmPack(
    name="salesforce",
    display_name="Salesforce",
    entries=[
        # ---------------------------------------------------------------
        # account_id
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="account_id",
            aliases=[
                "AccountId", "Account.Id", "AccountNumber",
                "Account_Number__c",
            ],
        ),

        # ---------------------------------------------------------------
        # snapshot_date
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="snapshot_date",
            aliases=[
                "LastModifiedDate", "CreatedDate",
                "SystemModstamp", "CloseDate",
            ],
        ),

        # ---------------------------------------------------------------
        # arr
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="arr",
            aliases=[
                "ARR__c", "Annual_Recurring_Revenue__c",
                "ACV__c", "Annual_Contract_Value__c",
                "Contract_Value__c", "AnnualRevenue",
            ],
        ),

        # ---------------------------------------------------------------
        # mrr
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="mrr",
            aliases=["MRR__c", "Monthly_Recurring_Revenue__c"],
        ),

        # ---------------------------------------------------------------
        # renewal_date
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="renewal_date",
            aliases=[
                "Renewal_Date__c", "Contract_End_Date__c",
                "Subscription_End_Date__c", "End_Date__c",
                "ContractEndDate",
            ],
        ),

        # ---------------------------------------------------------------
        # plan_type
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="plan_type",
            aliases=["Plan__c", "Tier__c", "Package__c", "Edition__c"],
        ),

        # ---------------------------------------------------------------
        # churned — direct, unambiguous custom flags
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="churned",
            aliases=[
                "Churned__c", "Is_Churned__c",
                "Lost_Customer__c",
                "Cancelled__c", "Canceled__c",
                "IsCanceled", "IsCancelled",
            ],
            notes="Direct Salesforce custom churn flags — clearly indicate churn.",
        ),

        # ---------------------------------------------------------------
        # churned — ambiguous Salesforce stage / status fields
        # These MUST require user confirmation before being used as the
        # churn label.
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="churned",
            aliases=["StageName", "IsClosed", "IsWon", "Status__c",
                     "Customer_Status__c", "Account_Status__c"],
            requires_confirmation=True,
            notes=(
                "StageName, IsClosed, and IsWon are Opportunity stage fields. "
                "IsClosed=True includes both Closed Won and Closed Lost. "
                "IsWon=True means won, NOT churned. "
                "Only confirm this mapping if values clearly indicate churn/retention."
            ),
        ),

        # ---------------------------------------------------------------
        # company_name
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="company_name",
            aliases=["AccountName", "Account_Name__c", "Name"],
        ),

        # ---------------------------------------------------------------
        # csm_owner
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="csm_owner",
            aliases=["OwnerId", "Owner.Name", "Customer_Success_Manager__c"],
        ),
    ],

    churn_positive_values=[
        "Closed Lost", "closedlost", "closed_lost",
        "Lost", "Cancelled", "Canceled",
        "Churned", "Inactive",
    ],
    churn_negative_values=[
        "Closed Won", "closedwon", "closed_won",
        "Won", "Active Renewal", "Renewed", "Active",
    ],
)
