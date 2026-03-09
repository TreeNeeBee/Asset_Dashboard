"""MVVM plugin framework — public API.

Import anything from ``app.plugins`` directly::

    from app.plugins import BasePlugin, PluginConfig, plugin_manager, create_plugin

Implementation is split across sub-modules for clarity:

* :mod:`.config`   — :class:`PluginConfig` (YAML reader/writer)
* :mod:`.base`     — abstract base classes + data types
* :mod:`.defaults` — config-driven default implementations + :func:`create_plugin`
* :mod:`.manager`  — :class:`PluginManager` singleton
"""

from .base import (
    API_BASE_URL,
    INFINITY_DATASOURCE,
    BasePlugin,
    BasePluginModel,
    BasePluginView,
    GrafanaPanelDef,
    IntervalConfig,
)
from .config import PluginConfig
from .defaults import (
    DeclarativePlugin,
    DefaultPluginModel,
    DefaultPluginView,
    create_plugin,
)
from .manager import PluginManager

# Module-level singleton
plugin_manager = PluginManager()

__all__ = [
    "API_BASE_URL",
    "INFINITY_DATASOURCE",
    "BasePlugin",
    "BasePluginModel",
    "BasePluginView",
    "DeclarativePlugin",
    "DefaultPluginModel",
    "DefaultPluginView",
    "GrafanaPanelDef",
    "IntervalConfig",
    "PluginConfig",
    "PluginManager",
    "create_plugin",
    "plugin_manager",
]
