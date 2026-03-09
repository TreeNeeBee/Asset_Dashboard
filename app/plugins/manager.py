"""Plugin discovery and lifecycle management."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Optional

from loguru import logger

from app.providers import registry as provider_registry

from .base import BasePlugin


class PluginManager:
    """Discovers, loads and exposes all registered plugins.

    A singleton — import via ``from app.plugins import plugin_manager``.
    """

    _instance: Optional["PluginManager"] = None
    _plugins: dict[str, BasePlugin]

    def __new__(cls) -> "PluginManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins = {}
        return cls._instance

    # ── Discovery ─────────────────────────────────────────────────

    def discover(self) -> None:
        """Auto-import every sub-package of ``app.plugins`` that exposes a
        module-level ``plugin`` instance."""
        import app.plugins as _pkg

        for _importer, modname, ispkg in pkgutil.iter_modules(_pkg.__path__):
            if not ispkg:
                continue
            fqn = f"app.plugins.{modname}"
            try:
                mod = importlib.import_module(fqn)
            except Exception:
                logger.exception("Failed to import plugin package {}", fqn)
                continue

            plug: BasePlugin | None = getattr(mod, "plugin", None)
            if plug is None:
                logger.warning(
                    "Plugin package {} has no `plugin` attribute – skipped", fqn,
                )
                continue
            if not isinstance(plug, BasePlugin):
                logger.warning(
                    "Plugin {} `plugin` is not a BasePlugin – skipped", fqn,
                )
                continue

            self._plugins[plug.key] = plug
            logger.info("Discovered plugin: {} ({})", plug.name, plug.key)

    # ── Provider registration ─────────────────────────────────────

    def register_providers(self) -> None:
        """Push every plugin's provider class into the shared ProviderRegistry."""
        for plug in self._plugins.values():
            cls = plug.model.provider_class()
            if cls.PROVIDER_KEY not in provider_registry:
                provider_registry.register(cls)

    # ── Accessors ─────────────────────────────────────────────────

    def get(self, key: str) -> BasePlugin:
        return self._plugins[key]

    def all_plugins(self) -> list[BasePlugin]:
        return list(self._plugins.values())

    def keys(self) -> list[str]:
        return list(self._plugins.keys())

    def __contains__(self, key: str) -> bool:
        return key in self._plugins

    def __repr__(self) -> str:
        return f"<PluginManager plugins={self.keys()}>"
