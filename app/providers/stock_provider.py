"""Backward-compatible shim — real implementation lives in app.plugins.stock.provider."""

from app.plugins.stock.provider import StockProvider  # noqa: F401
from app.providers import registry

# Auto-register (so legacy code that imports this module still works)
if StockProvider.PROVIDER_KEY not in registry:
    registry.register(StockProvider)
