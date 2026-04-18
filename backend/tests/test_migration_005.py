# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Migration 005 tests — TDD first.

Tests verify that migration 005_rename_fasts_to_protocols correctly:
  1. Renames fast_types → protocols and user_fasts → user_protocols
  2. Adds axes (VARCHAR(16)) and recipe_focused (BOOLEAN) columns to protocols
  3. Seeds three new rows: mediterranean, vegetarian, none
  4. Backfills existing rows with correct axes/recipe_focused values

These tests REQUIRE a live PostgreSQL connection because they probe
information_schema and use PostgreSQL-specific DDL (RENAME TABLE, DO $$ ... $$).
They will be skipped automatically if no PostgreSQL test URL is configured.

Set POSTGRES_TEST_URL to a writable PostgreSQL database to run these tests:
    export POSTGRES_TEST_URL="postgresql://user:pass@host:port/db"

The test creates its own tables (simulating migration 002–004 state) so it
does not depend on the production database being at exactly revision 004.
"""
import json
import os
import pytest

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")
pg_required = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="POSTGRES_TEST_URL not set — PostgreSQL migration tests skipped",
)


# ---------------------------------------------------------------------------
# Fixture: fresh PostgreSQL schema (simulates post-004 state)
# ---------------------------------------------------------------------------

@pytest.fixture
def pg_conn():
    """
    Synchronous psycopg2 connection to a test PostgreSQL database.

    Yields the connection (autocommit=False).  The fixture rolls back and
    closes after each test so each test starts clean.
    """
    psycopg2 = pytest.importorskip("psycopg2")
    conn = psycopg2.connect(POSTGRES_TEST_URL)
    conn.autocommit = False
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def pg_schema_004(pg_conn):
    """
    Sets up a minimal schema that mirrors the post-004 state so migration 005
    can be applied cleanly in an isolated transaction:

      - fast_types table (matches 002 definition)
      - user_fasts table with fast_type_id FK
      - 7 seeded rows in fast_types (to verify backfill and conflict handling)

    Uses a unique schema per test run to avoid conflicts between parallel runs.
    All objects are dropped after the test via pg_conn.rollback().
    """
    cur = pg_conn.cursor()

    # fast_types — matches migration 002
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fast_types (
            id          VARCHAR(50)  PRIMARY KEY,
            name        VARCHAR(100) NOT NULL,
            category    VARCHAR(20)  NOT NULL,
            rules       JSONB        NOT NULL,
            is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)

    # Seed existing 7 fast types (subset rules — just enough for FK/ID checks)
    existing_ids = [
        ("daniel_fast",  "Daniel Fast",               "faith",       "combined"),
        ("esther_fast",  "Esther Fast",               "faith",       "combined"),
        ("full_fast",    "Full Fast",                 "faith",       "combined"),
        ("partial_fast", "Partial Fast",              "faith",       "combined"),
        ("if_16_8",      "Intermittent Fasting 16:8", "intermittent","schedule_only"),
        ("if_18_6",      "Intermittent Fasting 18:6", "intermittent","schedule_only"),
        ("if_8_16",      "Intermittent Fasting 8:16", "intermittent","schedule_only"),
    ]
    for ft_id, ft_name, ft_cat, _expected_axes in existing_ids:
        cur.execute(
            """
            INSERT INTO fast_types (id, name, category, rules, is_active)
            VALUES (%s, %s, %s, %s, TRUE)
            ON CONFLICT (id) DO NOTHING
            """,
            (ft_id, ft_name, ft_cat, json.dumps({"id": ft_id})),
        )

    # user_fasts — matches migration 002 definition
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_fasts (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID        NOT NULL,
            fast_type_id    VARCHAR(50) NOT NULL REFERENCES fast_types(id),
            status          VARCHAR(20) NOT NULL DEFAULT 'active',
            start_date      DATE        NOT NULL DEFAULT CURRENT_DATE,
            end_date        DATE,
            custom_duration_days INTEGER,
            config          JSONB       NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    pg_conn.commit()
    yield pg_conn

    # Cleanup — drop tables in dependency order
    cur.execute("DROP TABLE IF EXISTS user_protocols CASCADE")
    cur.execute("DROP TABLE IF EXISTS user_fasts CASCADE")
    cur.execute("DROP TABLE IF EXISTS protocols CASCADE")
    cur.execute("DROP TABLE IF EXISTS fast_types CASCADE")
    pg_conn.commit()
    cur.close()


def _load_migration_005_module():
    """Load and return the migration 005 module."""
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "migration_005",
        pathlib.Path(__file__).parent.parent
        / "alembic/versions/005_rename_fasts_to_protocols.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_migration_005(conn) -> None:
    """
    Execute the DDL from migration 005 using a raw psycopg2 connection.

    Imports the migration module and calls upgrade() after wiring the
    Alembic op context to the given connection.
    """
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        mod = _load_migration_005_module()
        mod.upgrade()


def _run_downgrade_005(conn) -> None:
    """
    Execute downgrade() from migration 005 using a raw psycopg2 connection.
    """
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        mod = _load_migration_005_module()
        mod.downgrade()


# ---------------------------------------------------------------------------
# Test 0 — Migration file exists with correct metadata (runs without PG)
# ---------------------------------------------------------------------------

def test_migration_file_exists_and_has_correct_revision():
    """Migration 005 file exists, has the right revision ID and down_revision."""
    import importlib.util
    import pathlib

    migration_path = (
        pathlib.Path(__file__).parent.parent
        / "alembic/versions/005_rename_fasts_to_protocols.py"
    )
    assert migration_path.exists(), (
        f"Migration file not found at {migration_path}. "
        "Create backend/alembic/versions/005_rename_fasts_to_protocols.py"
    )

    spec = importlib.util.spec_from_file_location("migration_005", migration_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.revision == "005_rename_fasts_to_protocols", (
        f"revision must be '005_rename_fasts_to_protocols', got {mod.revision!r}"
    )
    assert mod.down_revision == "004_structured_ingredients", (
        f"down_revision must be '004_structured_ingredients', got {mod.down_revision!r}"
    )
    assert callable(mod.upgrade), "upgrade() function must exist"
    assert callable(mod.downgrade), "downgrade() function must exist"


# ---------------------------------------------------------------------------
# Test 1 — Tables renamed
# ---------------------------------------------------------------------------

@pg_required
def test_tables_renamed(pg_schema_004):
    """After 005, information_schema shows protocols + user_protocols; not fast_types / user_fasts."""
    conn = pg_schema_004
    _run_migration_005(conn)

    cur = conn.cursor()
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name IN ('protocols', 'user_protocols', 'fast_types', 'user_fasts')
        ORDER BY table_name
    """)
    table_names = {row[0] for row in cur.fetchall()}

    assert "protocols" in table_names, "protocols table must exist after migration"
    assert "user_protocols" in table_names, "user_protocols table must exist after migration"
    assert "fast_types" not in table_names, "fast_types must be renamed away"
    assert "user_fasts" not in table_names, "user_fasts must be renamed away"


