"""Background scheduler — per-source intervals for fetching prices."""

from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from sqlalchemy import select

from app.database import async_session_factory
from app.models import Asset, DataSource, PriceRecord
from app.providers import registry

scheduler = AsyncIOScheduler()


async def _fetch_single_source(source_id: int) -> None:
    """Fetch latest prices for a single DataSource."""
    async with async_session_factory() as session:
        src = await session.get(DataSource, source_id)
        if not src:
            logger.warning("Scheduler: source id={} no longer exists, removing job", source_id)
            job_id = f"fetch_source_{source_id}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            return

        if src.provider not in registry:
            logger.warning("Provider '{}' not registered — skipping source {}", src.provider, src.name)
            return

        assets = (
            await session.execute(
                select(Asset).where(Asset.source_id == src.id, Asset.is_active == 1)
            )
        ).scalars().all()

        if not assets:
            return

        symbols = [a.symbol for a in assets]
        sym_map = {a.symbol: a for a in assets}
        provider = registry.create(src.provider, base_url=src.base_url or "", api_key=src.api_key or "")

        try:
            points = await provider.fetch_latest(symbols)
            for pt in points:
                asset = sym_map.get(pt.symbol)
                if not asset:
                    continue
                rec = PriceRecord(
                    asset_id=asset.id,
                    timestamp=pt.timestamp or datetime.now(timezone.utc),
                    open=pt.open,
                    high=pt.high,
                    low=pt.low,
                    close=pt.close,
                    volume=pt.volume,
                    extra_json=str(pt.extra) if pt.extra else None,
                )
                session.add(rec)
            await session.commit()
            logger.info("Fetched {} points from source '{}'", len(points), src.name)
        except Exception:
            logger.exception("Error fetching from source '{}'", src.name)
        finally:
            await provider.close()


async def sync_scheduler_jobs() -> None:
    """Read all DataSources and create/update one job per source with its own interval."""
    async with async_session_factory() as session:
        sources = (await session.execute(select(DataSource))).scalars().all()

    active_job_ids: set[str] = set()
    for src in sources:
        job_id = f"fetch_source_{src.id}"
        active_job_ids.add(job_id)
        interval_sec = max(src.fetch_interval_ms / 1000.0, 0.001)

        existing = scheduler.get_job(job_id)
        if existing:
            # Reschedule if interval changed
            existing_interval = existing.trigger.interval.total_seconds()
            if abs(existing_interval - interval_sec) > 0.0005:
                scheduler.reschedule_job(
                    job_id, trigger="interval", seconds=interval_sec,
                )
                logger.info("Rescheduled source '{}' to interval={}ms", src.name, src.fetch_interval_ms)
        else:
            scheduler.add_job(
                _fetch_single_source,
                "interval",
                seconds=interval_sec,
                args=[src.id],
                id=job_id,
                replace_existing=True,
                next_run_time=datetime.now(timezone.utc),
            )
            logger.info("Added job for source '{}' interval={}ms", src.name, src.fetch_interval_ms)

    # Remove jobs for deleted sources
    for job in scheduler.get_jobs():
        if job.id.startswith("fetch_source_") and job.id not in active_job_ids:
            scheduler.remove_job(job.id)
            logger.info("Removed stale job {}", job.id)


def start_scheduler() -> None:
    """Start the scheduler (jobs are added via sync_scheduler_jobs)."""
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")
