"""Pydantic schemas — request / response models for the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models import SourceCategory


# ── DataSource ────────────────────────────────────────────────────────────────

class DataSourceCreate(BaseModel):
    name: str = Field(..., max_length=64, examples=["CoinGecko Crypto"])
    category: SourceCategory
    provider: str = Field(..., max_length=128, examples=["crypto_coingecko"])
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    description: Optional[str] = None
    fetch_interval_ms: int = Field(300000, ge=1, description="Fetch interval in milliseconds (min 1ms)")


class DataSourceUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=64)
    category: Optional[SourceCategory] = None
    provider: Optional[str] = Field(None, max_length=128)
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    description: Optional[str] = None
    fetch_interval_ms: Optional[int] = Field(None, ge=1, description="Fetch interval in milliseconds (min 1ms)")


class DataSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: SourceCategory
    provider: str
    base_url: Optional[str]
    description: Optional[str]
    fetch_interval_ms: int
    created_at: datetime


# ── Asset ─────────────────────────────────────────────────────────────────────

class AssetCreate(BaseModel):
    source_id: int
    symbol: str = Field(..., max_length=32, examples=["BTC"])
    display_name: Optional[str] = None
    metadata_json: Optional[str] = None


class AssetUpdate(BaseModel):
    symbol: Optional[str] = Field(None, max_length=32)
    display_name: Optional[str] = None
    metadata_json: Optional[str] = None
    is_active: Optional[bool] = None


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    symbol: str
    display_name: Optional[str]
    metadata_json: Optional[str]
    is_active: bool
    created_at: datetime


# ── PriceRecord ───────────────────────────────────────────────────────────────

class PriceRecordCreate(BaseModel):
    asset_id: int
    timestamp: datetime
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    volume: Optional[float] = None
    extra_json: Optional[str] = None


class PriceRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    timestamp: datetime
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: float
    volume: Optional[float]
    extra_json: Optional[str]


# ── Generic wrappers ──────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[Any]
