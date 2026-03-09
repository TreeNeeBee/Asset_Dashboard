"""Base classes for the MVVM plugin framework.

Defines the abstract contracts that every plugin must fulfil:

* :class:`BasePluginModel` — data provider + seed data
* :class:`BasePluginView`  — Grafana panel definitions
* :class:`BasePlugin`      — ViewModel that binds Model ↔ View
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional

from fastapi import APIRouter

from app.models import SourceCategory
from app.providers import BaseDataProvider

from .config import PluginConfig


# ────────────────────────────────────────────────────────────────────
# Constants shared by the View layer
# ────────────────────────────────────────────────────────────────────

INFINITY_DATASOURCE = {
    "type": "yesoreyeram-infinity-datasource",
    "uid": "PD043CF1CCE24D2D7",
}

API_BASE_URL = "http://api:8000"


# ────────────────────────────────────────────────────────────────────
# Grafana panel descriptor
# ────────────────────────────────────────────────────────────────────

@dataclass
class GrafanaPanelDef:
    """Declarative description of a Grafana panel contributed by a plugin."""

    panel_type: str                    # "timeseries", "table", "stat", …
    title: str
    width: int = 12                    # grid width (max 24)
    height: int = 8
    url_path: str = ""
    root_selector: str = "items"
    columns: list[dict[str, str]] = field(default_factory=list)
    field_config: dict[str, Any] = field(default_factory=dict)


# ────────────────────────────────────────────────────────────────────
# IntervalConfig — lightweight interval holder
# ────────────────────────────────────────────────────────────────────

@dataclass
class IntervalConfig:
    """Configurable fetch interval with a hard minimum of 1 ms."""

    fetch_interval_ms: int = 300_000
    MIN_INTERVAL_MS: ClassVar[int] = 1

    def __post_init__(self) -> None:
        self.fetch_interval_ms = max(self.MIN_INTERVAL_MS, self.fetch_interval_ms)

    @property
    def seconds(self) -> float:
        return self.fetch_interval_ms / 1000.0

    def update(self, ms: int) -> None:
        self.fetch_interval_ms = max(self.MIN_INTERVAL_MS, ms)


# ────────────────────────────────────────────────────────────────────
# Model layer — data provider + seed data
# ────────────────────────────────────────────────────────────────────

class BasePluginModel(abc.ABC):
    """Data layer: provider class and seed data definitions."""

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
        """Return kwargs for ``DataSource(**…)``."""

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
        """Return Grafana panel definitions."""


# ────────────────────────────────────────────────────────────────────
# ViewModel — binds Model ↔ View, owns configuration
# ────────────────────────────────────────────────────────────────────

class BasePlugin(abc.ABC):
    """ViewModel: metadata + configuration + Model/View coordination.

    Sub-classes must supply ``key``, ``name``, ``category`` properties and
    pass concrete Model / View instances to ``__init__``.
    """

    def __init__(
        self,
        *,
        model: BasePluginModel,
        view: BasePluginView,
        config: PluginConfig | None = None,
    ) -> None:
        self._config = config
        ms = config.fetch_interval_ms if config and config.raw else 300_000
        self._interval = IntervalConfig(fetch_interval_ms=ms)
        self._model = model
        self._view = view

    # ── Metadata ──────────────────────────────────────────────────

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
        """Maps to the DB ``SourceCategory`` enum."""

    # ── MVVM layer access ─────────────────────────────────────────

    @property
    def model(self) -> BasePluginModel:
        return self._model

    @property
    def view(self) -> BasePluginView:
        return self._view

    @property
    def interval(self) -> IntervalConfig:
        return self._interval

    @property
    def config(self) -> PluginConfig | None:
        return self._config

    # ── Interval sync (keeps IntervalConfig + PluginConfig in sync)

    def update_interval(self, ms: int) -> None:
        """Update fetch interval — syncs both in-memory state and config."""
        self._interval.update(ms)
        if self._config:
            self._config.fetch_interval_ms = ms

    # ── Convenience delegations ───────────────────────────────────

    def provider_class(self) -> type[BaseDataProvider]:
        return self._model.provider_class()

    def default_source(self) -> dict[str, Any]:
        """Build source dict (Model seed + config API key + interval)."""
        src = dict(self._model.default_source())
        if self._config:
            key = self._config.read_api_key()
            if key:
                src["api_key"] = key
        src.setdefault("fetch_interval_ms", self._interval.fetch_interval_ms)
        return src

    def default_assets(self) -> list[dict[str, str]]:
        return self._model.default_assets()

    def grafana_panels(
        self, source_id: int, asset_map: dict[str, int]
    ) -> list[GrafanaPanelDef]:
        return self._view.grafana_panels(source_id, asset_map)

    def api_router(self) -> Optional[APIRouter]:
        """Return an extra FastAPI router, or ``None``."""
        return None