# ---------------------------------------------------------------------------
# Test 2 — New columns exist on protocols
# ---------------------------------------------------------------------------

@pg_required
def test_new_columns_exist(pg_schema_004):
    """After 005, protocols table has axes (varchar) and recipe_focused (boolean) columns."""
    conn = pg_schema_004
    _run_migration_005(conn)

    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'protocols'
          AND column_name IN ('axes', 'recipe_focused')
        ORDER BY column_name
    """)
    cols = {row[0]: row[1] for row in cur.fetchall()}

    assert "axes" in cols, "axes column must exist on protocols"
    assert "recipe_focused" in cols, "recipe_focused column must exist on protocols"
    assert cols["axes"] in ("character varying", "varchar"), (
        f"axes should be varchar, got {cols['axes']}"
    )
    assert cols["recipe_focused"] == "boolean", (
        f"recipe_focused should be boolean, got {cols['recipe_focused']}"
    )


# ---------------------------------------------------------------------------
# Test 3 — Three new rows seeded
# ---------------------------------------------------------------------------

@pg_required
def test_new_rows_seeded(pg_schema_004):
    """After 005, protocols table contains mediterranean, vegetarian, and none rows."""
    conn = pg_schema_004
    _run_migration_005(conn)

    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, category, axes, recipe_focused
        FROM protocols
        WHERE id IN ('mediterranean', 'vegetarian', 'none')
        ORDER BY id
    """)
    rows = {row[0]: row for row in cur.fetchall()}

    assert "mediterranean" in rows, "mediterranean row must be seeded"
    assert "vegetarian" in rows, "vegetarian row must be seeded"
    assert "none" in rows, "none row must be seeded"

    med = rows["mediterranean"]
    assert med[2] == "diet", f"mediterranean category should be 'diet', got {med[2]}"
    assert med[3] == "diet_only", f"mediterranean axes should be 'diet_only', got {med[3]}"
    assert med[4] is True, "mediterranean recipe_focused should be TRUE"

    veg = rows["vegetarian"]
    assert veg[2] == "diet", f"vegetarian category should be 'diet', got {veg[2]}"
    assert veg[3] == "diet_only", f"vegetarian axes should be 'diet_only', got {veg[3]}"
    assert veg[4] is True, "vegetarian recipe_focused should be TRUE"

    none_row = rows["none"]
    assert none_row[2] == "diet", f"none category should be 'diet', got {none_row[2]}"
    assert none_row[3] == "diet_only", f"none axes should be 'diet_only', got {none_row[3]}"
    assert none_row[4] is True, "none recipe_focused should be TRUE"


# ---------------------------------------------------------------------------
# Test 4 — Backfill correct for existing rows
# ---------------------------------------------------------------------------

