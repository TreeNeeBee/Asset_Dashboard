"""US Stock plugin — auto-configured from config.yaml + provider."""

from app.plugins.defaults import create_plugin
from app.plugins.stock.provider import StockProvider

plugin = create_plugin(__file__, StockProvider)
