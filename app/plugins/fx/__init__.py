"""Foreign Exchange plugin — auto-configured from config.yaml + provider."""

from app.plugins.defaults import create_plugin
from app.plugins.fx.provider import FxProvider

plugin = create_plugin(__file__, FxProvider)
