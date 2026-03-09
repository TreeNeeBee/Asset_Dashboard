"""Backward-compatible shim — real implementation lives in app.plugins.fx.provider."""

from app.plugins.fx.provider import FxProvider  # noqa: F401
from app.providers import registry

# Auto-register (so legacy code that imports this module still works)
if FxProvider.PROVIDER_KEY not in registry:
    registry.register(FxProvider)

