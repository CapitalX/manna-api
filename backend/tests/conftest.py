# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Shared pytest fixtures for Manna backend tests.

Uses an in-memory SQLite database so tests run without a live PostgreSQL
instance.  Each test gets its own fresh DB (function scope).
"""
import os
import uuid
import asyncio

import pytest

# Point at a SQLite in-memory DB before importing anything that reads config
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest")
os.environ.setdefault("ALLOWED_ORIGINS", "*")

from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from fastapi.testclient import TestClient

# Patch JSONB → JSON for SQLite compatibility (must happen before app import)
import sqlalchemy.dialects.postgresql as _pg

class _JsonB(JSON):
    cache_ok = True
    def __init__(self, *a, **kw):
        kw.pop("astext_type", None)
        kw.pop("none_as_null", None)
        super().__init__(*a, **kw)

_pg.JSONB = _JsonB  # type: ignore[assignment]

from app.database import Base, get_db
from app.main import app
from app.models.user import Tenant, User
from app.fasting.models import FastType, UserFast
from app.auth.service import hash_password, create_access_token
from app.auth.dependencies import get_current_user

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Per-test DB engine + session (function scope)
# ---------------------------------------------------------------------------

@pytest.fixture
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def db_session(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def client(db_session: AsyncSession):
    """
    TestClient with overridden DB dependency.

    get_current_user is NOT overridden here — tests that need an
    authenticated request pass an authed_client fixture instead,
    which also overrides get_current_user.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def authed_client(db_session: AsyncSession):
    """
    Returns (TestClient, user, token) with both get_db and get_current_user
    overridden so tests can make authenticated requests against SQLite.
    """
    # We'll capture the current_user by running the setup coroutine when
    # the fixture is entered — but fixtures are sync, so we store a mutable
    # container that gets filled by the test via `await`.
    from app.auth.dependencies import get_current_user

    state: dict = {}

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return state["user"]

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as c:
        yield c, state
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

