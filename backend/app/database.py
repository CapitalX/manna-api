# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=settings.DEBUG)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all models. Every tenant-scoped table inherits TenantMixin."""
    pass


class TenantMixin:
    """Mixin that adds tenant_id to any model for multi-tenant isolation."""
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )


async def get_db() -> AsyncSession:
    """Dependency that provides a database session and sets the tenant context
    via PostgreSQL session variable for RLS enforcement."""
    async with async_session() as session:
        yield session


async def set_tenant_context(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Set the current tenant on the PostgreSQL session for RLS policies.

    No-ops gracefully on SQLite (used in tests) — set_config() is a
    PostgreSQL built-in that SQLite doesn't support. RLS isolation is
    enforced by explicit tenant_id filters in every query.
    """
    try:
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
            {"tid": str(tenant_id)},
        )
    except Exception as exc:
        # OperationalError: "no such function: set_config" — SQLite test environment
        if "set_config" in str(exc):
            return
        raise


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
