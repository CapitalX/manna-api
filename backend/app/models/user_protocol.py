# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from datetime import datetime, date
from typing import TYPE_CHECKING

from sqlalchemy import String, Boolean, DateTime, Date, Integer, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.protocol import Protocol


class UserProtocol(Base):
    """An active or historical protocol instance for a user."""
    __tablename__ = "user_protocols"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    protocol_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("protocols.id"), nullable=False
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

    protocol: Mapped["Protocol"] = relationship(back_populates="user_protocols")
