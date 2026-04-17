"""add recipe tables and dedupe index

Revision ID: 003_add_recipe_tables
Revises: 002_add_fasting_tables
Create Date: 2026-04-17

Context
-------
The recipes tables are currently created by `create_tables()` (SQLAlchemy
`Base.metadata.create_all`) in the app lifespan hook, so on a fresh or
existing production database the tables already exist.  This migration
records them formally in Alembic history so that:

  1. A future switch to pure-alembic (dropping `create_all`) won't lose
     the recipes tables.
  2. The dedupe index `ix_recipes_tenant_source_url` — which is load-bearing
     for Phase 14's per-user URL deduplication — is guaranteed to exist.

Migration safety
----------------
- All DDL uses `IF NOT EXISTS` so running this against a DB where
  `create_all()` already created the tables is idempotent.
- RLS policies are re-applied inside a PL/pgSQL DO block that checks for
  existence first — also idempotent.
- Downgrade: drops only the dedupe index (not the tables — multi-tenant data
  is too risky to drop automatically).

"""
# SPDX-License-Identifier: AGPL-3.0-or-later
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '003_add_recipe_tables'
down_revision = '002_add_fasting_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # recipes
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS recipes (
            id          UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
            tenant_id   UUID        NOT NULL,
            title       VARCHAR(500) NOT NULL,
            description TEXT,
            source_url  VARCHAR(2048),
            image_url   VARCHAR(2048),
            prep_time_minutes  INTEGER,
            cook_time_minutes  INTEGER,
            total_time_minutes INTEGER,
            servings    VARCHAR(100),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # ------------------------------------------------------------------
    # recipe_ingredients
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS recipe_ingredients (
            id         UUID         NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
            tenant_id  UUID         NOT NULL,
            recipe_id  UUID         NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            text       VARCHAR(1000) NOT NULL,
            position   INTEGER      NOT NULL DEFAULT 0
        )
    """))

    # ------------------------------------------------------------------
    # recipe_instructions
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS recipe_instructions (
            id         UUID    NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
            tenant_id  UUID    NOT NULL,
            recipe_id  UUID    NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            text       TEXT    NOT NULL,
            position   INTEGER NOT NULL DEFAULT 0
        )
    """))

    # ------------------------------------------------------------------
    # Indexes
    # ------------------------------------------------------------------

    # tenant_id index on all three tables (mirrors TenantMixin index)
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_recipes_tenant_id
            ON recipes(tenant_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_recipe_ingredients_tenant_id
            ON recipe_ingredients(tenant_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_recipe_instructions_tenant_id
            ON recipe_instructions(tenant_id)
    """))

    # Composite dedupe index — load-bearing for import-url deduplication.
    # O(log n) lookup vs full scan on every import call.
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_recipes_tenant_source_url
            ON recipes(tenant_id, source_url)
    """))

    # ------------------------------------------------------------------
    # RLS policies (idempotent DO block)
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        DO $$
        BEGIN
            -- Enable RLS on recipes
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = 'recipes' AND c.relrowsecurity = TRUE
                  AND n.nspname = 'public'
            ) THEN
                ALTER TABLE recipes ENABLE ROW LEVEL SECURITY;
            END IF;

            -- Enable RLS on recipe_ingredients
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = 'recipe_ingredients' AND c.relrowsecurity = TRUE
                  AND n.nspname = 'public'
            ) THEN
                ALTER TABLE recipe_ingredients ENABLE ROW LEVEL SECURITY;
            END IF;

            -- Enable RLS on recipe_instructions
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = 'recipe_instructions' AND c.relrowsecurity = TRUE
                  AND n.nspname = 'public'
            ) THEN
                ALTER TABLE recipe_instructions ENABLE ROW LEVEL SECURITY;
            END IF;

            -- Policy: tenant_isolation_recipes
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'recipes'
                  AND policyname = 'tenant_isolation_recipes'
            ) THEN
                CREATE POLICY tenant_isolation_recipes ON recipes
                    USING (tenant_id = (current_setting('app.current_tenant_id'))::uuid);
            END IF;

            -- Policy: tenant_isolation_recipe_ingredients
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'recipe_ingredients'
                  AND policyname = 'tenant_isolation_recipe_ingredients'
            ) THEN
                CREATE POLICY tenant_isolation_recipe_ingredients ON recipe_ingredients
                    USING (tenant_id = (current_setting('app.current_tenant_id'))::uuid);
            END IF;

            -- Policy: tenant_isolation_recipe_instructions
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'recipe_instructions'
                  AND policyname = 'tenant_isolation_recipe_instructions'
            ) THEN
                CREATE POLICY tenant_isolation_recipe_instructions ON recipe_instructions
                    USING (tenant_id = (current_setting('app.current_tenant_id'))::uuid);
            END IF;
        END $$;
    """))


def downgrade() -> None:
    # Drop only the dedupe index — not the tables.
    # Multi-tenant recipe data should never be auto-dropped by a downgrade.
    op.execute("DROP INDEX IF EXISTS ix_recipes_tenant_source_url")