ALL_FAST_TYPES_SEEDS = [
    {
        "id": "daniel_fast",
        "name": "Daniel Fast",
        "category": "faith",
        "rules": {
            "id": "daniel_fast",
            "name": "Daniel Fast",
            "category": "faith",
            "description": "Test description",
            "scripture_ref": "Daniel 10:2-3",
            "duration": {"type": "user_configurable", "default_days": 21, "min_days": 1, "max_days": 40},
            "allowed_ingredients": ["fruits", "vegetables"],
            "restricted_ingredients": ["meat", "dairy"],
            "eating_window": {"type": "sunrise_sunset", "fast_hours": None, "eat_hours": None, "start_time": None, "end_time": None},
            "hydration": {"water_allowed": True, "hydration_reminders": True},
            "nutrition_targets": None,
            "devotional_enabled": True,
            "prayer_guide_enabled": True,
            "prep_meals_enabled": True,
            "breakfast_protocol_enabled": False,
            "medical_disclaimer": False,
            "timer_enabled": False,
            "streak_tracking": True,
        },
    },
    {
        "id": "esther_fast",
        "name": "Esther Fast",
        "category": "faith",
        "rules": {
            "id": "esther_fast",
            "name": "Esther Fast",
            "category": "faith",
            "description": "3-day absolute fast",
            "scripture_ref": "Esther 4:16",
            "duration": {"type": "fixed", "default_days": 3, "min_days": 3, "max_days": 3},
            "allowed_ingredients": [],
            "restricted_ingredients": ["water"],
            "eating_window": {"type": "none", "fast_hours": None, "eat_hours": None, "start_time": None, "end_time": None},
            "hydration": {"water_allowed": False, "hydration_reminders": False},
            "nutrition_targets": None,
            "devotional_enabled": True,
            "prayer_guide_enabled": True,
            "prep_meals_enabled": False,
            "breakfast_protocol_enabled": False,
            "medical_disclaimer": True,
            "timer_enabled": True,
            "streak_tracking": False,
        },
    },
    {
        "id": "full_fast",
        "name": "Full Fast",
        "category": "faith",
        "rules": {
            "id": "full_fast", "name": "Full Fast", "category": "faith", "description": "Water only",
            "scripture_ref": "Matthew 4:2", "duration": {"type": "user_configurable", "default_days": 1, "min_days": 1, "max_days": 40},
            "allowed_ingredients": ["water"], "restricted_ingredients": [],
            "eating_window": {"type": "none", "fast_hours": None, "eat_hours": None, "start_time": None, "end_time": None},
            "hydration": {"water_allowed": True, "hydration_reminders": True}, "nutrition_targets": None,
            "devotional_enabled": True, "prayer_guide_enabled": True, "prep_meals_enabled": False,
            "breakfast_protocol_enabled": True, "medical_disclaimer": True, "timer_enabled": True, "streak_tracking": True,
        },
    },
    {
        "id": "partial_fast",
        "name": "Partial Fast",
        "category": "faith",
        "rules": {
            "id": "partial_fast", "name": "Partial Fast", "category": "faith", "description": "Sunrise to sunset",
            "scripture_ref": "Judges 20:26", "duration": {"type": "user_configurable", "default_days": 7, "min_days": 1, "max_days": 40},
            "allowed_ingredients": ["fruits"], "restricted_ingredients": ["alcohol"],
            "eating_window": {"type": "sunrise_sunset", "fast_hours": None, "eat_hours": None, "start_time": None, "end_time": None},
            "hydration": {"water_allowed": True, "hydration_reminders": True}, "nutrition_targets": None,
            "devotional_enabled": True, "prayer_guide_enabled": True, "prep_meals_enabled": True,
            "breakfast_protocol_enabled": False, "medical_disclaimer": False, "timer_enabled": True, "streak_tracking": True,
        },
    },
    {
        "id": "if_16_8",
        "name": "Intermittent Fasting 16:8",
        "category": "intermittent",
        "rules": {
            "id": "if_16_8", "name": "Intermittent Fasting 16:8", "category": "intermittent", "description": "16h fast",
            "scripture_ref": None, "duration": {"type": "ongoing", "default_days": None, "min_days": None, "max_days": None},
            "allowed_ingredients": [], "restricted_ingredients": [],
            "eating_window": {"type": "time_range", "fast_hours": 16, "eat_hours": 8, "start_time": "12:00", "end_time": "20:00"},
            "hydration": {"water_allowed": True, "hydration_reminders": True}, "nutrition_targets": {"calories": 2000, "protein_g": 150, "carbs_g": 200, "fat_g": 70},
            "devotional_enabled": False, "prayer_guide_enabled": False, "prep_meals_enabled": True,
            "breakfast_protocol_enabled": False, "medical_disclaimer": False, "timer_enabled": True, "streak_tracking": True,
        },
    },
    {
        "id": "if_8_16",
        "name": "Intermittent Fasting 8:16",
        "category": "intermittent",
        "rules": {
            "id": "if_8_16", "name": "Intermittent Fasting 8:16", "category": "intermittent", "description": "8h fast",
            "scripture_ref": None, "duration": {"type": "ongoing", "default_days": None, "min_days": None, "max_days": None},
            "allowed_ingredients": [], "restricted_ingredients": [],
            "eating_window": {"type": "time_range", "fast_hours": 8, "eat_hours": 16, "start_time": "22:00", "end_time": "06:00"},
            "hydration": {"water_allowed": True, "hydration_reminders": True}, "nutrition_targets": {"calories": 2200, "protein_g": 160, "carbs_g": 240, "fat_g": 80},
            "devotional_enabled": False, "prayer_guide_enabled": False, "prep_meals_enabled": True,
            "breakfast_protocol_enabled": False, "medical_disclaimer": False, "timer_enabled": True, "streak_tracking": True,
        },
    },
    {
        "id": "if_18_6",
        "name": "Intermittent Fasting 18:6",
        "category": "intermittent",
        "rules": {
            "id": "if_18_6", "name": "Intermittent Fasting 18:6", "category": "intermittent", "description": "18h fast",
            "scripture_ref": None, "duration": {"type": "ongoing", "default_days": None, "min_days": None, "max_days": None},
            "allowed_ingredients": [], "restricted_ingredients": [],
            "eating_window": {"type": "time_range", "fast_hours": 18, "eat_hours": 6, "start_time": "12:00", "end_time": "18:00"},
            "hydration": {"water_allowed": True, "hydration_reminders": True}, "nutrition_targets": {"calories": 1800, "protein_g": 140, "carbs_g": 180, "fat_g": 65},
            "devotional_enabled": False, "prayer_guide_enabled": False, "prep_meals_enabled": True,
            "breakfast_protocol_enabled": False, "medical_disclaimer": False, "timer_enabled": True, "streak_tracking": True,
        },
    },
]


async def create_user_and_token(db: AsyncSession) -> tuple[User, str]:
    """Create a test tenant + user and return (user, jwt_token)."""
    tenant = Tenant(id=uuid.uuid4(), name="Test Tenant")
    db.add(tenant)
    await db.flush()

    user = User(
        id=uuid.uuid4(),
        email=f"test-{uuid.uuid4()}@manna.dev",
        hashed_password=hash_password("password123"),
        tenant_id=tenant.id,
    )
    db.add(user)
    await db.flush()

    token = create_access_token(user.id, tenant.id)
    return user, token


async def seed_recipe(
    db: AsyncSession,
    user,
    url: str = "https://example.com/recipe",
    title: str = "Test Recipe",
) -> None:
    """Insert a recipe row scoped to the given user's tenant."""
    from app.models.recipe import Recipe
    from app.recipes.scraper import normalize_source_url

    recipe = Recipe(
        title=title,
        description=None,
        source_url=normalize_source_url(url),
        image_url=None,
        prep_time_minutes=None,
        cook_time_minutes=None,
        total_time_minutes=None,
        servings=None,
        tenant_id=user.tenant_id,
    )
    db.add(recipe)
    await db.flush()
    return recipe


async def seed_fast_types(db: AsyncSession, seeds: list[dict] | None = None) -> None:
    """Insert fast type records into the test DB."""
    seeds = seeds or ALL_FAST_TYPES_SEEDS
    for seed in seeds:
        ft = FastType(
            id=seed["id"],
            name=seed["name"],
            category=seed["category"],
            rules=seed["rules"],
            is_active=True,
        )
        db.add(ft)
    await db.flush()
