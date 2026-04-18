# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, HttpUrl


class IngredientOut(BaseModel):
    id: uuid.UUID
    text: str
    position: int
    # --- Phase 15: Structured parse fields (all optional for backwards compat) ---
    raw_text: str | None = None
    quantity: float | None = None
    unit: str | None = None
    name: str | None = None
    category: str = "other"
    confidence: float = 0.0
    needs_review: bool = True
    model_config = {"from_attributes": True}


class InstructionOut(BaseModel):
    id: uuid.UUID
    text: str
    position: int
    model_config = {"from_attributes": True}


class RecipeCreate(BaseModel):
    title: str
    description: str | None = None
    source_url: str | None = None
    image_url: str | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    total_time_minutes: int | None = None
    servings: str | None = None
    ingredients: list[str] = []
    instructions: list[str] = []


class RecipeOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    source_url: str | None
    image_url: str | None
    prep_time_minutes: int | None
    cook_time_minutes: int | None
    total_time_minutes: int | None
    servings: str | None
    ingredients: list[IngredientOut]
    instructions: list[InstructionOut]
    # --- Phase 15: Quality scoring fields (optional for backwards compat) ---
    quality_score: int = 0
    quality_tier: Literal["draft", "needs_info", "processable", "verified"] = "draft"
    quality_reasons: list[str] = []
    user_verified: bool = False
    model_config = {"from_attributes": True}


class ScrapeRequest(BaseModel):
    url: HttpUrl


class ImportUrlRequest(BaseModel):
    url: HttpUrl


class ImportUrlResponse(BaseModel):
    recipe: RecipeOut
    already_exists: bool


# --- Phase 15: New schemas ---

class IngredientUpdate(BaseModel):
    """Partial update for a single ingredient's structured fields."""
    quantity: float | None = None
    unit: str | None = None
    name: str | None = None
    category: str | None = None
    needs_review: bool | None = None


class ChecklistItemOut(BaseModel):
    ingredient_id: uuid.UUID
    checked: bool
    checked_at: datetime | None = None
    model_config = {"from_attributes": True}


class ChecklistToggleRequest(BaseModel):
    checked: bool
