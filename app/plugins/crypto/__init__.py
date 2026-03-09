"""Cryptocurrency plugin — auto-configured from config.yaml + provider."""

from app.plugins.defaults import create_plugin
from app.plugins.crypto.provider import CryptoProvider

plugin = create_plugin(__file__, CryptoProvider)
