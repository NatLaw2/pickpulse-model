"""Integration connectors for external systems."""
from app.integrations.registry import register_class
from app.integrations.hubspot import HubSpotConnector
from app.integrations.stripe import StripeConnector

# Register built-in connectors
register_class("hubspot", "HubSpot CRM", HubSpotConnector)
register_class("stripe", "Stripe Billing", StripeConnector)
