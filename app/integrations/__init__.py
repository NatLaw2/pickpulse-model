"""Integration connectors for external systems."""
from app.integrations.registry import register_class
from app.integrations.hubspot import HubSpotConnector
from app.integrations.salesforce import SalesforceConnector
from app.integrations.stripe import StripeConnector
from app.integrations.csv_connector import CSVConnector

# Register built-in connectors
register_class("hubspot", "HubSpot CRM", HubSpotConnector)
register_class("salesforce", "Salesforce CRM", SalesforceConnector)
register_class("stripe", "Stripe Billing", StripeConnector)
register_class("csv", "CSV Import", CSVConnector)
