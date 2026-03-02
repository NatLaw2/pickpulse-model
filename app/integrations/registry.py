"""Connector registry — single place to register and look up connectors."""
from __future__ import annotations

import logging
from typing import Dict, Optional, Type

from app.integrations.base import BaseConnector
from app.integrations.models import ConnectorConfig, ConnectorInfo, ConnectorStatus

logger = logging.getLogger(__name__)

_CONNECTOR_CLASSES: Dict[str, Type[BaseConnector]] = {}

# Legacy in-memory configs for backward compatibility during transition
_ACTIVE_CONFIGS: Dict[str, ConnectorConfig] = {}


def register_connector(cls: Type[BaseConnector]) -> Type[BaseConnector]:
    """Decorator to register a connector class."""
    instance = cls(ConnectorConfig(name=cls.name.fget(None), display_name=cls.display_name.fget(None)))  # type: ignore[arg-type]
    _CONNECTOR_CLASSES[instance.name] = cls
    return cls


def register_class(name: str, display_name: str, cls: Type[BaseConnector]) -> None:
    """Imperatively register a connector class."""
    _CONNECTOR_CLASSES[name] = cls


def available_connectors() -> Dict[str, Type[BaseConnector]]:
    return dict(_CONNECTOR_CLASSES)


def configure(name: str, config: ConnectorConfig) -> None:
    """Store a connector configuration (legacy in-memory)."""
    _ACTIVE_CONFIGS[name] = config


def get_config(name: str) -> Optional[ConnectorConfig]:
    return _ACTIVE_CONFIGS.get(name)


def get_connector(name: str) -> Optional[BaseConnector]:
    """Instantiate a configured connector from legacy in-memory config, or None."""
    cls = _CONNECTOR_CLASSES.get(name)
    cfg = _ACTIVE_CONFIGS.get(name)
    if not cls or not cfg:
        return None
    return cls(cfg)


def get_connector_for_integration(integration_id: str) -> Optional[BaseConnector]:
    """Instantiate a connector using DB-stored integration + decrypted token.

    This is the new preferred method — reads encrypted tokens from DB.
    """
    from app.integrations.service import get_integration, get_decrypted_token

    integration = get_integration(integration_id=integration_id)
    if not integration:
        return None

    provider = integration["provider"]
    cls = _CONNECTOR_CLASSES.get(provider)
    if not cls:
        logger.warning("No connector class registered for provider: %s", provider)
        return None

    # Get decrypted token
    token = get_decrypted_token(integration_id)
    if not token:
        logger.warning("No token found for integration: %s", integration_id)
        return None

    # Build config with token
    config = ConnectorConfig(
        name=provider,
        display_name=integration["display_name"],
        api_key=token if integration["auth_method"] == "api_key" else None,
        extra={"access_token": token} if integration["auth_method"] == "oauth" else {},
        enabled=True,
    )

    return cls(config)


def list_connectors() -> list[ConnectorInfo]:
    """List all registered connectors with their status (legacy)."""
    results = []
    for name, cls in _CONNECTOR_CLASSES.items():
        cfg = _ACTIVE_CONFIGS.get(name)
        dummy = cls(ConnectorConfig(name=name, display_name=""))
        info = ConnectorInfo(
            name=name,
            display_name=dummy.display_name,
            status=ConnectorStatus.configured if cfg and cfg.enabled else ConnectorStatus.not_configured,
            enabled=cfg.enabled if cfg else False,
        )
        results.append(info)
    return results
