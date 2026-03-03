"""Beacon connector plugin architecture."""

from src.connectors.base import BaseConnector, ConnectorRegistry, registry

__all__ = ["BaseConnector", "ConnectorRegistry", "registry"]
