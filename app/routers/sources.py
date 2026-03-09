"""CRUD router for DataSource management (dynamic add / remove)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import DataSource
from app.providers import registry
from app.schemas import (
    DataSourceCreate,
    DataSourceRead,
    DataSourceUpdate,
    PaginatedResponse,
)
from app.scheduler import sync_scheduler_jobs

router = APIRouter(prefix="/api/v1/sources", tags=["Data Sources"])


# ── Provider registry info (MUST be before /{source_id} to avoid capture) ────

@router.get("/registry/providers")
async def list_registered_providers():
    """Return the list of currently registered provider keys."""
    return {"providers": registry.list_keys()}


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=PaginatedResponse)
async def list_sources(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    total = (await session.execute(select(func.count(DataSource.id)))).scalar_one()
    stmt = select(DataSource).offset((page - 1) * size).limit(size)
    rows = (await session.execute(stmt)).scalars().all()
    return PaginatedResponse(
        total=total,
        page=page,
        size=size,
        items=[DataSourceRead.model_validate(r) for r in rows],
    )


# ── Get by ID ─────────────────────────────────────────────────────────────────

@router.get("/{source_id}", response_model=DataSourceRead)
async def get_source(source_id: int, session: AsyncSession = Depends(get_session)):
    obj = await session.get(DataSource, source_id)
    if not obj:
        raise HTTPException(404, "DataSource not found")
    return DataSourceRead.model_validate(obj)


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("", response_model=DataSourceRead, status_code=201)
async def create_source(body: DataSourceCreate, session: AsyncSession = Depends(get_session)):
    obj = DataSource(**body.model_dump())
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    await sync_scheduler_jobs()
    return DataSourceRead.model_validate(obj)


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{source_id}", response_model=DataSourceRead)
async def update_source(
    source_id: int,
    body: DataSourceUpdate,
    session: AsyncSession = Depends(get_session),
):
    obj = await session.get(DataSource, source_id)
    if not obj:
        raise HTTPException(404, "DataSource not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await session.commit()
    await session.refresh(obj)
    await sync_scheduler_jobs()
    return DataSourceRead.model_validate(obj)


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{source_id}", status_code=204)
async def delete_source(source_id: int, session: AsyncSession = Depends(get_session)):
    obj = await session.get(DataSource, source_id)
    if not obj:
        raise HTTPException(404, "DataSource not found")
    await session.delete(obj)
    await session.commit()
    await sync_scheduler_jobs()
