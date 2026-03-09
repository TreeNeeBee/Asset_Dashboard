"""Router for price records — read & manual ingest, plus live-fetch trigger."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Asset, DataSource, PriceRecord
from app.providers import registry
from app.schemas import PaginatedResponse, PriceRecordCreate, PriceRecordRead

router = APIRouter(prefix="/api/v1/prices", tags=["Prices"])


# ── List price records (with optional filters) ───────────────────────────────

@router.get("", response_model=PaginatedResponse)
async def list_prices(
    asset_id: int | None = Query(None),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    base = select(PriceRecord)
    cnt = select(func.count(PriceRecord.id))

    if asset_id is not None:
        base = base.where(PriceRecord.asset_id == asset_id)
        cnt = cnt.where(PriceRecord.asset_id == asset_id)
    if start:
        base = base.where(PriceRecord.timestamp >= start)
        cnt = cnt.where(PriceRecord.timestamp >= start)
    if end:
        base = base.where(PriceRecord.timestamp <= end)
        cnt = cnt.where(PriceRecord.timestamp <= end)

    total = (await session.execute(cnt)).scalar_one()
    rows = (
        await session.execute(
            base.order_by(PriceRecord.timestamp.desc()).offset((page - 1) * size).limit(size)
        )
    ).scalars().all()

    return PaginatedResponse(
        total=total, page=page, size=size,
        items=[PriceRecordRead.model_validate(r) for r in rows],
    )


# ── Manual insert ─────────────────────────────────────────────────────────────

@router.post("", response_model=PriceRecordRead, status_code=201)
async def create_price(body: PriceRecordCreate, session: AsyncSession = Depends(get_session)):
    obj = PriceRecord(**body.model_dump())
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return PriceRecordRead.model_validate(obj)


# ── Trigger a live fetch for one data source ──────────────────────────────────

@router.post("/fetch/{source_id}", tags=["Prices"])
async def trigger_fetch(source_id: int, session: AsyncSession = Depends(get_session)):
    """Immediately fetch latest prices for all assets under the given data source."""
    src = await session.get(DataSource, source_id)
    if not src:
        raise HTTPException(404, "DataSource not found")

    if src.provider not in registry:
        raise HTTPException(
            400,
            f"Provider '{src.provider}' is not registered. Available: {registry.list_keys()}",
        )

    provider = registry.create(src.provider, base_url=src.base_url or "", api_key=src.api_key or "")

    # Gather active assets
    assets = (
        await session.execute(
            select(Asset).where(Asset.source_id == source_id, Asset.is_active == 1)
        )
    ).scalars().all()

    if not assets:
        return {"fetched": 0, "message": "No active assets for this source"}

    symbols = [a.symbol for a in assets]
    sym_to_asset = {a.symbol: a for a in assets}

    try:
        points = await provider.fetch_latest(symbols)
    finally:
        await provider.close()

    saved = 0
    for pt in points:
        asset = sym_to_asset.get(pt.symbol)
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
        saved += 1
    await session.commit()

    return {"fetched": saved, "symbols": [p.symbol for p in points]}
