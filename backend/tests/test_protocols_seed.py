# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Seed-integrity tests for all 10 Protocol rows.

Verifies that every protocol seeded (7 original + 3 new from migration 005)
has the correct shape: valid axes, boolean recipe_focused, ongoing duration
for diet protocols, and wildcard allowed_ingredients for 'none'.

Uses SQLite in-memory DB + AsyncSession fixture (same pattern as the other
test suites).  Does NOT require a live PostgreSQL connection.
"""
import json

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.protocol import Protocol

pytestmark = pytest.mark.asyncio

# All 10 protocol IDs (7 original faith/intermittent + 3 new diet)
ALL_SEED_IDS = [
    "daniel_fast",
    "esther_fast",
    "full_fast",
    "partial_fast",
    "if_16_8",
    "if_18_6",
    "if_8_16",
    "mediterranean",
    "vegetarian",
    "none",
]

# Seed data for the 3 new diet protocols (not in ALL_FAST_TYPES_SEEDS)
DIET_PROTOCOL_SEEDS = [
    {
        "id": "mediterranean",
        "name": "Mediterranean",
        "category": "diet",
        "axes": "diet_only",
        "recipe_focused": True,
        "rules": {
            "id": "mediterranean",
            "name": "Mediterranean",
            "category": "diet",
            "description": "Whole foods, plants, fish, and olive oil — no timing constraint.",
            "scripture_ref": None,
            "duration": {"type": "ongoing", "default_days": None},
            "allowed_ingredients": [
                "vegetables", "fruits", "whole_grains", "legumes", "nuts_seeds",
                "oils", "fish", "poultry", "herbs_spices", "dairy",
            ],
            "restricted_ingredients": ["refined_sugar", "refined_grains", "processed_meat"],
            "eating_window": {"type": "none"},
            "hydration": {"water_allowed": True, "hydration_reminders": True},
            "nutrition_targets": None,
            "devotional_enabled": False,
            "prayer_guide_enabled": False,
            "prep_meals_enabled": False,
            "breakfast_protocol_enabled": False,
            "medical_disclaimer": False,
            "timer_enabled": False,
            "streak_tracking": True,
        },
    },
    {
        "id": "vegetarian",
        "name": "Vegetarian",
        "category": "diet",
        "axes": "diet_only",
        "recipe_focused": True,
        "rules": {
            "id": "vegetarian",
            "name": "Vegetarian",
            "category": "diet",
            "description": "Plant-based with dairy and eggs; no meat, poultry, or fish.",
            "scripture_ref": None,
            "duration": {"type": "ongoing", "default_days": None},
            "allowed_ingredients": [
                "vegetables", "fruits", "whole_grains", "legumes", "nuts_seeds",
                "oils", "dairy", "eggs", "herbs_spices",
            ],
            "restricted_ingredients": ["meat", "poultry", "fish", "seafood"],
            "eating_window": {"type": "none"},
            "hydration": {"water_allowed": True, "hydration_reminders": False},
            "nutrition_targets": None,
            "devotional_enabled": False,
            "prayer_guide_enabled": False,
            "prep_meals_enabled": False,
            "breakfast_protocol_enabled": False,
            "medical_disclaimer": False,
            "timer_enabled": False,
            "streak_tracking": True,
        },
    },
    {
        "id": "none",
        "name": "None (freestyle)",
        "category": "diet",
        "axes": "diet_only",
        "recipe_focused": True,
        "rules": {
            "id": "none",
            "name": "None (freestyle)",
            "category": "diet",
            "description": "No guardrails. Save recipes, cook anything.",
            "scripture_ref": None,
            "duration": {"type": "ongoing", "default_days": None},
            "allowed_ingredients": ["*"],
            "restricted_ingredients": [],
            "eating_window": {"type": "none"},
            "hydration": {"water_allowed": True, "hydration_reminders": False},
            "nutrition_targets": None,
            "devotional_enabled": False,
            "prayer_guide_enabled": False,
            "prep_meals_enabled": False,
            "breakfast_protocol_enabled": False,
            "medical_disclaimer": False,
            "timer_enabled": False,
            "streak_tracking": False,
        },
    },
]

VALID_AXES = {"combined", "schedule_only", "diet_only"}


async def _seed_all_protocols(db: AsyncSession) -> None:
    """Seed all 10 protocols (7 from conftest helpers + 3 new diet rows)."""
    from tests.conftest import seed_fast_types

    # Seed the original 7 (axes/recipe_focused get ORM defaults: "combined" / False)
    await seed_fast_types(db)

    # Seed the 3 new diet protocols with explicit axes + recipe_focused
    for seed in DIET_PROTOCOL_SEEDS:
        protocol = Protocol(
            id=seed["id"],
            name=seed["name"],
            category=seed["category"],
            rules=seed["rules"],
            is_active=True,
            axes=seed["axes"],
            recipe_focused=seed["recipe_focused"],
        )
        db.add(protocol)
    await db.flush()


def _parse_rules(raw) -> dict:
    """Return rules as a dict regardless of whether the DB returned str or dict."""
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Test 1 — All 10 rows are seeded (integer count check)
# ---------------------------------------------------------------------------

async def test_all_10_protocols_seeded(db_session: AsyncSession):
    """All 10 protocols exist in the DB after seeding."""
    await _seed_all_protocols(db_session)

    result = await db_session.execute(
        select(func.count(Protocol.id)).where(Protocol.id.in_(ALL_SEED_IDS))
    )
    count = result.scalar_one()
    assert count == 10, f"Expected 10 seeded protocols, got {count}"


# ---------------------------------------------------------------------------
# Test 2 — Every protocol has a valid axes value
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("protocol_id", ALL_SEED_IDS)
async def test_protocol_has_valid_axes(protocol_id: str, db_session: AsyncSession):
    """Every protocol has axes in ('combined', 'schedule_only', 'diet_only')."""
    await _seed_all_protocols(db_session)

    result = await db_session.execute(
        select(Protocol.axes).where(Protocol.id == protocol_id)
    )
    axes = result.scalar_one()
    assert axes in VALID_AXES, (
        f"Protocol '{protocol_id}' has invalid axes '{axes}'; expected one of {VALID_AXES}"
    )


# ---------------------------------------------------------------------------
# Test 3 — Every protocol has a boolean recipe_focused value (not null)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("protocol_id", ALL_SEED_IDS)
async def test_protocol_has_boolean_recipe_focused(protocol_id: str, db_session: AsyncSession):
    """Every protocol has recipe_focused as a non-null boolean-compatible value."""
    await _seed_all_protocols(db_session)

    result = await db_session.execute(
        select(Protocol.recipe_focused).where(Protocol.id == protocol_id)
    )
    recipe_focused = result.scalar_one()
    # SQLite returns int (0/1) for BOOLEAN columns; PostgreSQL returns bool.
    # We assert it's non-null and boolean-coercible (0, 1, True, False all pass).
    assert recipe_focused is not None, (
        f"Protocol '{protocol_id}' recipe_focused must not be null"
    )
    assert recipe_focused in (True, False, 0, 1), (
        f"Protocol '{protocol_id}' recipe_focused={recipe_focused!r} is not a boolean value"
    )


# ---------------------------------------------------------------------------
# Test 4 — mediterranean / vegetarian / none have duration.type == 'ongoing'
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("protocol_id", ["mediterranean", "vegetarian", "none"])
async def test_diet_protocols_have_ongoing_duration(protocol_id: str, db_session: AsyncSession):
    """mediterranean, vegetarian, and none protocols all have duration.type == 'ongoing'."""
    await _seed_all_protocols(db_session)

    result = await db_session.execute(
        select(Protocol.rules).where(Protocol.id == protocol_id)
    )
    rules = _parse_rules(result.scalar_one())
    duration_type = rules.get("duration", {}).get("type")
    assert duration_type == "ongoing", (
        f"Protocol '{protocol_id}' duration.type should be 'ongoing', got {duration_type!r}"
    )


# ---------------------------------------------------------------------------
# Test 5 — none has allowed_ingredients == ['*']
# ---------------------------------------------------------------------------

async def test_none_protocol_has_wildcard_ingredients(db_session: AsyncSession):
    """The 'none' protocol has allowed_ingredients == ['*']."""
    await _seed_all_protocols(db_session)

    result = await db_session.execute(
        select(Protocol.rules).where(Protocol.id == "none")
    )
    rules = _parse_rules(result.scalar_one())
    allowed = rules.get("allowed_ingredients")
    assert allowed == ["*"], (
        f"Protocol 'none' allowed_ingredients should be ['*'], got {allowed!r}"
    )
