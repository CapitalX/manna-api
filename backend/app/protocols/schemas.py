# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations
from pydantic import BaseModel


# --- Sub-schemas ---

class EatingWindowOverride(BaseModel):
    start_time: str  # "HH:MM"
    end_time: str    # "HH:MM"


class NutritionTargetsOverride(BaseModel):
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int


# --- Request schemas ---

class StartProtocolConfig(BaseModel):
    fast_type_id: str  # kept as fast_type_id for wire compatibility (mobile still sends this key)
    custom_duration_days: int | None = None
    eating_window_override: EatingWindowOverride | None = None
    nutrition_targets_override: NutritionTargetsOverride | None = None


class UpdateProtocolConfig(BaseModel):
    eating_window_override: EatingWindowOverride | None = None
    nutrition_targets_override: NutritionTargetsOverride | None = None


# --- Response schemas ---

class UserProtocolResponse(BaseModel):
    id: str
    user_id: str
    fast_type_id: str  # kept as fast_type_id for wire compatibility (mobile reads this key)
    status: str
    start_date: str
    end_date: str | None
    current_day: int
    custom_duration_days: int | None
    eating_window_override: EatingWindowOverride | None
    nutrition_targets_override: NutritionTargetsOverride | None
    created_at: str
    updated_at: str


class CompletedDaysResponse(BaseModel):
    completed_days: list[str]

