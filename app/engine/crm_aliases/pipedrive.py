"""
Pipedrive CRM alias pack.

Pipedrive organises data around Organisations, Persons, and Deals.
Deal status (won / lost / open) is the most common churn-like signal,
but it is intrinsically ambiguous — a "lost" deal may not mean the
account has churned if the company uses Pipedrive for new-business only.

IMPORTANT product rules:
- status / deal_status / stage_name all require user confirmation before
  being used as the churn label.
- lost_reason is a supporting text field, NOT a binary churn indicator;
  it requires confirmation.
- org_id / organization_id are the canonical account identifiers.
- value / annual_value map to arr.
"""
from ._base import AliasEntry, CrmPack

PIPEDRIVE_PACK = CrmPack(
    name="pipedrive",
    display_name="Pipedrive",
    entries=[
        # ---------------------------------------------------------------
        # account_id
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="account_id",
            aliases=[
                "org_id", "organization_id",
                "person_id", "company_id",
            ],
        ),

        # ---------------------------------------------------------------
        # snapshot_date
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="snapshot_date",
            aliases=[
                "add_time", "update_time",
                "won_time", "lost_time", "close_time",
            ],
        ),

        # ---------------------------------------------------------------
        # arr
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="arr",
            aliases=[
                "annual_value", "contract_value",
                "yearly_value",
            ],
        ),

        # ---------------------------------------------------------------
        # mrr
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="mrr",
            aliases=["monthly_value", "recurring_value"],
        ),

        # ---------------------------------------------------------------
        # renewal_date
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="renewal_date",
            aliases=[
                "expected_close_date", "contract_end",
                "subscription_end",
            ],
        ),

        # ---------------------------------------------------------------
        # plan_type
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="plan_type",
            aliases=["product_tier", "pipeline_id"],
        ),

        # ---------------------------------------------------------------
        # churned — direct flags, unambiguous
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="churned",
            aliases=["is_lost", "churned", "canceled", "cancelled"],
            notes="Direct Pipedrive churn flags — unambiguous.",
        ),

        # ---------------------------------------------------------------
        # churned — ambiguous deal stage / status fields
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="churned",
            aliases=[
                "status", "deal_status",
                "stage_name", "stage_id",
                "lost_reason",
            ],
            requires_confirmation=True,
            notes=(
                "Pipedrive 'status' is one of: open, won, lost. "
                "'lost' often (but not always) means customer churned — depends "
                "on whether Pipedrive is used for renewals or new-business only. "
                "'stage_id' and 'stage_name' are pipeline stages, NOT churn labels. "
                "'lost_reason' is a text description that should NOT be used as the "
                "binary label without value normalisation and user confirmation."
            ),
        ),

        # ---------------------------------------------------------------
        # company_name
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="company_name",
            aliases=["org_name", "organization_name", "title"],
        ),
    ],

    churn_positive_values=[
        "lost", "cancelled", "canceled", "churned",
    ],
    churn_negative_values=[
        "won", "open", "active",
    ],
)
