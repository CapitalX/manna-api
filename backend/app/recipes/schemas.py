# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from pydantic import BaseModel, HttpUrl


class IngredientOut(BaseModel):
    id: uuid.UUID
    text: str
    position: int
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
    model_config = {"from_attributes": True}


class ScrapeRequest(BaseModel):
    url: HttpUrl