@pg_required
def test_backfill_correct(pg_schema_004):
    """After 005, existing rows have correct axes + recipe_focused values."""
    conn = pg_schema_004
    _run_migration_005(conn)

    cur = conn.cursor()
    cur.execute("""
        SELECT id, axes, recipe_focused
        FROM protocols
        WHERE id IN (
            'daniel_fast','esther_fast','full_fast','partial_fast',
            'if_16_8','if_18_6','if_8_16'
        )
        ORDER BY id
    """)
    rows = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

    # Faith fasts → combined, recipe_focused=False
    for faith_id in ("daniel_fast", "esther_fast", "full_fast", "partial_fast"):
        axes, rf = rows[faith_id]
        assert axes == "combined", f"{faith_id} axes should be 'combined', got {axes}"
        assert rf is False, f"{faith_id} recipe_focused should be FALSE"

    # IF fasts → schedule_only, recipe_focused=False
    for if_id in ("if_16_8", "if_18_6", "if_8_16"):
        axes, rf = rows[if_id]
        assert axes == "schedule_only", f"{if_id} axes should be 'schedule_only', got {axes}"
        assert rf is False, f"{if_id} recipe_focused should be FALSE"


# ---------------------------------------------------------------------------
# Test 5 — Downgrade reverses the upgrade cleanly
# ---------------------------------------------------------------------------

@pg_required
def test_downgrade_reverses_upgrade(pg_schema_004):
    """
    After upgrade() + downgrade(), the schema must be back to post-004 state:

    - fast_types and user_fasts exist
    - protocols and user_protocols do NOT exist
    - axes and recipe_focused columns are gone from fast_types
    - The three seeded diet rows (mediterranean, vegetarian, none) are gone
    - The RLS policy tenant_isolation_user_fasts exists on user_fasts
      (verifies C1: the downgrade policy rename targets user_protocols, not user_fasts)

    A user_protocols row referencing 'mediterranean' is inserted before downgrade
    to exercise the FK-safe DELETE path from I2.
    """
    conn = pg_schema_004
    cur = conn.cursor()

    # Step 1: apply upgrade
    _run_migration_005(conn)

    # Step 2: create an RLS policy on user_protocols (so the rename-back in
    # downgrade is meaningful and the C1 fix is exercised)
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename  = 'user_protocols'
                  AND policyname = 'tenant_isolation_user_protocols'
            ) THEN
                -- Enable RLS and create the policy so the RENAME in downgrade has
                -- something real to act on.
                ALTER TABLE user_protocols ENABLE ROW LEVEL SECURITY;
                CREATE POLICY tenant_isolation_user_protocols
                    ON user_protocols
                    USING (true);
            END IF;
        END $$;
    """)
    conn.commit()

    # Step 3: insert a user_protocols row referencing 'mediterranean' to exercise
    # the FK-safe delete path (I2 fix) — without it the seed DELETE would FK-fail
    cur.execute("""
        INSERT INTO user_protocols (user_id, protocol_id, status, start_date, config)
        VALUES (gen_random_uuid(), 'mediterranean', 'active', CURRENT_DATE, '{}')
    """)
    conn.commit()

    # Step 4: run downgrade — must not raise
    _run_downgrade_005(conn)
    conn.commit()

    # Step 5: assert tables reverted
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name IN ('fast_types', 'user_fasts', 'protocols', 'user_protocols')
        ORDER BY table_name
    """)
    table_names = {row[0] for row in cur.fetchall()}

    assert "fast_types" in table_names, "fast_types must exist after downgrade"
    assert "user_fasts" in table_names, "user_fasts must exist after downgrade"
    assert "protocols" not in table_names, "protocols must be renamed away by downgrade"
    assert "user_protocols" not in table_names, "user_protocols must be renamed away by downgrade"

    # Step 6: axes and recipe_focused must be gone from fast_types
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'fast_types'
          AND column_name IN ('axes', 'recipe_focused')
    """)
    leftover_cols = {row[0] for row in cur.fetchall()}
    assert "axes" not in leftover_cols, "axes column must be dropped by downgrade"
    assert "recipe_focused" not in leftover_cols, "recipe_focused column must be dropped by downgrade"

    # Step 7: the three seeded diet rows must not appear in fast_types
    cur.execute("""
        SELECT id FROM fast_types
        WHERE id IN ('mediterranean', 'vegetarian', 'none')
    """)
    leftover_seeds = {row[0] for row in cur.fetchall()}
    assert not leftover_seeds, (
        f"Seeded diet rows must be deleted by downgrade; found: {leftover_seeds}"
    )

    # Step 8: RLS policy tenant_isolation_user_fasts must exist on user_fasts
    # (verifies C1 — the rename was issued ON user_protocols, not ON user_fasts)
    cur.execute("""
        SELECT policyname
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'user_fasts'
          AND policyname = 'tenant_isolation_user_fasts'
    """)
    policy_row = cur.fetchone()
    assert policy_row is not None, (
        "RLS policy 'tenant_isolation_user_fasts' must exist on user_fasts after downgrade. "
        "If missing, the downgrade policy rename was issued on the wrong table (C1 bug)."
    )
