"""Base connector class and registry for Beacon plugins."""

from __future__ import annotations

import importlib
import pkgutil
from abc import ABC, abstractmethod
from typing import Any

from src.models import ActionItem, Event, Source, SourceType


class BaseConnector(ABC):
    """Abstract base class for all Beacon source connectors.

    Subclass this to implement a new connector. The connector_type class
    attribute must be set to the corresponding SourceType value.
    """

    connector_type: SourceType

    def __init__(self, source: Source) -> None:
        self.source = source

    @abstractmethod
    def validate_config(self) -> bool:
        """Validate that the connector configuration is complete and correct.

        Returns True if config is valid, False otherwise.
        """

    @abstractmethod
    def sync(self) -> tuple[list[Event], list[ActionItem]]:
        """Pull the latest data from the source.

        Returns a tuple of (events, action_items).
        Raises ConnectorError on unrecoverable failure.
        """

    def test_connection(self) -> bool:
        """Test that the connector can reach its source.

        Default implementation calls validate_config(). Override for
        real connectivity checks.
        """
        return self.validate_config()

    def get_config(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from the source config dict."""
        return self.source.config.get(key, default)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(source={self.source.name!r})"


class ConnectorError(Exception):
    """Raised when a connector encounters an unrecoverable error."""


class ConnectorRegistry:
    """Registry that maps SourceType -> BaseConnector subclass.

    Usage:
        registry.register(MyConnector)
        cls = registry.get(SourceType.GITHUB)
        connector = cls(source)
    """

    def __init__(self) -> None:
        self._registry: dict[SourceType, type[BaseConnector]] = {}

    def register(self, cls: type[BaseConnector]) -> type[BaseConnector]:
        """Register a connector class. Can be used as a decorator.

        Raises ValueError if a connector for that SourceType is already registered.
        """
        if not hasattr(cls, "connector_type"):
            raise ValueError(f"{cls.__name__} must define a 'connector_type' class attribute")
        source_type = cls.connector_type
        if source_type in self._registry:
            raise ValueError(
                f"A connector for {source_type.value!r} is already registered: "
                f"{self._registry[source_type].__name__}"
            )
        self._registry[source_type] = cls
        return cls

    def get(self, source_type: SourceType) -> type[BaseConnector] | None:
        """Return the connector class for a SourceType, or None if not registered."""
        return self._registry.get(source_type)

    def available(self) -> list[SourceType]:
        """Return a list of all registered SourceTypes."""
        return list(self._registry.keys())

    def all(self) -> dict[SourceType, type[BaseConnector]]:
        """Return a copy of the full registry."""
        return dict(self._registry)

    def load_from_package(self, package_name: str) -> None:
        """Auto-discover and import all modules in a package to trigger @register decorators.

        Args:
            package_name: dotted module path (e.g. 'src.connectors.plugins')
        """
        try:
            package = importlib.import_module(package_name)
        except ModuleNotFoundError:
            return
        package_path = getattr(package, "__path__", [])
        for _finder, module_name, _is_pkg in pkgutil.iter_modules(package_path):
            importlib.import_module(f"{package_name}.{module_name}")

    def unregister(self, source_type: SourceType) -> None:
        """Remove a connector from the registry (mainly for testing)."""
        self._registry.pop(source_type, None)

    def clear(self) -> None:
        """Clear all registrations (mainly for testing)."""
        self._registry.clear()

    def __len__(self) -> int:
        return len(self._registry)

    def __repr__(self) -> str:
        types = [st.value for st in self._registry]
        return f"ConnectorRegistry(registered={types!r})"


# Module-level singleton registry
registry = ConnectorRegistry()
