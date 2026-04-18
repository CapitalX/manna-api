"""rename fast_types/user_fasts to protocols/user_protocols; add axes + recipe_focused; seed 3 new protocols

Revision ID: 005_rename_fasts_to_protocols
Revises: 004_structured_ingredients
Create Date: 2026-04-17

Context
-------
Phase 16: Scope pivot — "fasts" become "protocols." The table rename is purely
cosmetic at the DB level; the FK structure and all existing data are preserved.

Three new non-fast protocols are seeded: mediterranean, vegetarian, and none
(freestyle). Two new columns (axes, recipe_focused) are added to support the
home-screen data-driven rendering introduced in Phase 16.

Migration safety
----------------
- All RENAME operations are wrapped in a DO $$ ... IF EXISTS ... END $$ block
  so the migration is re-runnable without error.
- ADD COLUMN uses IF NOT EXISTS throughout.
- INSERT uses ON CONFLICT (id) DO NOTHING for idempotent seed inserts.
- RLS policy + index renames are wrapped in a defensive EXCEPTION block so
  reruns don't fail when the rename has already been applied.
- downgrade() reverses every change in reverse order.

Production notes
----------------
- The Dockerfile runs `alembic upgrade head` before uvicorn starts.
  This migration will run on the first deploy after the code lands.
- Existing user_fasts rows (production has none at time of writing) would be
  preserved — the rename does not truncate.
"""
# SPDX-License-Identifier: AGPL-3.0-or-later
import json

from alembic import op
import sqlalchemy as sa

revision = '005_rename_fasts_to_protocols'
down_revision = '004_structured_ingredients'
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Seed data for three new protocols
# ---------------------------------------------------------------------------

MEDITERRANEAN_RULES = {
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
}

VEGETARIAN_RULES = {
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
    "streak_tracking": False,
}

NONE_RULES = {
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
}


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Rename fast_types → protocols (idempotent)
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'fast_types'
            ) THEN
                ALTER TABLE fast_types RENAME TO protocols;
            END IF;
        END $$;
    """))

    # ------------------------------------------------------------------
    # 2. Rename user_fasts → user_protocols (idempotent)
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'user_fasts'
            ) THEN
                ALTER TABLE user_fasts RENAME TO user_protocols;
            END IF;
        END $$;
    """))

    # ------------------------------------------------------------------
    # 3. Rename fast_type_id → protocol_id on user_protocols (idempotent)
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'user_protocols'
                  AND column_name = 'fast_type_id'
            ) THEN
                ALTER TABLE user_protocols RENAME COLUMN fast_type_id TO protocol_id;
            END IF;
        END $$;
    """))

    # ------------------------------------------------------------------
    # 4. Add axes column to protocols
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        ALTER TABLE protocols
            ADD COLUMN IF NOT EXISTS axes VARCHAR(16) NOT NULL DEFAULT 'combined'
    """))

    # ------------------------------------------------------------------
    # 5. Add recipe_focused column to protocols
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        ALTER TABLE protocols
            ADD COLUMN IF NOT EXISTS recipe_focused BOOLEAN NOT NULL DEFAULT FALSE
    """))

    # ------------------------------------------------------------------
    # 6. Backfill faith fasts → axes='combined', recipe_focused=FALSE
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE protocols
        SET axes = 'combined', recipe_focused = FALSE
        WHERE id IN ('daniel_fast', 'esther_fast', 'full_fast', 'partial_fast')
    """))

    # ------------------------------------------------------------------
    # 7. Backfill IF fasts → axes='schedule_only', recipe_focused=FALSE
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE protocols
        SET axes = 'schedule_only', recipe_focused = FALSE
        WHERE id IN ('if_16_8', 'if_18_6', 'if_8_16')
    """))

    # ------------------------------------------------------------------
    # 8. Seed three new diet protocols
    # ------------------------------------------------------------------
    new_protocols = [
        ("mediterranean", "Mediterranean",    "diet", MEDITERRANEAN_RULES, True,  "diet_only", True),
        ("vegetarian",    "Vegetarian",        "diet", VEGETARIAN_RULES,    True,  "diet_only", True),
        ("none",          "None (freestyle)",  "diet", NONE_RULES,          True,  "diet_only", True),
    ]

    for proto_id, proto_name, category, rules, is_active, axes, recipe_focused in new_protocols:
        conn.execute(sa.text("""
            INSERT INTO protocols (id, name, category, rules, is_active, axes, recipe_focused)
            VALUES (:id, :name, :category, CAST(:rules AS JSONB), :is_active, :axes, :recipe_focused)
            ON CONFLICT (id) DO NOTHING
        """), {
            "id": proto_id,
            "name": proto_name,
            "category": category,
            "rules": json.dumps(rules),
            "is_active": is_active,
            "axes": axes,
            "recipe_focused": recipe_focused,
        })

    # ------------------------------------------------------------------
    # 9. Rename RLS policies + indexes (defensive — ignore if already done)
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DO $$
        BEGIN
            -- Rename RLS policy on user_protocols
            ALTER POLICY tenant_isolation_user_fasts ON user_protocols
                RENAME TO tenant_isolation_user_protocols;
        EXCEPTION WHEN OTHERS THEN
            NULL;  -- policy already renamed or doesn't exist
        END $$;
    """))

    conn.execute(sa.text("""
        DO $$
        BEGIN
            ALTER INDEX IF EXISTS ix_user_fasts_user_id
                RENAME TO ix_user_protocols_user_id;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """))

    conn.execute(sa.text("""
        DO $$
        BEGIN
            ALTER INDEX IF EXISTS idx_user_fasts_user_active
                RENAME TO idx_user_protocols_user_active;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # Reverse index / policy renames (defensive)
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DO $$
        BEGIN
            ALTER INDEX IF EXISTS idx_user_protocols_user_active
                RENAME TO idx_user_fasts_user_active;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$;
    """))

    conn.execute(sa.text("""
        DO $$
        BEGIN
            ALTER INDEX IF EXISTS ix_user_protocols_user_id
                RENAME TO ix_user_fasts_user_id;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$;
    """))

    conn.execute(sa.text("""
        DO $$
        BEGIN
            ALTER POLICY tenant_isolation_user_protocols ON user_fasts
                RENAME TO tenant_isolation_user_fasts;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$;
    """))

    # ------------------------------------------------------------------
    # Delete the three new diet protocol rows
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DELETE FROM protocols WHERE id IN ('mediterranean', 'vegetarian', 'none')
    """))

    # ------------------------------------------------------------------
    # Drop the new columns
    # ------------------------------------------------------------------
    conn.execute(sa.text("ALTER TABLE protocols DROP COLUMN IF EXISTS recipe_focused"))
    conn.execute(sa.text("ALTER TABLE protocols DROP COLUMN IF EXISTS axes"))

    # ------------------------------------------------------------------
    # Rename protocol_id → fast_type_id on user_protocols (idempotent)
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'user_protocols'
                  AND column_name = 'protocol_id'
            ) THEN
                ALTER TABLE user_protocols RENAME COLUMN protocol_id TO fast_type_id;
            END IF;
        END $$;
    """))

    # ------------------------------------------------------------------
    # Rename user_protocols → user_fasts (idempotent)
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'user_protocols'
            ) THEN
                ALTER TABLE user_protocols RENAME TO user_fasts;
            END IF;
        END $$;
    """))

    # ------------------------------------------------------------------
    # Rename protocols → fast_types (idempotent)
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'protocols'
            ) THEN
                ALTER TABLE protocols RENAME TO fast_types;
            END IF;
        END $$;
    """))
