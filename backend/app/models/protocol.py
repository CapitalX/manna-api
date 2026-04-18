# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user_protocol import UserProtocol


class Protocol(Base):
    """Pluggable protocol definition. Adding a new protocol is an INSERT, not a code change."""
    __tablename__ = "protocols"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # "faith" | "intermittent" | "diet"
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False)  # Full Protocol JSON definition
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    axes: Mapped[str] = mapped_column(String(16), nullable=False, default="combined")
    recipe_focused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user_protocols: Mapped[list["UserProtocol"]] = relationship(back_populates="protocol")
