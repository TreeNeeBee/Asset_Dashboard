"""Application entry-point — builds and returns the FastAPI app."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.config import settings, validate_secrets
from app.database import get_session, init_db
from app.models import DataSource
from app.plugins import plugin_manager
from app.routers import assets, dashboard, prices, sources
from app.scheduler import start_scheduler, stop_scheduler, sync_scheduler_jobs
from app.tradingview import router as tv_router


class IntervalUpdateRequest(BaseModel):
    """Request body for updating a plugin's fetch interval."""
    fetch_interval_ms: int = Field(..., ge=1, description="Fetch interval in ms (min 1)")


class PluginConfigUpdateRequest(BaseModel):
    """Request body for updating a plugin's configuration."""
    fetch_interval_ms: int | None = Field(None, ge=1, description="Fetch interval in ms (min 1)")
    source: dict[str, Any] | None = Field(None, description="Data source settings")
    api_key_file: str | None = Field(None, description="Path to API key file")
    assets: list[dict[str, str]] | None = Field(None, description="Tracked assets list")


@asynccontextmanager
async def lifespan(application: FastAPI):  # noqa: ARG001
    """Startup / shutdown lifecycle hook."""
    # ── Validate secrets / API keys ───────────────────────────────
    validate_secrets()

    # ── Discover & register plugins ───────────────────────────────
    logger.info("Discovering plugins …")
    plugin_manager.discover()
    plugin_manager.register_providers()
    logger.info("Loaded plugins: {}", plugin_manager.keys())

    # ── Mount plugin-contributed routes ────────────────────────────
    for plug in plugin_manager.all_plugins():
        extra = plug.api_router()
        if extra is not None:
            application.include_router(extra)
            logger.info("Mounted extra router from plugin '{}'", plug.key)

    logger.info("Initialising database …")
    await init_db()

    logger.info("Starting background scheduler …")
    start_scheduler()
    await sync_scheduler_jobs()

    yield  # ← app is running

    logger.info("Shutting down scheduler …")
    stop_scheduler()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Asset Dashboard API",
        description=(
            "Unified REST API for crypto / stock / FX asset tracking.\n"
            "Consumed by Grafana dashboards and TradingView charts.\n\n"
            "Asset types are loaded as **plugins** — add a new sub-package "
            "under `app/plugins/` to extend the system."
        ),
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS — allow Grafana & local dev
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount core routers
    application.include_router(sources.router)
    application.include_router(assets.router)
    application.include_router(prices.router)
    application.include_router(dashboard.router)
    application.include_router(tv_router)

    # ── Plugin introspection endpoint ─────────────────────────────
    @application.get("/api/v1/plugins", tags=["Plugins"])
    async def list_plugins():
        """Return metadata about all loaded plugins."""
        items = []
        for p in plugin_manager.all_plugins():
            items.append({
                "key": p.key,
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "category": p.category.value,
                "provider_key": p.model.provider_class().PROVIDER_KEY,
                "fetch_interval_ms": p.interval.fetch_interval_ms,
            })
        return {"total": len(items), "plugins": items}

    @application.get("/api/v1/plugins/{plugin_key}", tags=["Plugins"])
    async def get_plugin(plugin_key: str):
        """Return detailed info for a single plugin (MVVM layers)."""
        if plugin_key not in plugin_manager:
            raise HTTPException(404, f"Plugin '{plugin_key}' not found")
        p = plugin_manager.get(plugin_key)
        result: dict[str, Any] = {
            "key": p.key,
            "name": p.name,
            "version": p.version,
            "description": p.description,
            "category": p.category.value,
            "provider_key": p.model.provider_class().PROVIDER_KEY,
            "fetch_interval_ms": p.interval.fetch_interval_ms,
            "model": {
                "default_source": p.model.default_source(),
                "default_assets": p.model.default_assets(),
            },
            "view": {
                "panel_count_hint": "call grafana_panels() with real IDs",
            },
        }
        # Include config details if available
        if p.config:
            result["config"] = {
                "path": str(p.config.path),
                "raw": p.config.raw,
            }
        return result

    # ── Plugin config CRUD ────────────────────────────────────────

    @application.get("/api/v1/plugins/{plugin_key}/config", tags=["Plugins"])
    async def get_plugin_config(plugin_key: str):
        """Return the full YAML configuration for a plugin."""
        if plugin_key not in plugin_manager:
            raise HTTPException(404, f"Plugin '{plugin_key}' not found")
        plug = plugin_manager.get(plugin_key)
        if not plug.config:
            raise HTTPException(404, f"Plugin '{plugin_key}' has no config file")
        plug.config.reload()
        return {
            "plugin": plugin_key,
            "config_path": str(plug.config.path),
            "config": plug.config.raw,
        }

    @application.patch("/api/v1/plugins/{plugin_key}/config", tags=["Plugins"])
    async def update_plugin_config(
        plugin_key: str,
        body: PluginConfigUpdateRequest,
        session: AsyncSession = Depends(get_session),
    ):
        """Update plugin configuration — saves to config.yaml, updates
        in-memory state, and re-syncs the DB + scheduler."""
        if plugin_key not in plugin_manager:
            raise HTTPException(404, f"Plugin '{plugin_key}' not found")
        plug = plugin_manager.get(plugin_key)
        if not plug.config:
            raise HTTPException(404, f"Plugin '{plugin_key}' has no config file")

        changed = False
        if body.fetch_interval_ms is not None:
            plug.update_interval(body.fetch_interval_ms)
            changed = True
        if body.source is not None:
            plug.config.source = body.source
            changed = True
        if body.api_key_file is not None:
            plug.config.api_key_file = body.api_key_file
            changed = True
        if body.assets is not None:
            plug.config.assets = body.assets
            changed = True

        if changed:
            plug.config.save()
            # Persist interval to DB
            src_name = plug.model.default_source().get("name", "")
            if src_name:
                row = (
                    await session.execute(
                        select(DataSource).where(DataSource.name == src_name)
                    )
                ).scalar_one_or_none()
                if row:
                    row.fetch_interval_ms = plug.interval.fetch_interval_ms
                    await session.commit()
                    await sync_scheduler_jobs()

        return {
            "plugin": plugin_key,
            "config": plug.config.raw,
        }

    @application.patch("/api/v1/plugins/{plugin_key}/interval", tags=["Plugins"])
    async def update_plugin_interval(
        plugin_key: str,
        body: IntervalUpdateRequest,
        session: AsyncSession = Depends(get_session),
    ):
        """Update the fetch interval for a plugin (min 1 ms).

        Updates both the in-memory ViewModel config and the database
        DataSource row, then re-syncs the scheduler.
        """
        if plugin_key not in plugin_manager:
            raise HTTPException(404, f"Plugin '{plugin_key}' not found")

        plug = plugin_manager.get(plugin_key)
        plug.update_interval(body.fetch_interval_ms)

        # Persist to config.yaml
        if plug.config:
            plug.config.save()

        # Persist to DB
        src_name = plug.model.default_source()["name"]
        row = (
            await session.execute(
                select(DataSource).where(DataSource.name == src_name)
            )
        ).scalar_one_or_none()
        if row:
            row.fetch_interval_ms = plug.interval.fetch_interval_ms
            await session.commit()
            await sync_scheduler_jobs()

        return {
            "plugin": plugin_key,
            "fetch_interval_ms": plug.interval.fetch_interval_ms,
        }

    @application.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok"}

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
