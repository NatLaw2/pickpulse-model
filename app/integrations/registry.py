"""Connector registry — single place to register and look up connectors."""
from __future__ import annotations

from typing import Dict, Optional, Type

from app.integrations.base import BaseConnector
from app.integrations.models import ConnectorConfig, ConnectorInfo, ConnectorStatus


_CONNECTOR_CLASSES: Dict[str, Type[BaseConnector]] = {}
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
    """Store a connector configuration."""
    _ACTIVE_CONFIGS[name] = config


def get_config(name: str) -> Optional[ConnectorConfig]:
    return _ACTIVE_CONFIGS.get(name)


def get_connector(name: str) -> Optional[BaseConnector]:
    """Instantiate a configured connector, or None."""
    cls = _CONNECTOR_CLASSES.get(name)
    cfg = _ACTIVE_CONFIGS.get(name)
    if not cls or not cfg:
        return None
    return cls(cfg)


def list_connectors() -> list[ConnectorInfo]:
    """List all registered connectors with their status."""
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
