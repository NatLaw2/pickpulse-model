"""
HubSpot CRM alias pack.

Covers HubSpot Company, Deal, and Contact property exports, including
both standard snake_case names and HubSpot's internal hs_* prefixed fields.

IMPORTANT product rules:
- lifecyclestage is NOT a direct churn label.  A stage of "customer" means
  retained; "churned" or "inactive_customer" may mean churned — but the
  user must confirm before we use this as the label column.
- dealstage (e.g. "closedlost" / "closedwon") is ambiguous and requires
  confirmation.
- Direct custom properties like churn_flag or is_churned are unambiguous
  and do not require confirmation.
"""
from ._base import AliasEntry, CrmPack

HUBSPOT_PACK = CrmPack(
    name="hubspot",
    display_name="HubSpot",
    entries=[
        # ---------------------------------------------------------------
        # account_id
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="account_id",
            aliases=[
                "hs_object_id", "companyId", "company_id",
                "hs_company_id", "record_id",
            ],
        ),

        # ---------------------------------------------------------------
        # snapshot_date
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="snapshot_date",
            aliases=[
                "createdate", "hs_lastmodifieddate",
                "lastmodifieddate", "closedate",
            ],
        ),

        # ---------------------------------------------------------------
        # arr
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="arr",
            aliases=[
                "hubspot_arr", "annual_recurring_revenue",
                "contract_value", "annualrevenue",
            ],
        ),

        # ---------------------------------------------------------------
        # mrr
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="mrr",
            aliases=["hubspot_mrr", "monthly_recurring_revenue", "amount"],
        ),

        # ---------------------------------------------------------------
        # renewal_date
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="renewal_date",
            aliases=[
                "renewal_date", "contract_end_date",
                "next_renewal_date", "cancellation_date",
                "hs_closed_date",
            ],
        ),

        # ---------------------------------------------------------------
        # plan_type
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="plan_type",
            aliases=["hubspot_tier", "subscription_plan", "hs_product_name"],
        ),

        # ---------------------------------------------------------------
        # churned — direct, unambiguous custom properties
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="churned",
            aliases=[
                "churn_flag", "is_churned", "churned",
                "canceled", "cancelled", "lost_customer",
                "hs_is_churned",
            ],
            notes="Direct HubSpot custom churn properties — unambiguous.",
        ),

        # ---------------------------------------------------------------
        # churned — ambiguous lifecycle / deal stage fields
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="churned",
            aliases=[
                "dealstage", "deal_stage",
                "lifecyclestage", "lifecycle_stage",
                "hs_lead_status", "customer_status",
                "subscription_status",
            ],
            requires_confirmation=True,
            notes=(
                "HubSpot lifecycle and deal stage fields are NOT direct churn "
                "labels. 'lifecyclestage=customer' means retained. "
                "'dealstage=closedlost' may indicate churn but requires "
                "business-context confirmation. Value normalisation will convert "
                "closedlost→1 and closedwon→0 after the user confirms."
            ),
        ),

        # ---------------------------------------------------------------
        # company_name
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="company_name",
            aliases=["name", "company", "hs_company_name"],
        ),

        # ---------------------------------------------------------------
        # csm_owner
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="csm_owner",
            aliases=["hubspot_owner_id", "hs_owner", "assigned_owner"],
        ),
    ],

    churn_positive_values=[
        "closedlost", "closed_lost", "lost", "churned",
        "inactive_customer", "inactive",
        "cancelled", "canceled",
    ],
    churn_negative_values=[
        "closedwon", "closed_won", "won", "active",
        "customer", "evangelist", "opportunity",
    ],
)
