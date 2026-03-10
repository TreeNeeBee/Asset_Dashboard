"""ORM models — single source of truth for the database schema.

Tables
------
* ``data_sources``   – registry of pluggable data sources (BTC, stock, FX …)
* ``assets``         – individual tracked assets (BTC-USD, AAPL, EUR/CNY …)
* ``price_records``  – time-series price / value snapshots
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Shared declarative base."""


# ---------------------------------------------------------------------------
# Data-source categories
# ---------------------------------------------------------------------------

class SourceCategory(str, enum.Enum):
    CRYPTO = "crypto"
    STOCK = "stock"
    FX = "fx"
    ASHARE = "ashare"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# DataSource — pluggable provider registry
# ---------------------------------------------------------------------------

class DataSource(Base):
    __tablename__ = "data_sources"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    name: str = Column(String(64), unique=True, nullable=False, comment="Human-readable name")
    category: SourceCategory = Column(Enum(SourceCategory), nullable=False)
    provider: str = Column(String(128), nullable=False, comment="Python dotted path or built-in key")
    base_url: str = Column(String(512), nullable=True)
    api_key: str = Column(String(256), nullable=True)
    description: str = Column(Text, nullable=True)
    fetch_interval_ms: int = Column(Integer, default=300000, nullable=False, comment="Fetch interval in milliseconds (min 1)")
    created_at: datetime = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    assets = relationship("Asset", back_populates="source", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<DataSource id={self.id} name={self.name!r} category={self.category}>"


# ---------------------------------------------------------------------------
# Asset — an item tracked by a data source
# ---------------------------------------------------------------------------

class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("source_id", "symbol", name="uq_source_symbol"),)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    source_id: int = Column(Integer, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    symbol: str = Column(String(32), nullable=False, comment="Ticker / pair symbol, e.g. BTC, AAPL, EUR/CNY")
    display_name: str = Column(String(128), nullable=True)
    metadata_json: str = Column(Text, nullable=True, comment="Arbitrary JSON blob for extra info")
    is_active: bool = Column(Integer, default=1, comment="Soft-delete flag (1=active)")
    created_at: datetime = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    source = relationship("DataSource", back_populates="assets")
    records = relationship("PriceRecord", back_populates="asset", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Asset id={self.id} symbol={self.symbol!r}>"


# ---------------------------------------------------------------------------
# PriceRecord — time-series data points
# ---------------------------------------------------------------------------

class PriceRecord(Base):
    __tablename__ = "price_records"
    __table_args__ = (
        UniqueConstraint("asset_id", "timestamp", name="uq_price_asset_ts"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    asset_id: int = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    timestamp: datetime = Column(DateTime(timezone=True), nullable=False, index=True)
    open: float = Column(Float, nullable=True)
    high: float = Column(Float, nullable=True)
    low: float = Column(Float, nullable=True)
    close: float = Column(Float, nullable=False)
    volume: float = Column(Float, nullable=True)
    extra_json: str = Column(Text, nullable=True, comment="Provider-specific extra fields")

    asset = relationship("Asset", back_populates="records")

    def __repr__(self) -> str:
        return f"<PriceRecord asset_id={self.asset_id} ts={self.timestamp} close={self.close}>"
