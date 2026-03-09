"""Seed the database with default data sources & sample assets.

Seed data is drawn from every loaded **plugin** — each plugin declares its
own ``default_source()`` and ``default_assets()``, so adding a new plugin
automatically enriches the seed without touching this file.

Run:  python -m app.seed
"""

from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import select

from app.database import async_session_factory, init_db
from app.grafana import export_dashboard_json
from app.models import Asset, DataSource
from app.plugins import plugin_manager


def _bootstrap_plugins() -> None:
    """Discover plugins and register their providers."""
    plugin_manager.discover()
    plugin_manager.register_providers()


async def seed() -> None:
    """Insert seed data (idempotent — skips if source already exists).

    After seeding, the Grafana dashboard JSON is regenerated so that
    panel URLs reference the correct asset IDs.
    """
    _bootstrap_plugins()
    await init_db()

    plugins = plugin_manager.all_plugins()
    if not plugins:
        print("⚠  No plugins discovered — nothing to seed.")
        return

    source_map: dict[str, int] = {}          # plugin_key → source.id
    asset_map: dict[str, dict[str, int]] = {}  # plugin_key → {symbol: asset.id}

    async with async_session_factory() as session:
        # ── Data Sources (one per plugin) ─────────────────────────
        existing_names = set(
            (await session.execute(select(DataSource.name))).scalars().all()
        )

        for plug in plugins:
            src_kwargs = plug.default_source()
            src_name = src_kwargs["name"]
            category = plug.category

            if src_name in existing_names:
                row = (
                    await session.execute(
                        select(DataSource).where(DataSource.name == src_name)
                    )
                ).scalar_one()
                source_map[plug.key] = row.id
                print(f"  ✓ Source already exists: {src_name}")
            else:
                src = DataSource(category=category, **src_kwargs)
                session.add(src)
                await session.flush()
                source_map[plug.key] = src.id
                print(f"  + Created source: {src_name} (id={src.id})")

        # ── Assets (from each plugin) ────────────────────────────
        for plug in plugins:
            src_id = source_map[plug.key]
            asset_map.setdefault(plug.key, {})

            for asset_def in plug.default_assets():
                symbol = asset_def["symbol"]
                display = asset_def.get("display_name", symbol)
                exists = (
                    await session.execute(
                        select(Asset).where(
                            Asset.source_id == src_id, Asset.symbol == symbol
                        )
                    )
                ).scalar_one_or_none()

                if exists:
                    asset_map[plug.key][symbol] = exists.id
                    print(f"  ✓ Asset already exists: {symbol}")
                else:
                    asset = Asset(source_id=src_id, symbol=symbol, display_name=display)
                    session.add(asset)
                    await session.flush()
                    asset_map[plug.key][symbol] = asset.id
                    print(f"  + Created asset: {symbol} (source={plug.name})")

        await session.commit()

    # ── Regenerate Grafana dashboard from plugins ────────────────
    fpath = export_dashboard_json(source_map=source_map, asset_map=asset_map)
    print(f"\n  ↻ Dashboard JSON regenerated → {fpath}")
    print("\nSeed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
