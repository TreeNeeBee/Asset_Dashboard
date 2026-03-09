"""CRUD router for Asset management (dynamic add / remove tracked assets)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Asset
from app.schemas import AssetCreate, AssetRead, AssetUpdate, PaginatedResponse

router = APIRouter(prefix="/api/v1/assets", tags=["Assets"])


@router.get("", response_model=PaginatedResponse)
async def list_assets(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    source_id: int | None = Query(None),
    active_only: bool = Query(True),
    session: AsyncSession = Depends(get_session),
):
    base = select(Asset)
    count_base = select(func.count(Asset.id))
    if source_id is not None:
        base = base.where(Asset.source_id == source_id)
        count_base = count_base.where(Asset.source_id == source_id)
    if active_only:
        base = base.where(Asset.is_active == 1)
        count_base = count_base.where(Asset.is_active == 1)

    total = (await session.execute(count_base)).scalar_one()
    rows = (await session.execute(base.offset((page - 1) * size).limit(size))).scalars().all()
    return PaginatedResponse(
        total=total, page=page, size=size,
        items=[AssetRead.model_validate(r) for r in rows],
    )


@router.get("/{asset_id}", response_model=AssetRead)
async def get_asset(asset_id: int, session: AsyncSession = Depends(get_session)):
    obj = await session.get(Asset, asset_id)
    if not obj:
        raise HTTPException(404, "Asset not found")
    return AssetRead.model_validate(obj)


@router.post("", response_model=AssetRead, status_code=201)
async def create_asset(body: AssetCreate, session: AsyncSession = Depends(get_session)):
    obj = Asset(**body.model_dump())
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return AssetRead.model_validate(obj)


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset(asset_id: int, body: AssetUpdate, session: AsyncSession = Depends(get_session)):
    obj = await session.get(Asset, asset_id)
    if not obj:
        raise HTTPException(404, "Asset not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await session.commit()
    await session.refresh(obj)
    return AssetRead.model_validate(obj)


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(asset_id: int, session: AsyncSession = Depends(get_session)):
    obj = await session.get(Asset, asset_id)
    if not obj:
        raise HTTPException(404, "Asset not found")
    await session.delete(obj)
    await session.commit()
