-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Migration 001: Enable Row Level Security for multi-tenant isolation
-- Every tenant-scoped table gets an RLS policy that restricts reads and writes
-- to rows matching the current session's app.current_tenant_id setting.

-- ============================================================
-- USERS
-- ============================================================
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_users ON users
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- ============================================================
-- RECIPES
-- ============================================================
ALTER TABLE recipes ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipes FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_recipes ON recipes
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- ============================================================
-- RECIPE_INGREDIENTS
-- ============================================================
ALTER TABLE recipe_ingredients ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipe_ingredients FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_recipe_ingredients ON recipe_ingredients
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- ============================================================
-- RECIPE_INSTRUCTIONS
-- ============================================================
ALTER TABLE recipe_instructions ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipe_instructions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_recipe_instructions ON recipe_instructions
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- ============================================================
-- Grant the application role access (the app connects as 'manna')
-- The superuser/migration user bypasses RLS by default.
-- The app user must NOT be a superuser for RLS to take effect.
-- ============================================================
-- Run as superuser:
-- CREATE ROLE manna_app LOGIN PASSWORD 'manna_dev';
-- GRANT ALL ON ALL TABLES IN SCHEMA public TO manna_app;
-- GRANT USAGE ON SCHEMA public TO manna_app;
