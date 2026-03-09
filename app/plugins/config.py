"""Per-plugin YAML configuration — single source of truth for plugin settings.

Each plugin owns a ``config.yaml`` file next to its ``__init__.py``.
The :class:`PluginConfig` class reads/writes this file and provides
typed property accessors for all standard fields.

Standard top-level keys::

    # Metadata
    key: "crypto"
    name: "Cryptocurrency"
    category: "crypto"
    description: "..."
    version: "1.0.0"

    # View
    panel_title_prefix: "Crypto"
    close_column_label: "Close"

    # Interval
    fetch_interval_ms: 60000

    # Source
    source:
      name: "CoinGecko Crypto"
      provider: "crypto_coingecko"
      base_url: "https://..."
      description: "..."
    api_key_file: ""

    # Assets
    assets:
      - symbol: "BTC"
        display_name: "Bitcoin"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from loguru import logger


class PluginConfig:
    """Reads / writes a per-plugin ``config.yaml``.

    Any extra keys are preserved on save so users can add custom settings.
    """

    def __init__(self, config_path: Path) -> None:
        self._path = config_path
        self._data: dict[str, Any] = {}
        self.load()

    # ── I/O ───────────────────────────────────────────────────────

    def load(self) -> None:
        """Load config from disk."""
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
            yaml.dump(
                self._data, f,
                default_flow_style=False, sort_keys=False, allow_unicode=True,
            )
        logger.debug("Saved plugin config → {}", self._path)

    def reload(self) -> None:
        """Alias for :meth:`load`."""
        self.load()

    # ── Generic accessors ─────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._path

    @property
    def raw(self) -> dict[str, Any]:
        """Full config dict (mutable reference)."""
        return self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    # ── Plugin metadata ───────────────────────────────────────────

    @property
    def key(self) -> str:
        return str(self._data.get("key", ""))

    @property
    def plugin_name(self) -> str:
        """Human-readable name (``name`` field in YAML)."""
        return str(self._data.get("name", ""))

    @property
    def category(self) -> str:
        return str(self._data.get("category", "custom"))

    @property
    def description(self) -> str:
        return str(self._data.get("description", ""))

    @property
    def version(self) -> str:
        return str(self._data.get("version", "1.0.0"))

    # ── Grafana view settings ─────────────────────────────────────

    @property
    def panel_title_prefix(self) -> str:
        return str(self._data.get("panel_title_prefix", self.plugin_name))

    @property
    def close_column_label(self) -> str:
        return str(self._data.get("close_column_label", "Close"))

    # ── Fetch interval ────────────────────────────────────────────

    @property
    def fetch_interval_ms(self) -> int:
        val = self._data.get("fetch_interval_ms", 300_000)
        return max(1, int(val))

    @fetch_interval_ms.setter
    def fetch_interval_ms(self, ms: int) -> None:
        self._data["fetch_interval_ms"] = max(1, int(ms))

    @property
    def interval_seconds(self) -> float:
        """Interval converted to fractional seconds."""
        return self.fetch_interval_ms / 1000.0

    # ── Data source ───────────────────────────────────────────────

    @property
    def source(self) -> dict[str, Any]:
        return dict(self._data.get("source", {}))

    @source.setter
    def source(self, val: dict[str, Any]) -> None:
        self._data["source"] = dict(val)

    # ── API key ───────────────────────────────────────────────────

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
        if not p.is_absolute():
            p = self._path.parent / p
        if not p.exists():
            logger.warning("api_key_file not found: {}", p)
            return ""
        return p.read_text(encoding="utf-8").strip()

    # ── Assets ────────────────────────────────────────────────────

    @property
    def assets(self) -> list[dict[str, str]]:
        return list(self._data.get("assets", []))

    @assets.setter
    def assets(self, val: list[dict[str, str]]) -> None:
        self._data["assets"] = list(val)

    # ── repr ──────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<PluginConfig path={self._path}>"
