"""SQLAlchemy async engine & session factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency — yields a DB session."""
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Create all tables (dev convenience — use Alembic in production)."""
    from app.models import Base, SourceCategory  # noqa: F811
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Ensure the DB enum contains every Python-side value
    # (handles upgrades when new categories are added)
    for cat in SourceCategory:
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        f"ALTER TYPE sourcecategory ADD VALUE IF NOT EXISTS '{cat.name}'"
                    )
                )
        except Exception:
            pass  # value already exists or fresh DB
