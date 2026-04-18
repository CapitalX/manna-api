# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.protocol import Protocol
from app.models.user_protocol import UserProtocol
from app.protocols.schemas import (
    StartProtocolConfig,
    UpdateProtocolConfig,
    UserProtocolResponse,
    CompletedDaysResponse,
)

router = APIRouter(prefix="/protocols", tags=["protocols"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_user_protocol(up: UserProtocol) -> UserProtocolResponse:
    """Convert a UserProtocol ORM object to a UserProtocolResponse Pydantic model."""
    today = date.today()
    current_day = (today - up.start_date).days + 1

    config = up.config or {}
    eating_window_override = config.get("eating_window_override")
    nutrition_targets_override = config.get("nutrition_targets_override")

    return UserProtocolResponse(
        id=str(up.id),
        user_id=str(up.user_id),
        fast_type_id=up.protocol_id,  # wire compat: mobile reads fast_type_id
        status=up.status,
        start_date=up.start_date.isoformat(),
        end_date=up.end_date.isoformat() if up.end_date else None,
        current_day=current_day,
        custom_duration_days=up.custom_duration_days,
        eating_window_override=eating_window_override,
        nutrition_targets_override=nutrition_targets_override,
        created_at=up.created_at.isoformat(),
        updated_at=up.updated_at.isoformat(),
    )


async def _get_active_protocol_or_404(user_id: uuid.UUID, db: AsyncSession) -> UserProtocol:
    result = await db.execute(
        select(UserProtocol).where(
            and_(UserProtocol.user_id == user_id, UserProtocol.status == "active")
        )
    )
    up = result.scalar_one_or_none()
    if not up:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active fast")
    return up


# ---------------------------------------------------------------------------
# GET /protocols/types — public
# ---------------------------------------------------------------------------

@router.get("/types")
async def get_protocols(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Return all active protocol definitions. No auth required."""
    result = await db.execute(
        select(Protocol).where(Protocol.is_active == True)  # noqa: E712
    )
    protocols = result.scalars().all()
    # Return the full rules JSONB (which is the complete Protocol definition)
    return [p.rules for p in protocols]


# ---------------------------------------------------------------------------
# POST /protocols/start — auth required
# ---------------------------------------------------------------------------

@router.post("/start", response_model=UserProtocolResponse, status_code=201)
async def start_protocol(
    body: StartProtocolConfig,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProtocolResponse:
    """Create a new protocol for the authenticated user."""
    # 1. Verify the protocol exists
    pt_result = await db.execute(
        select(Protocol).where(
            and_(Protocol.id == body.fast_type_id, Protocol.is_active == True)  # noqa: E712
        )
    )
    protocol = pt_result.scalar_one_or_none()
    if not protocol:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fast type '{body.fast_type_id}' not found",
        )

    # 2. Check for existing active protocol (409)
    existing_result = await db.execute(
        select(UserProtocol).where(
            and_(UserProtocol.user_id == current_user.id, UserProtocol.status == "active")
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has an active fast",
        )

    # 3. Validate custom_duration_days based on duration type
    rules = protocol.rules
    duration_type = rules.get("duration", {}).get("type")
    min_days = rules.get("duration", {}).get("min_days")
    max_days = rules.get("duration", {}).get("max_days")

    if duration_type == "fixed" and body.custom_duration_days is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="custom_duration_days cannot be set for fixed-duration fasts",
        )
    if duration_type == "user_configurable" and body.custom_duration_days is not None:
        if min_days is not None and body.custom_duration_days < min_days:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"custom_duration_days must be at least {min_days}",
            )
        if max_days is not None and body.custom_duration_days > max_days:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"custom_duration_days must be at most {max_days}",
            )

    # 4. Compute start/end dates
    start_date = date.today()
    end_date: date | None = None

    if duration_type == "fixed":
        default_days = rules.get("duration", {}).get("default_days") or 1
        end_date = start_date + timedelta(days=default_days)
    elif duration_type == "user_configurable":
        duration_days = body.custom_duration_days or (rules.get("duration", {}).get("default_days") or 1)
        end_date = start_date + timedelta(days=duration_days)
    # ongoing: end_date stays None

    # 5. Build config JSONB (overrides only)
    config: dict = {}
    if body.eating_window_override:
        config["eating_window_override"] = body.eating_window_override.model_dump()
    if body.nutrition_targets_override:
        config["nutrition_targets_override"] = body.nutrition_targets_override.model_dump()

    # 6. Create the UserProtocol
    user_protocol = UserProtocol(
        id=uuid.uuid4(),
        user_id=current_user.id,
        protocol_id=body.fast_type_id,  # wire compat: request body still uses fast_type_id
        status="active",
        start_date=start_date,
        end_date=end_date,
        custom_duration_days=body.custom_duration_days,
        config=config,
    )
    db.add(user_protocol)
    await db.commit()
    await db.refresh(user_protocol)

    return _serialize_user_protocol(user_protocol)


# ---------------------------------------------------------------------------
# GET /protocols/me — auth required
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserProtocolResponse)
async def get_active_protocol(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProtocolResponse:
    """Get the authenticated user's active protocol."""
    up = await _get_active_protocol_or_404(current_user.id, db)
    return _serialize_user_protocol(up)


# ---------------------------------------------------------------------------
# PATCH /protocols/me — auth required
# ---------------------------------------------------------------------------

@router.patch("/me", response_model=UserProtocolResponse)
async def update_active_protocol(
    body: UpdateProtocolConfig,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProtocolResponse:
    """Update the authenticated user's active protocol configuration."""
    up = await _get_active_protocol_or_404(current_user.id, db)

    config = dict(up.config or {})

    if body.eating_window_override is not None:
        config["eating_window_override"] = body.eating_window_override.model_dump()
    elif "eating_window_override" in body.model_fields_set:
        # Explicit null clears the override
        config.pop("eating_window_override", None)

    if body.nutrition_targets_override is not None:
        config["nutrition_targets_override"] = body.nutrition_targets_override.model_dump()
    elif "nutrition_targets_override" in body.model_fields_set:
        config.pop("nutrition_targets_override", None)

    up.config = config
    await db.commit()
    await db.refresh(up)

    return _serialize_user_protocol(up)


# ---------------------------------------------------------------------------
# POST /protocols/me/complete — auth required
# ---------------------------------------------------------------------------

@router.post("/me/complete", response_model=UserProtocolResponse)
async def complete_protocol(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProtocolResponse:
    """Mark the authenticated user's active protocol as completed."""
    up = await _get_active_protocol_or_404(current_user.id, db)
    up.status = "completed"
    await db.commit()
    await db.refresh(up)
    return _serialize_user_protocol(up)


# ---------------------------------------------------------------------------
# POST /protocols/me/abandon — auth required
# ---------------------------------------------------------------------------

@router.post("/me/abandon", response_model=UserProtocolResponse)
async def abandon_protocol(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProtocolResponse:
    """Mark the authenticated user's active protocol as abandoned."""
    up = await _get_active_protocol_or_404(current_user.id, db)
    up.status = "abandoned"
    await db.commit()
    await db.refresh(up)
    return _serialize_user_protocol(up)


# ---------------------------------------------------------------------------
# GET /protocols/me/completed-days — auth required
# ---------------------------------------------------------------------------

@router.get("/me/completed-days", response_model=CompletedDaysResponse)
async def get_completed_days(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompletedDaysResponse:
    """Return ISO dates where the user has at least one completed protocol (for streak calculation)."""
    result = await db.execute(
        select(UserProtocol).where(
            and_(UserProtocol.user_id == current_user.id, UserProtocol.status == "completed")
        )
    )
    completed_protocols = result.scalars().all()

    # Collect unique dates where a completed protocol existed (using start_date)
    seen: set[str] = set()
    for up in completed_protocols:
        seen.add(up.start_date.isoformat())

    return CompletedDaysResponse(completed_days=sorted(seen))


# ---------------------------------------------------------------------------
# GET /protocols/me/recent — auth required
# ---------------------------------------------------------------------------

@router.get("/me/recent", response_model=list[UserProtocolResponse])
async def get_recent_protocols(
    limit: int = Query(default=1, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserProtocolResponse]:
    """Return recent completed or abandoned protocols (for break-fast cards)."""
    result = await db.execute(
        select(UserProtocol)
        .where(
            and_(
                UserProtocol.user_id == current_user.id,
                UserProtocol.status.in_(["completed", "abandoned"]),
            )
        )
        .order_by(UserProtocol.created_at.desc())
        .limit(limit)
    )
    protocols = result.scalars().all()
    return [_serialize_user_protocol(up) for up in protocols]
