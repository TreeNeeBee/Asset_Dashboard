"""MVVM plugin framework for Asset Dashboard.

Every asset-type (crypto, stock, FX, …) is a **plugin** structured as
three MVVM layers plus a YAML configuration file:

* **Model**     (``BasePluginModel``)     — data provider + seed data
* **View**      (``BasePluginView``)      — Grafana panel definitions
* **ViewModel** (``BasePlugin``)          — metadata, configuration,
  fetch-interval management; binds Model ↔ View
* **Config**    (``PluginConfig``)        — per-plugin ``config.yaml``

Plugins are discovered automatically by scanning sub-packages of
``app.plugins``.  Each sub-package must expose a module-level ``plugin``
instance that inherits from :class:`BasePlugin`.

Usage::

    from app.plugins import plugin_manager
    plugin_manager.discover()
    plugin_manager.register_providers()
"""

from __future__ import annotations

import abc
import importlib
import pkgutil
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Optional

import yaml
from fastapi import APIRouter
from loguru import logger

from app.models import SourceCategory
from app.providers import BaseDataProvider, registry as provider_registry


# ────────────────────────────────────────────────────────────────────
# Grafana panel descriptor (shared by View layer)
# ────────────────────────────────────────────────────────────────────

INFINITY_DATASOURCE = {
    "type": "yesoreyeram-infinity-datasource",
    "uid": "PD043CF1CCE24D2D7",
}

API_BASE_URL = "http://api:8000"


@dataclass
class GrafanaPanelDef:
    """Declarative description of a Grafana panel contributed by a plugin."""

    panel_type: str                    # "timeseries", "table", "stat", "barchart" …
    title: str
    width: int = 12                    # grid width (max 24)
    height: int = 8
    # What data to show  ─ one of:
    url_path: str = ""                 # e.g. "/api/v1/prices?asset_id={asset_id}&size=500"
    root_selector: str = "items"
    columns: list[dict[str, str]] = field(default_factory=list)
    # Extra Grafana panel options
    field_config: dict[str, Any] = field(default_factory=dict)


# ────────────────────────────────────────────────────────────────────
# Fetch-interval configuration
# ────────────────────────────────────────────────────────────────────

@dataclass
class IntervalConfig:
    """Configurable fetch interval with hard minimum of 1 ms."""

    fetch_interval_ms: int = 300_000
    MIN_INTERVAL_MS: ClassVar[int] = 1

    def __post_init__(self) -> None:
        self.fetch_interval_ms = max(self.MIN_INTERVAL_MS, self.fetch_interval_ms)

    @property
    def seconds(self) -> float:
        """Interval converted to fractional seconds."""
        return self.fetch_interval_ms / 1000.0

    def update(self, ms: int) -> None:
        """Update interval (enforcing minimum)."""
        self.fetch_interval_ms = max(self.MIN_INTERVAL_MS, ms)


# ────────────────────────────────────────────────────────────────────
# Per-plugin YAML configuration
# ────────────────────────────────────────────────────────────────────

