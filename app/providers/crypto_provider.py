"""Backward-compatible shim — real implementation lives in app.plugins.crypto.provider."""

from app.plugins.crypto.provider import CryptoProvider  # noqa: F401
from app.providers import registry

# Auto-register (so legacy code that imports this module still works)
if CryptoProvider.PROVIDER_KEY not in registry:
    registry.register(CryptoProvider)



# Auto-register on import
registry.register(CryptoProvider)
