# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from datetime import datetime, date

from sqlalchemy import String, Boolean, DateTime, Date, Integer, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FastType(Base):
    """Pluggable fast type definition. Adding a new fast type is an INSERT, not a code change."""
    __tablename__ = "fast_types"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # "faith" | "intermittent"
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False)  # Full FastType JSON definition
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user_fasts: Mapped[list["UserFast"]] = relationship(back_populates="fast_type")


class UserFast(Base):
    """An active or historical fast instance for a user."""
    __tablename__ = "user_fasts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    fast_type_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("fast_types.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # "active" | "completed" | "abandoned"
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    custom_duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    fast_type: Mapped["FastType"] = relationship(back_populates="user_fasts")
