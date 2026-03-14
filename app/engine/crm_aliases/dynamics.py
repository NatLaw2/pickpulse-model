"""
Microsoft Dynamics 365 CRM alias pack.

Dynamics uses camelCase entity attribute names.  The stateCode and
statusCode fields carry numeric values whose meaning depends on the
entity type and org configuration — they must NEVER be silently mapped
to churned.

IMPORTANT product rules:
- statecode / statuscode hold raw numeric codes (0 = Active, 1 = Inactive
  for Account, but this varies by entity).  Their textual exported labels
  may be valid churn signals, but the raw codes must require confirmation.
- annualrevenue is a native Dynamics field (maps to arr).
- accountid (all lowercase) is the standard GUID field.
"""
from ._base import AliasEntry, CrmPack

DYNAMICS_PACK = CrmPack(
    name="dynamics",
    display_name="Microsoft Dynamics 365",
    entries=[
        # ---------------------------------------------------------------
        # account_id
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="account_id",
            aliases=[
                "accountid", "accountnumber",
                "customerid", "parentaccountid",
            ],
        ),

        # ---------------------------------------------------------------
        # snapshot_date
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="snapshot_date",
            aliases=[
                "createdon", "modifiedon",
                "overriddencreatedon", "closedon",
            ],
        ),

        # ---------------------------------------------------------------
        # arr
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="arr",
            aliases=[
                "annualrevenue", "contractvalue",
                "estimatedvalue", "totalamount",
            ],
        ),

        # ---------------------------------------------------------------
        # mrr
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="mrr",
            aliases=["monthlyrevenue", "recurringmonthlyrevenue"],
        ),

        # ---------------------------------------------------------------
        # renewal_date
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="renewal_date",
            aliases=[
                "renewaldate", "contractenddate",
                "expirationdate", "termenddate",
            ],
        ),

        # ---------------------------------------------------------------
        # plan_type
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="plan_type",
            aliases=["plantype", "subscriptiontier", "servicetier"],
        ),

        # ---------------------------------------------------------------
        # churned — direct custom fields, unambiguous
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="churned",
            aliases=[
                "churnflag", "ischurned", "lostcustomer",
                "canceled", "cancelled",
            ],
            notes="Direct Dynamics custom churn fields — unambiguous.",
        ),

        # ---------------------------------------------------------------
        # churned — ambiguous state/status code fields
        # Raw numeric codes MUST require confirmation.
        # Textual label exports (e.g. "Active" / "Inactive") are still
        # ambiguous because meaning varies by entity type and org config.
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="churned",
            aliases=[
                "statecode", "statuscode",
                "accountstatus", "subscriptionstatus",
            ],
            requires_confirmation=True,
            notes=(
                "Dynamics statecode/statuscode values are numeric codes whose "
                "meaning varies by entity and org configuration. "
                "0=Active / 1=Inactive is common for Account but NOT guaranteed. "
                "Always require user confirmation before using as churn label."
            ),
        ),

        # ---------------------------------------------------------------
        # company_name
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="company_name",
            aliases=["name", "fullname", "accountname"],
        ),

        # ---------------------------------------------------------------
        # csm_owner
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="csm_owner",
            aliases=["ownerid", "ownerpassword", "primarycontactid"],
        ),
    ],

    churn_positive_values=[
        "inactive", "canceled", "cancelled", "lost",
        "terminated", "deactivated",
        "1",  # statecode=1 often means Inactive for Account — only after confirmation
    ],
    churn_negative_values=[
        "active", "current", "renewed",
        "0",  # statecode=0 often means Active — only after confirmation
    ],
)