class PluginConfig:
    """Reads / writes a per-plugin ``config.yaml`` that lives next to the
    plugin's ``__init__.py``.

    Required top-level keys::

        fetch_interval_ms: 60000         # min 1
        source:
          name: "CoinGecko Crypto"
          provider: "crypto_coingecko"
          base_url: "https://api.coingecko.com/api/v3"
          description: "..."
        api_key_file: ""                 # path to key file (empty = no key)

    Any extra keys are preserved on save so users can add custom settings.
    """

    _REQUIRED_KEYS = {"fetch_interval_ms", "source", "api_key_file"}

    def __init__(self, config_path: Path) -> None:
        self._path = config_path
        self._data: dict[str, Any] = {}
        self.load()

    # ── I/O ───────────────────────────────────────────────────────

    def load(self) -> None:
        """Load config from disk.  If the file does not exist, ``_data``
        stays empty and callers must call :meth:`save` first."""
        if not self._path.exists():
            logger.warning("Plugin config not found: {}", self._path)
            return
        with open(self._path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        self._data = loaded if isinstance(loaded, dict) else {}
        logger.debug("Loaded plugin config from {}", self._path)

    def save(self) -> None:
        """Persist current config dict back to YAML."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(self._data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        logger.debug("Saved plugin config → {}", self._path)

    def reload(self) -> None:
        """Alias for :meth:`load`."""
        self.load()

    # ── Typed accessors ───────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._path

    @property
    def raw(self) -> dict[str, Any]:
        """Full config dict (mutable)."""
        return self._data

    # -- fetch_interval_ms --

    @property
    def fetch_interval_ms(self) -> int:
        val = self._data.get("fetch_interval_ms", 300_000)
        return max(1, int(val))

    @fetch_interval_ms.setter
    def fetch_interval_ms(self, ms: int) -> None:
        self._data["fetch_interval_ms"] = max(1, int(ms))

    # -- source dict --

    @property
    def source(self) -> dict[str, Any]:
        return dict(self._data.get("source", {}))

    @source.setter
    def source(self, val: dict[str, Any]) -> None:
        self._data["source"] = dict(val)

    # -- api_key_file --

    @property
    def api_key_file(self) -> str:
        return str(self._data.get("api_key_file", "") or "")

    @api_key_file.setter
    def api_key_file(self, path: str) -> None:
        self._data["api_key_file"] = path

    def read_api_key(self) -> str:
        """Read the API key from the file pointed to by ``api_key_file``.

        Returns empty string if no key file is configured or the file
        does not exist.
        """
        kf = self.api_key_file
        if not kf:
            return ""
        p = Path(kf)
        # Allow relative paths resolved against the config file's directory
        if not p.is_absolute():
            p = self._path.parent / p
        if not p.exists():
            logger.warning("api_key_file not found: {}", p)
            return ""
        return p.read_text(encoding="utf-8").strip()

    # -- assets --

    @property
    def assets(self) -> list[dict[str, str]]:
        return list(self._data.get("assets", []))

    @assets.setter
    def assets(self, val: list[dict[str, str]]) -> None:
        self._data["assets"] = list(val)

    # -- arbitrary extra settings --

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __repr__(self) -> str:
        return f"<PluginConfig path={self._path}>"


# ────────────────────────────────────────────────────────────────────
# Model layer — data provider + seed data
# ────────────────────────────────────────────────────────────────────

class BasePluginModel(abc.ABC):
    """Data layer: provider class and seed data definitions.

    Receives a :class:`PluginConfig` so seed data can be derived from
    the config file instead of being hard-coded.
    """

    def __init__(self, config: PluginConfig | None = None) -> None:
        self._config = config

    @property
    def config(self) -> PluginConfig | None:
        return self._config

    @abc.abstractmethod
    def provider_class(self) -> type[BaseDataProvider]:
        """Return the concrete BaseDataProvider subclass."""

    @abc.abstractmethod
    def default_source(self) -> dict[str, Any]:
        """Return kwargs for ``DataSource(**…)`` (sans ``category`` and
        ``fetch_interval_ms`` — interval is managed by the ViewModel)."""

    @abc.abstractmethod
    def default_assets(self) -> list[dict[str, str]]:
        """Return ``[{"symbol": …, "display_name": …}, …]``."""


# ────────────────────────────────────────────────────────────────────
# View layer — Grafana panel definitions
# ────────────────────────────────────────────────────────────────────

class BasePluginView(abc.ABC):
    """Presentation layer: Grafana dashboard panel definitions."""

    @abc.abstractmethod
    def grafana_panels(
        self, source_id: int, asset_map: dict[str, int]
    ) -> list[GrafanaPanelDef]:
        """Return Grafana panel definitions.

        *asset_map* maps symbol → DB asset.id so URLs can be templated.
        """


# ────────────────────────────────────────────────────────────────────
# ViewModel (BasePlugin) — binds Model ↔ View, owns configuration
# ────────────────────────────────────────────────────────────────────

class BasePlugin(abc.ABC):
    """ViewModel: metadata + configuration + Model/View coordination.

    Sub-classes must:

    1. Supply ``key``, ``name``, ``category`` properties.
    2. Pass concrete ``BasePluginModel`` and ``BasePluginView`` instances
       (plus an optional ``IntervalConfig``) to ``__init__``.

    A ``config.yaml`` file beside the plugin's ``__init__.py`` is loaded
    automatically.  The interval config is synchronised with the YAML on
    init and after every update.
    """

    def __init__(
        self,
        *,
        model: BasePluginModel,
        view: BasePluginView,
        interval: IntervalConfig | None = None,
        config: PluginConfig | None = None,
    ) -> None:
        self._config = config
        # If config is loaded, let it drive the interval
        if self._config and self._config.raw:
            effective_ms = self._config.fetch_interval_ms
        elif interval:
            effective_ms = interval.fetch_interval_ms
        else:
            effective_ms = 300_000
        self._interval = IntervalConfig(fetch_interval_ms=effective_ms)
        self._model = model
        self._view = view

    # ── Metadata (ViewModel responsibility) ───────────────────────

    @property
    @abc.abstractmethod
    def key(self) -> str:
        """Unique short identifier, e.g. ``crypto``."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable name, e.g. ``Cryptocurrency``."""

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return ""

    @property
    @abc.abstractmethod
    def category(self) -> SourceCategory:
        """Maps to the DB enum."""

    # ── MVVM layer access ─────────────────────────────────────────

    @property
    def model(self) -> BasePluginModel:
        """Data layer (provider + seed data)."""
        return self._model

    @property
    def view(self) -> BasePluginView:
        """Presentation layer (Grafana panels)."""
        return self._view

    @property
    def interval(self) -> IntervalConfig:
        """Fetch-interval configuration (min 1 ms)."""
        return self._interval

    @property
    def config(self) -> PluginConfig | None:
        """Per-plugin YAML configuration (``None`` if not loaded)."""
        return self._config

    # ── Convenience delegations (backward-compatible) ─────────────

    def provider_class(self) -> type[BaseDataProvider]:
        return self._model.provider_class()

    def default_source(self) -> dict[str, Any]:
        """Merge Model seed data with ViewModel interval and YAML config."""
        src = dict(self._model.default_source())
        # YAML config overrides hard-coded values
        if self._config and self._config.raw:
            cfg_src = self._config.source
            if cfg_src:
                src.update({k: v for k, v in cfg_src.items() if v is not None and v != ""})
            # Resolve API key from file
            key = self._config.read_api_key()
            if key:
                src["api_key"] = key
        src.setdefault("fetch_interval_ms", self._interval.fetch_interval_ms)
        return src

    def default_assets(self) -> list[dict[str, str]]:
        """Return assets — prefer YAML config if it has an ``assets`` list."""
        if self._config and self._config.assets:
            return self._config.assets
        return self._model.default_assets()

    def grafana_panels(
        self, source_id: int, asset_map: dict[str, int]
    ) -> list[GrafanaPanelDef]:
        return self._view.grafana_panels(source_id, asset_map)

    # ── Optional API routes ───────────────────────────────────────

    def api_router(self) -> Optional[APIRouter]:
        """Return an extra FastAPI router, or ``None``."""
        return None


# ────────────────────────────────────────────────────────────────────
#  Plugin manager (singleton)
# ────────────────────────────────────────────────────────────────────

class PluginManager:
    """Discovers, loads and exposes all registered plugins."""

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

        for importer, modname, ispkg in pkgutil.iter_modules(_pkg.__path__):
            if not ispkg:
                continue  # only sub-packages
            fqn = f"app.plugins.{modname}"
            try:
                mod = importlib.import_module(fqn)
            except Exception:
                logger.exception("Failed to import plugin package {}", fqn)
                continue

            plug: BasePlugin | None = getattr(mod, "plugin", None)
            if plug is None:
                logger.warning("Plugin package {} has no `plugin` attribute – skipped", fqn)
                continue
            if not isinstance(plug, BasePlugin):
                logger.warning("Plugin {} `plugin` is not a BasePlugin – skipped", fqn)
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


# Module-level singleton
plugin_manager = PluginManager()
