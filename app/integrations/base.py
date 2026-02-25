"""Abstract base class for integration connectors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from app.integrations.models import Account, AccountSignal, ConnectorConfig


class BaseConnector(ABC):
    """Interface that all connectors must implement."""

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        """Return True if the API key / credentials are valid."""
        ...

    @abstractmethod
    def pull_accounts(self) -> List[Account]:
        """Pull all accounts from the external system."""
        ...

    @abstractmethod
    def pull_signals(self, external_ids: List[str]) -> List[AccountSignal]:
        """Pull daily usage / engagement signals for given accounts."""
        ...
