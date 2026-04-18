"""add structured ingredient columns and recipe_checklist_items

Revision ID: 004_add_structured_ingredient_columns
Revises: 003_add_recipe_tables
Create Date: 2026-04-17

Context
-------
Phase 15: Structured Recipes — Ingredient Parsing, Scoring, and Shopping Checklist.

Adds structured parse columns to recipe_ingredients (quantity, unit, name, category,
confidence, needs_review, raw_text), quality columns to recipes (quality_score,
quality_tier, quality_reasons, last_scored_at, scoring_version, user_verified),
and a new recipe_checklist_items table for per-user per-ingredient check state.

Migration safety
----------------
- All DDL uses ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS — idempotent.
- Backfills raw_text from existing text column within upgrade() so existing rows
  have raw_text populated. Does NOT attempt to parse existing rows — that is done
  by the one-shot backfill script (scripts/backfill_recipe_parsing.py).
- RLS policies applied via idempotent DO block.
- Downgrade drops only the new columns and the new table (does not drop recipes or
  recipe_ingredients themselves).

"""
# SPDX-License-Identifier: AGPL-3.0-or-later
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '004_add_structured_ingredient_columns'
down_revision = '003_add_recipe_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # recipe_ingredients — add structured parse columns
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        ALTER TABLE recipe_ingredients ADD COLUMN IF NOT EXISTS raw_text TEXT
    """))
    conn.execute(sa.text("""
        ALTER TABLE recipe_ingredients ADD COLUMN IF NOT EXISTS quantity NUMERIC(10,3)
    """))
    conn.execute(sa.text("""
        ALTER TABLE recipe_ingredients ADD COLUMN IF NOT EXISTS unit VARCHAR(32)
    """))
    conn.execute(sa.text("""
        ALTER TABLE recipe_ingredients ADD COLUMN IF NOT EXISTS name VARCHAR(500)
    """))
    conn.execute(sa.text("""
        ALTER TABLE recipe_ingredients ADD COLUMN IF NOT EXISTS category VARCHAR(32) DEFAULT 'other'
    """))
    conn.execute(sa.text("""
        ALTER TABLE recipe_ingredients ADD COLUMN IF NOT EXISTS confidence REAL DEFAULT 0.0
    """))
    conn.execute(sa.text("""
        ALTER TABLE recipe_ingredients ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT TRUE
    """))

    # Backfill raw_text from existing text column for all rows that don't have it yet
    conn.execute(sa.text("""
        UPDATE recipe_ingredients SET raw_text = text WHERE raw_text IS NULL
    """))

    # ------------------------------------------------------------------
    # recipes — add quality scoring columns
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        ALTER TABLE recipes ADD COLUMN IF NOT EXISTS quality_score INTEGER DEFAULT 0
    """))
    conn.execute(sa.text("""
        ALTER TABLE recipes ADD COLUMN IF NOT EXISTS quality_tier VARCHAR(16) DEFAULT 'draft'
    """))
    conn.execute(sa.text("""
        ALTER TABLE recipes ADD COLUMN IF NOT EXISTS quality_reasons JSONB DEFAULT '[]'::jsonb
    """))
    conn.execute(sa.text("""
        ALTER TABLE recipes ADD COLUMN IF NOT EXISTS last_scored_at TIMESTAMPTZ
    """))
    conn.execute(sa.text("""
        ALTER TABLE recipes ADD COLUMN IF NOT EXISTS scoring_version INTEGER DEFAULT 1
    """))
    conn.execute(sa.text("""
        ALTER TABLE recipes ADD COLUMN IF NOT EXISTS user_verified BOOLEAN DEFAULT FALSE
    """))

    # ------------------------------------------------------------------
    # recipe_checklist_items — new table for per-user check state
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS recipe_checklist_items (
            id           UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
            tenant_id    UUID        NOT NULL,
            user_id      UUID        NOT NULL,
            recipe_id    UUID        NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            ingredient_id UUID       NOT NULL REFERENCES recipe_ingredients(id) ON DELETE CASCADE,
            checked      BOOLEAN     NOT NULL DEFAULT FALSE,
            checked_at   TIMESTAMPTZ,
            UNIQUE(user_id, recipe_id, ingredient_id)
        )
    """))

    # Indexes
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_recipe_checklist_items_tenant_id
            ON recipe_checklist_items(tenant_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_recipe_checklist_items_recipe_id
            ON recipe_checklist_items(recipe_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_recipe_checklist_items_user_id
            ON recipe_checklist_items(user_id)
    """))

    # ------------------------------------------------------------------
    # RLS policies (idempotent DO block)
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DO $$
        BEGIN
            -- Enable RLS on recipe_checklist_items
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = 'recipe_checklist_items' AND c.relrowsecurity = TRUE
                  AND n.nspname = 'public'
            ) THEN
                ALTER TABLE recipe_checklist_items ENABLE ROW LEVEL SECURITY;
            END IF;

            -- Policy: tenant_isolation_recipe_checklist_items
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'recipe_checklist_items'
                  AND policyname = 'tenant_isolation_recipe_checklist_items'
            ) THEN
                CREATE POLICY tenant_isolation_recipe_checklist_items ON recipe_checklist_items
                    USING (tenant_id = (current_setting('app.current_tenant_id'))::uuid);
            END IF;
        END $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # Drop the new table
    conn.execute(sa.text("DROP TABLE IF EXISTS recipe_checklist_items"))

    # Drop new columns from recipes
    conn.execute(sa.text("ALTER TABLE recipes DROP COLUMN IF EXISTS user_verified"))
    conn.execute(sa.text("ALTER TABLE recipes DROP COLUMN IF EXISTS scoring_version"))
    conn.execute(sa.text("ALTER TABLE recipes DROP COLUMN IF EXISTS last_scored_at"))
    conn.execute(sa.text("ALTER TABLE recipes DROP COLUMN IF EXISTS quality_reasons"))
    conn.execute(sa.text("ALTER TABLE recipes DROP COLUMN IF EXISTS quality_tier"))
    conn.execute(sa.text("ALTER TABLE recipes DROP COLUMN IF EXISTS quality_score"))

    # Drop new columns from recipe_ingredients
    conn.execute(sa.text("ALTER TABLE recipe_ingredients DROP COLUMN IF EXISTS needs_review"))
    conn.execute(sa.text("ALTER TABLE recipe_ingredients DROP COLUMN IF EXISTS confidence"))
    conn.execute(sa.text("ALTER TABLE recipe_ingredients DROP COLUMN IF EXISTS category"))
    conn.execute(sa.text("ALTER TABLE recipe_ingredients DROP COLUMN IF EXISTS name"))
    conn.execute(sa.text("ALTER TABLE recipe_ingredients DROP COLUMN IF EXISTS unit"))
    conn.execute(sa.text("ALTER TABLE recipe_ingredients DROP COLUMN IF EXISTS quantity"))
    conn.execute(sa.text("ALTER TABLE recipe_ingredients DROP COLUMN IF EXISTS raw_text"))
