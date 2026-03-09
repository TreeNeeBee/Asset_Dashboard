"""Router for Grafana dashboard management.

Provides endpoints to regenerate the provisioned dashboard JSON
from the currently loaded plugins + database state.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.grafana import export_dashboard_json
from app.models import Asset, DataSource
from app.plugins import plugin_manager

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


async def _build_maps(session: AsyncSession) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Build source_map & asset_map by matching DB rows to loaded plugins."""
    source_map: dict[str, int] = {}
    asset_map: dict[str, dict[str, int]] = {}

    sources = (await session.execute(select(DataSource))).scalars().all()
    provider_to_source = {s.provider: s for s in sources}

    for plug in plugin_manager.all_plugins():
        pcls = plug.provider_class()
        src = provider_to_source.get(pcls.PROVIDER_KEY)
        if src is None:
            continue
        source_map[plug.key] = src.id

        assets = (
            await session.execute(
                select(Asset).where(Asset.source_id == src.id, Asset.is_active == 1)
            )
        ).scalars().all()
        asset_map[plug.key] = {a.symbol: a.id for a in assets}

    return source_map, asset_map


@router.post("/regenerate")
async def regenerate_dashboard(session: AsyncSession = Depends(get_session)):
    """Regenerate the Grafana provisioned dashboard JSON from plugins + DB state."""
    source_map, asset_map = await _build_maps(session)
    fpath = export_dashboard_json(source_map=source_map, asset_map=asset_map)
    return {
        "status": "ok",
        "file": str(fpath),
        "plugins": list(source_map.keys()),
        "hint": "Grafana will pick up changes within its polling interval (default 10s).",
    }


@router.get("/preview")
async def preview_dashboard(session: AsyncSession = Depends(get_session)):
    """Return the dashboard JSON model (for debugging / preview)."""
    from app.grafana import build_dashboard_model

    source_map, asset_map = await _build_maps(session)
    return build_dashboard_model(source_map, asset_map)
