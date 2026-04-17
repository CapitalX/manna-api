# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.fasting.models import FastType, UserFast
from app.fasting.schemas import (
    StartFastRequest,
    UpdateFastRequest,
    UserFastResponse,
    CompletedDaysResponse,
)

router = APIRouter(prefix="/fasts", tags=["fasts"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_user_fast(uf: UserFast) -> UserFastResponse:
    """Convert a UserFast ORM object to a UserFastResponse Pydantic model."""
    today = date.today()
    current_day = (today - uf.start_date).days + 1

    config = uf.config or {}
    eating_window_override = config.get("eating_window_override")
    nutrition_targets_override = config.get("nutrition_targets_override")

    return UserFastResponse(
        id=str(uf.id),
        user_id=str(uf.user_id),
        fast_type_id=uf.fast_type_id,
        status=uf.status,
        start_date=uf.start_date.isoformat(),
        end_date=uf.end_date.isoformat() if uf.end_date else None,
        current_day=current_day,
        custom_duration_days=uf.custom_duration_days,
        eating_window_override=eating_window_override,
        nutrition_targets_override=nutrition_targets_override,
        created_at=uf.created_at.isoformat(),
        updated_at=uf.updated_at.isoformat(),
    )


async def _get_active_fast_or_404(user_id: uuid.UUID, db: AsyncSession) -> UserFast:
    result = await db.execute(
        select(UserFast).where(
            and_(UserFast.user_id == user_id, UserFast.status == "active")
        )
    )
    uf = result.scalar_one_or_none()
    if not uf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active fast")
    return uf


# ---------------------------------------------------------------------------
# GET /fasts/types — public
# ---------------------------------------------------------------------------

@router.get("/types")
async def list_fast_types(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Return all active fast type definitions. No auth required."""
    result = await db.execute(
        select(FastType).where(FastType.is_active == True)  # noqa: E712
    )
    fast_types = result.scalars().all()
    # Return the full rules JSONB (which is the complete FastType definition)
    return [ft.rules for ft in fast_types]


# ---------------------------------------------------------------------------
# POST /fasts/start — auth required
# ---------------------------------------------------------------------------

@router.post("/start", response_model=UserFastResponse, status_code=201)
async def start_fast(
    body: StartFastRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserFastResponse:
    """Create a new fast for the authenticated user."""
    # 1. Verify the fast type exists
    ft_result = await db.execute(
        select(FastType).where(
            and_(FastType.id == body.fast_type_id, FastType.is_active == True)  # noqa: E712
        )
    )
    fast_type = ft_result.scalar_one_or_none()
    if not fast_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fast type '{body.fast_type_id}' not found",
        )

    # 2. Check for existing active fast (409)
    existing_result = await db.execute(
        select(UserFast).where(
            and_(UserFast.user_id == current_user.id, UserFast.status == "active")
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has an active fast",
        )

    # 3. Validate custom_duration_days based on duration type
    rules = fast_type.rules
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

    # 6. Create the UserFast
    user_fast = UserFast(
        id=uuid.uuid4(),
        user_id=current_user.id,
        fast_type_id=body.fast_type_id,
        status="active",
        start_date=start_date,
        end_date=end_date,
        custom_duration_days=body.custom_duration_days,
        config=config,
    )
    db.add(user_fast)
    await db.commit()
    await db.refresh(user_fast)

    return _serialize_user_fast(user_fast)


# ---------------------------------------------------------------------------
# GET /fasts/me — auth required
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserFastResponse)
async def get_active_fast(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserFastResponse:
    """Get the authenticated user's active fast."""
    uf = await _get_active_fast_or_404(current_user.id, db)
    return _serialize_user_fast(uf)


# ---------------------------------------------------------------------------
# PATCH /fasts/me — auth required
# ---------------------------------------------------------------------------

@router.patch("/me", response_model=UserFastResponse)
async def update_active_fast(
    body: UpdateFastRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserFastResponse:
    """Update the authenticated user's active fast configuration."""
    uf = await _get_active_fast_or_404(current_user.id, db)

    config = dict(uf.config or {})

    if body.eating_window_override is not None:
        config["eating_window_override"] = body.eating_window_override.model_dump()
    elif "eating_window_override" in body.model_fields_set:
        # Explicit null clears the override
        config.pop("eating_window_override", None)

    if body.nutrition_targets_override is not None:
        config["nutrition_targets_override"] = body.nutrition_targets_override.model_dump()
    elif "nutrition_targets_override" in body.model_fields_set:
        config.pop("nutrition_targets_override", None)

    uf.config = config
    await db.commit()
    await db.refresh(uf)

    return _serialize_user_fast(uf)


# ---------------------------------------------------------------------------
# POST /fasts/me/complete — auth required
# ---------------------------------------------------------------------------

@router.post("/me/complete", response_model=UserFastResponse)
async def complete_fast(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserFastResponse:
    """Mark the authenticated user's active fast as completed."""
    uf = await _get_active_fast_or_404(current_user.id, db)
    uf.status = "completed"
    await db.commit()
    await db.refresh(uf)
    return _serialize_user_fast(uf)


# ---------------------------------------------------------------------------
# POST /fasts/me/abandon — auth required
# ---------------------------------------------------------------------------

@router.post("/me/abandon", response_model=UserFastResponse)
async def abandon_fast(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserFastResponse:
    """Mark the authenticated user's active fast as abandoned."""
    uf = await _get_active_fast_or_404(current_user.id, db)
    uf.status = "abandoned"
    await db.commit()
    await db.refresh(uf)
    return _serialize_user_fast(uf)


# ---------------------------------------------------------------------------
# GET /fasts/me/completed-days — auth required
# ---------------------------------------------------------------------------

@router.get("/me/completed-days", response_model=CompletedDaysResponse)
async def get_completed_days(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompletedDaysResponse:
    """Return ISO dates where the user has at least one completed fast (for streak calculation)."""
    result = await db.execute(
        select(UserFast).where(
            and_(UserFast.user_id == current_user.id, UserFast.status == "completed")
        )
    )
    completed_fasts = result.scalars().all()

    # Collect unique dates where a completed fast existed (using start_date)
    seen: set[str] = set()
    for uf in completed_fasts:
        seen.add(uf.start_date.isoformat())

    return CompletedDaysResponse(completed_days=sorted(seen))


# ---------------------------------------------------------------------------
# GET /fasts/me/recent — auth required
# ---------------------------------------------------------------------------

@router.get("/me/recent", response_model=list[UserFastResponse])
async def get_recent_fasts(
    limit: int = Query(default=1, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserFastResponse]:
    """Return recent completed or abandoned fasts (for break-fast cards)."""
    result = await db.execute(
        select(UserFast)
        .where(
            and_(
                UserFast.user_id == current_user.id,
                UserFast.status.in_(["completed", "abandoned"]),
            )
        )
        .order_by(UserFast.created_at.desc())
        .limit(limit)
    )
    fasts = result.scalars().all()
    return [_serialize_user_fast(uf) for uf in fasts]
