"""
Global alias pack — vendor-agnostic synonyms for all canonical fields.

This is the primary alias library.  It is a superset of the original
hardcoded ALIAS_MAP, extended with every common spelling and naming
convention found in generic CRM/data-warehouse exports.

Ordering within each alias list matters: the suggestion engine claims the
first matching alias, so the most common / least ambiguous names appear first.
"""
from ._base import AliasEntry, CrmPack

GLOBAL_PACK = CrmPack(
    name="global",
    display_name="Global",
    entries=[
        # ---------------------------------------------------------------
        # account_id
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="account_id",
            aliases=[
                "account_id", "accountid",
                "customer_id", "customerid",
                "client_id", "clientid",
                "company_id", "companyid",
                "org_id", "orgid",
                "organization_id", "organisationid", "organization_id",
                "crm_account_id", "crmaccountid",
                "tenant_id", "tenantid",
                "account_number", "accountnumber",
                "cust_id", "custid",
                "subscriber_id", "subscriberid",
                "entity_id", "entityid",
                "record_id", "recordid",
                "uuid", "uid",
                # "id" last — too generic; only wins if nothing else matches
                "id",
            ],
        ),

        # ---------------------------------------------------------------
        # snapshot_date
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="snapshot_date",
            aliases=[
                "snapshot_date", "snapshotdate",
                "record_date", "recorddate",
                "as_of_date", "asofdate",
                "report_date", "reportdate",
                "export_date", "exportdate",
                "period_date", "perioddate",
                "cohort_date", "cohortdate",
                "eval_date", "evaldate",
                "observation_date",
                "data_date", "datadate",
                "extract_date", "extractdate",
                "run_date", "rundate",
                "month_date", "monthdate",
                "created_date", "createddate",
                "updated_date", "updateddate",
                "modified_date", "modifieddate",
                # Generic "date" / "month" / "period" — last resort
                "period", "date", "month",
            ],
        ),

        # ---------------------------------------------------------------
        # churned — non-ambiguous direct flags only.
        # Ambiguous CRM fields (StageName, dealstage, status, etc.) are
        # added in their respective CRM packs with requires_confirmation=True.
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="churned",
            aliases=[
                "churned", "churn",
                "is_churned", "ischurned",
                "churn_flag", "churnflag", "churned_flag",
                "did_churn", "didchurn",
                "canceled", "cancelled",
                "is_canceled", "iscanceled",
                "is_cancelled", "iscancelled",
                "cancellation_flag", "canceled_flag", "cancelled_flag",
                "attrited", "lost",
                "terminated", "contract_ended",
                "deactivated",
                "non_renewed", "nonrenewed",
                "closed_lost", "closedlost",
                "inactive",
            ],
        ),

        # Global status-like fields that are ambiguous for churn —
        # suggest with confirmation required.
        AliasEntry(
            canonical="churned",
            aliases=[
                "status", "account_status", "customer_status",
                "subscription_status", "lifecycle_status", "state",
            ],
            requires_confirmation=True,
            notes=(
                "Generic status fields are ambiguous. Map to 'churned' only if "
                "values clearly represent a churn outcome (e.g. active/inactive, "
                "won/lost). Value normalization will convert text values to 0/1."
            ),
        ),

        # ---------------------------------------------------------------
        # arr
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="arr",
            aliases=[
                "arr", "arr_usd", "arrvalue",
                "annual_recurring_revenue",
                "annual_revenue", "annualrevenue",
                "annual_contract_value",
                "acv",
                "contract_value", "contractvalue",
                "total_arr", "totalarr",
                "yearly_revenue", "yearlyrevenue",
            ],
        ),

        # ---------------------------------------------------------------
        # mrr
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="mrr",
            aliases=[
                "mrr", "mrr_usd",
                "monthly_recurring_revenue",
                "monthly_revenue", "monthlyrevenue",
                "monthly_contract_value",
                "monthly_value", "monthlyvalue",
                "recurring_monthly_revenue",
            ],
        ),

        # ---------------------------------------------------------------
        # renewal_date
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="renewal_date",
            aliases=[
                "renewal_date", "renewaldate",
                "next_renewal_date", "nextrenewaldate",
                "contract_end", "contractend",
                "contract_end_date", "contractenddate",
                "expiry_date", "expirydate",
                "expiration_date", "expirationdate",
                "term_end_date", "termenddate",
                "next_renewal", "nextrenewal",
                "subscription_end", "subscriptionend",
                "subscription_end_date",
                "end_date", "enddate",
                "contract_expiry",
            ],
        ),

        # ---------------------------------------------------------------
        # days_until_renewal
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="days_until_renewal",
            aliases=[
                "days_until_renewal", "daysuntilrenewal",
                "days_to_renewal", "daystorenewal",
                "renewal_days", "renewaldays",
                "days_remaining", "daysremaining",
                "days_to_contract_end",
                "days_to_expiry",
                "contract_days_remaining",
            ],
        ),

        # ---------------------------------------------------------------
        # contract_start_date
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="contract_start_date",
            aliases=[
                "contract_start_date", "contractstartdate",
                "start_date", "startdate",
                "contract_start", "contractstart",
                "account_start_date",
                "created_date", "createddate",
                "inception_date",
                "onboard_date", "onboarddate",
                "signup_date", "signupdate",
            ],
        ),

        # ---------------------------------------------------------------
        # seats_purchased
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="seats_purchased",
            aliases=[
                "seats_purchased", "seatspurchased",
                "seats", "licenses", "license_count", "licensecount",
                "total_seats", "totalseats",
                "contracted_seats",
                "users_purchased",
            ],
        ),

        # ---------------------------------------------------------------
        # seats_active_30d
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="seats_active_30d",
            aliases=[
                "seats_active_30d", "active_seats_30d",
                "active_users_30d",
                "mau", "mau_30",
                "active_seats", "active_users",
                "users_active_30d",
                "monthly_active_users",
                "active_licenses_30d",
            ],
        ),

        # ---------------------------------------------------------------
        # login_days_30d
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="login_days_30d",
            aliases=[
                "login_days_30d", "logindays30d",
                "logins_last_30", "logins_30d",
                "active_days_30", "activedays30",
                "login_count_30d", "logincount30d",
                "sessions_30d", "sessions30d",
                "usage_days_30d", "usagedays30d",
                "active_usage_days_30d",
                "dau_30",
                # Looser aliases — common in analytics exports
                "monthly_logins", "monthlylogins",
                "logins", "login_count", "sessions",
            ],
        ),

        # ---------------------------------------------------------------
        # support_tickets_30d
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="support_tickets_30d",
            aliases=[
                "support_tickets_30d", "supporttickets30d",
                "tickets_30d", "tickets30d",
                "ticket_count_30d",
                "support_cases_30d",
                "cases_30d", "cases30d",
                "helpdesk_tickets_30d",
                "support_requests_30d",
                "incidents_30d",
                # Looser aliases
                "support_tickets", "ticket_count", "tickets",
                "support_cases", "cases",
                "support_incidents",
            ],
        ),

        # ---------------------------------------------------------------
        # nps_score
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="nps_score",
            aliases=[
                "nps_score", "npsscore",
                "nps",
                "net_promoter_score",
                "satisfaction", "satisfaction_score",
                "csat", "csat_score",
            ],
        ),

        # ---------------------------------------------------------------
        # plan_type
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="plan_type",
            aliases=[
                "plan_type", "plantype",
                "plan", "tier",
                "subscription", "subscription_plan",
                "plan_name", "planname",
                "product", "product_tier",
                "subscription_tier",
                "package",
                "edition", "sku",
                "plan_tier",
            ],
        ),

        # ---------------------------------------------------------------
        # auto_renew_flag
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="auto_renew_flag",
            aliases=[
                "auto_renew_flag", "autorenewflag",
                "auto_renew", "autorenew",
                "auto_renewal", "autorenewal",
                "auto_renew_enabled",
                "is_auto_renew",
            ],
        ),

        # ---------------------------------------------------------------
        # company_name (display only)
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="company_name",
            aliases=[
                "company_name", "companyname",
                "account_name", "accountname",
                "customer_name", "customername",
                "client_name", "clientname",
                "organization", "org_name", "orgname",
            ],
        ),

        # ---------------------------------------------------------------
        # csm_owner (display only)
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="csm_owner",
            aliases=[
                "csm_owner", "csmowner",
                "csm", "account_owner", "accountowner",
                "customer_success_manager",
                "csm_name", "assigned_csm",
            ],
        ),

        # ---------------------------------------------------------------
        # industry (display only)
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="industry",
            aliases=[
                "industry", "vertical", "sector", "market",
                "industry_name", "business_type",
            ],
        ),

        # ---------------------------------------------------------------
        # region (display only)
        # ---------------------------------------------------------------
        AliasEntry(
            canonical="region",
            aliases=[
                "region", "geography", "geo", "country",
                "territory", "market_region",
            ],
        ),
    ],

    # -------------------------------------------------------------------
    # Global churn value vocabulary
    # -------------------------------------------------------------------
    churn_positive_values=[
        "churned", "canceled", "cancelled", "terminated", "lost",
        "closed lost", "closed_lost", "closedlost",
        "inactive", "deactivated",
        "non-renewed", "non renewed", "non_renewed", "nonrenewed",
        "attrited",
    ],
    churn_negative_values=[
        "active", "retained", "renewed", "open",
        "current customer", "current_customer",
        "won", "closed won", "closed_won", "closedwon",
    ],
)
