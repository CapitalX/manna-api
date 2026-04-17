"""add fasting tables

Revision ID: 002_add_fasting_tables
Revises:
Create Date: 2026-04-17

"""
# SPDX-License-Identifier: AGPL-3.0-or-later
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import json

# revision identifiers, used by Alembic.
revision = '002_add_fasting_tables'
down_revision = None
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Fast type seed data (translated from lib/fasting/constants.ts)
# ---------------------------------------------------------------------------

FAST_TYPES_SEED = [
    {
        "id": "daniel_fast",
        "name": "Daniel Fast",
        "category": "faith",
        "rules": {
            "id": "daniel_fast",
            "name": "Daniel Fast",
            "category": "faith",
            "description": "A 21-day partial fast based on Daniel 10:2-3, consisting of fruits, vegetables, whole grains, and water while abstaining from meat, dairy, sugar, and caffeine.",
            "scripture_ref": "Daniel 10:2-3",
            "duration": {"type": "user_configurable", "default_days": 21, "min_days": 1, "max_days": 40},
            "allowed_ingredients": ["fruits", "vegetables", "whole_grains", "nuts_seeds", "legumes", "oils", "herbs_spices", "water"],
            "restricted_ingredients": ["meat", "dairy", "refined_sugar", "leavened_bread", "caffeine", "alcohol"],
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
            "description": "A 3-day absolute fast (no food or water) based on Esther 4:16. This is a serious commitment requiring medical awareness.",
            "scripture_ref": "Esther 4:16",
            "duration": {"type": "fixed", "default_days": 3, "min_days": 3, "max_days": 3},
            "allowed_ingredients": [],
            "restricted_ingredients": ["meat", "dairy", "refined_sugar", "leavened_bread", "caffeine", "alcohol", "fruits", "vegetables", "whole_grains", "nuts_seeds", "legumes", "oils", "water"],
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
            "id": "full_fast",
            "name": "Full Fast",
            "category": "faith",
            "description": "A water-only fast with no food intake. Water is permitted to maintain hydration.",
            "scripture_ref": "Matthew 4:2",
            "duration": {"type": "user_configurable", "default_days": 1, "min_days": 1, "max_days": 40},
            "allowed_ingredients": ["water"],
            "restricted_ingredients": ["meat", "dairy", "refined_sugar", "leavened_bread", "caffeine", "alcohol", "fruits", "vegetables", "whole_grains", "nuts_seeds", "legumes", "oils"],
            "eating_window": {"type": "none", "fast_hours": None, "eat_hours": None, "start_time": None, "end_time": None},
            "hydration": {"water_allowed": True, "hydration_reminders": True},
            "nutrition_targets": None,
            "devotional_enabled": True,
            "prayer_guide_enabled": True,
            "prep_meals_enabled": False,
            "breakfast_protocol_enabled": True,
            "medical_disclaimer": True,
            "timer_enabled": True,
            "streak_tracking": True,
        },
    },
    {
        "id": "partial_fast",
        "name": "Partial Fast",
        "category": "faith",
        "rules": {
            "id": "partial_fast",
            "name": "Partial Fast",
            "category": "faith",
            "description": "A fast where eating is restricted to certain hours of the day, typically from sunrise to sunset.",
            "scripture_ref": "Judges 20:26",
            "duration": {"type": "user_configurable", "default_days": 7, "min_days": 1, "max_days": 40},
            "allowed_ingredients": ["fruits", "vegetables", "whole_grains", "nuts_seeds", "legumes", "oils", "herbs_spices", "water", "meat", "dairy"],
            "restricted_ingredients": ["alcohol"],
            "eating_window": {"type": "sunrise_sunset", "fast_hours": None, "eat_hours": None, "start_time": None, "end_time": None},
            "hydration": {"water_allowed": True, "hydration_reminders": True},
            "nutrition_targets": None,
            "devotional_enabled": True,
            "prayer_guide_enabled": True,
            "prep_meals_enabled": True,
            "breakfast_protocol_enabled": False,
            "medical_disclaimer": False,
            "timer_enabled": True,
            "streak_tracking": True,
        },
    },
    {
        "id": "if_16_8",
        "name": "Intermittent Fasting 16:8",
        "category": "intermittent",
        "rules": {
            "id": "if_16_8",
            "name": "Intermittent Fasting 16:8",
            "category": "intermittent",
            "description": "Fast for 16 hours and eat within an 8-hour window. A popular and sustainable approach to intermittent fasting.",
            "scripture_ref": None,
            "duration": {"type": "ongoing", "default_days": None, "min_days": None, "max_days": None},
            "allowed_ingredients": [],
            "restricted_ingredients": [],
            "eating_window": {"type": "time_range", "fast_hours": 16, "eat_hours": 8, "start_time": "12:00", "end_time": "20:00"},
            "hydration": {"water_allowed": True, "hydration_reminders": True},
            "nutrition_targets": {"calories": 2000, "protein_g": 150, "carbs_g": 200, "fat_g": 70},
            "devotional_enabled": False,
            "prayer_guide_enabled": False,
            "prep_meals_enabled": True,
            "breakfast_protocol_enabled": False,
            "medical_disclaimer": False,
            "timer_enabled": True,
            "streak_tracking": True,
        },
    },
    {
        "id": "if_8_16",
        "name": "Intermittent Fasting 8:16",
        "category": "intermittent",
        "rules": {
            "id": "if_8_16",
            "name": "Intermittent Fasting 8:16",
            "category": "intermittent",
            "description": "A gentle fast with an 8-hour fasting window and a 16-hour eating window, ideal for beginners or overnight fasting.",
            "scripture_ref": None,
            "duration": {"type": "ongoing", "default_days": None, "min_days": None, "max_days": None},
            "allowed_ingredients": [],
            "restricted_ingredients": [],
            "eating_window": {"type": "time_range", "fast_hours": 8, "eat_hours": 16, "start_time": "22:00", "end_time": "06:00"},
            "hydration": {"water_allowed": True, "hydration_reminders": True},
            "nutrition_targets": {"calories": 2200, "protein_g": 160, "carbs_g": 240, "fat_g": 80},
            "devotional_enabled": False,
            "prayer_guide_enabled": False,
            "prep_meals_enabled": True,
            "breakfast_protocol_enabled": False,
            "medical_disclaimer": False,
            "timer_enabled": True,
            "streak_tracking": True,
        },
    },
    {
        "id": "if_18_6",
        "name": "Intermittent Fasting 18:6",
        "category": "intermittent",
        "rules": {
            "id": "if_18_6",
            "name": "Intermittent Fasting 18:6",
            "category": "intermittent",
            "description": "An advanced fast with an 18-hour fasting window and a 6-hour eating window for experienced fasters.",
            "scripture_ref": None,
            "duration": {"type": "ongoing", "default_days": None, "min_days": None, "max_days": None},
            "allowed_ingredients": [],
            "restricted_ingredients": [],
            "eating_window": {"type": "time_range", "fast_hours": 18, "eat_hours": 6, "start_time": "12:00", "end_time": "18:00"},
            "hydration": {"water_allowed": True, "hydration_reminders": True},
            "nutrition_targets": {"calories": 1800, "protein_g": 140, "carbs_g": 180, "fat_g": 65},
            "devotional_enabled": False,
            "prayer_guide_enabled": False,
            "prep_meals_enabled": True,
            "breakfast_protocol_enabled": False,
            "medical_disclaimer": False,
            "timer_enabled": True,
            "streak_tracking": True,
        },
    },
]


def upgrade() -> None:
    # Create fast_types table
    op.create_table(
        "fast_types",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("rules", postgresql.JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # Create user_fasts table
    op.create_table(
        "user_fasts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "fast_type_id",
            sa.String(50),
            sa.ForeignKey("fast_types.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("custom_duration_days", sa.Integer, nullable=True),
        sa.Column(
            "config",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # Partial unique index: only one active fast per user.
    # Postgres doesn't support partial UNIQUE constraints (only partial unique
    # *indexes*), so this single index enforces the rule.
    op.create_index(
        "idx_user_fasts_user_active",
        "user_fasts",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    # Seed all 7 fast types
    fast_types_table = sa.table(
        "fast_types",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("rules", postgresql.JSONB),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        fast_types_table,
        [
            {
                "id": ft["id"],
                "name": ft["name"],
                "category": ft["category"],
                "rules": ft["rules"],
                "is_active": True,
            }
            for ft in FAST_TYPES_SEED
        ],
    )


def downgrade() -> None:
    op.drop_index("idx_user_fasts_user_active", table_name="user_fasts")
    op.drop_table("user_fasts")
    op.drop_table("fast_types")
