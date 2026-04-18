# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db, set_tenant_context
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.recipe import Recipe, RecipeIngredient, RecipeInstruction, RecipeChecklistItem
from sqlalchemy import desc
from app.recipes.schemas import (
    RecipeCreate, RecipeOut, ScrapeRequest, ImportUrlRequest, ImportUrlResponse,
    IngredientUpdate, ChecklistItemOut, ChecklistToggleRequest,
)
from app.recipes.scraper import scrape_recipe_url, normalize_source_url
from app.recipes.parser import parse_line
from app.recipes.categorizer import categorize
from app.recipes.scoring import score_recipe

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _apply_parse_and_score(recipe: Recipe, db_ingredient: RecipeIngredient, raw_text: str) -> None:
    """Parse a raw ingredient line and set structured fields on the ingredient model."""
    parsed = parse_line(raw_text)
    cat, _cat_conf = categorize(parsed.name or raw_text)
    db_ingredient.raw_text = raw_text
    db_ingredient.quantity = parsed.quantity
    db_ingredient.unit = parsed.unit
    db_ingredient.name = parsed.name
    db_ingredient.category = cat
    db_ingredient.confidence = parsed.confidence
    db_ingredient.needs_review = parsed.needs_review


def _apply_score_to_recipe(recipe: Recipe, ingredient_list=None) -> None:
    """Run scorer and persist results on the recipe model (caller commits).

    Args:
        recipe: The Recipe model instance.
        ingredient_list: Optional explicit list of ingredients to score against.
            When provided, bypasses the recipe.ingredients relationship access
            (avoids lazy-load issues during flush before commit).
            When None, uses recipe.ingredients (must already be loaded).
    """

    class _RecipeProxy:
        """Thin proxy so score_recipe() can read ingredients without touching ORM lazy loads."""
        def __init__(self, r, ings):
            self.servings = r.servings
            self.user_verified = r.user_verified
            self.ingredients = ings

    proxy = _RecipeProxy(recipe, ingredient_list if ingredient_list is not None else recipe.ingredients)
    result = score_recipe(proxy)
    recipe.quality_score = result.score
    recipe.quality_tier = result.tier
    recipe.quality_reasons = result.reasons
    recipe.last_scored_at = datetime.now(timezone.utc)


@router.get("/", response_model=list[RecipeOut])
async def list_recipes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await set_tenant_context(db, current_user.tenant_id)
    result = await db.execute(
        select(Recipe)
        .where(Recipe.tenant_id == current_user.tenant_id)
        .options(selectinload(Recipe.ingredients), selectinload(Recipe.instructions))
        .order_by(desc(Recipe.created_at))
    )
    return result.scalars().all()


@router.post("/", response_model=RecipeOut, status_code=201)
async def create_recipe(
    body: RecipeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await set_tenant_context(db, current_user.tenant_id)
    recipe = Recipe(
        title=body.title,
        description=body.description,
        source_url=body.source_url,
        image_url=body.image_url,
        prep_time_minutes=body.prep_time_minutes,
        cook_time_minutes=body.cook_time_minutes,
        total_time_minutes=body.total_time_minutes,
        servings=body.servings,
        tenant_id=current_user.tenant_id,
    )
    db.add(recipe)
    await db.flush()

    for i, text in enumerate(body.ingredients):
        db.add(RecipeIngredient(
            recipe_id=recipe.id, text=text, position=i, tenant_id=current_user.tenant_id
        ))
    for i, text in enumerate(body.instructions):
        db.add(RecipeInstruction(
            recipe_id=recipe.id, text=text, position=i, tenant_id=current_user.tenant_id
        ))

    await db.commit()
    await db.refresh(recipe, ["ingredients", "instructions"])
    return recipe


@router.post("/import-url", response_model=ImportUrlResponse, status_code=201)
async def import_recipe_from_url(
    body: ImportUrlRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Import a recipe from a public URL.

    - Normalizes the URL (strips tracking params, lowercases host, strips fragment).
    - Checks for an existing recipe with the same normalized URL for this tenant.
    - If found: returns 200 with `already_exists: true` — no re-scrape.
    - If not found: scrapes, persists, returns 201 with `already_exists: false`.
    - Sparse scrapes (zero ingredients/instructions) are persisted — partial data
      beats a confusing 422.
    - httpx.TimeoutException → 504 (upstream site too slow).
    - Any other scraper exception → 422 (unreadable / blocked site).
    """
    await set_tenant_context(db, current_user.tenant_id)

    normalized_url = normalize_source_url(str(body.url))

    # --- Dedupe check ---
    existing_result = await db.execute(
        select(Recipe)
        .where(
            Recipe.tenant_id == current_user.tenant_id,
            Recipe.source_url == normalized_url,
        )
        .options(selectinload(Recipe.ingredients), selectinload(Recipe.instructions))
        .limit(1)
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        response.status_code = status.HTTP_200_OK
        return ImportUrlResponse(recipe=RecipeOut.model_validate(existing), already_exists=True)

    # --- Scrape ---
    try:
        scraped = await scrape_recipe_url(str(body.url))
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Source site didn't respond in time.",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Couldn't read that recipe. Try a different URL.",
        )

    # --- Persist (using normalized URL as source_url) ---
    recipe = Recipe(
        title=scraped.title,
        description=scraped.description,
        source_url=normalized_url,
        image_url=scraped.image_url,
        prep_time_minutes=scraped.prep_time_minutes,
        cook_time_minutes=scraped.cook_time_minutes,
        total_time_minutes=scraped.total_time_minutes,
        servings=scraped.servings,
        tenant_id=current_user.tenant_id,
    )
    db.add(recipe)
    await db.flush()

    ingredients: list[RecipeIngredient] = []
    for i, text in enumerate(scraped.ingredients):
        ing = RecipeIngredient(
            recipe_id=recipe.id, text=text, position=i, tenant_id=current_user.tenant_id
        )
        _apply_parse_and_score(recipe, ing, text)
        db.add(ing)
        ingredients.append(ing)

    for i, text in enumerate(scraped.instructions):
        db.add(RecipeInstruction(
            recipe_id=recipe.id, text=text, position=i, tenant_id=current_user.tenant_id
        ))

    # Flush so IDs are assigned to ingredients
    await db.flush()

    # Score using the in-memory list (avoids touching the mapped relationship
    # attribute before the session is committed, which would trigger a lazy load)
    _apply_score_to_recipe(recipe, ingredient_list=ingredients)

    await db.commit()
    await db.refresh(recipe, ["ingredients", "instructions"])

    return ImportUrlResponse(recipe=RecipeOut.model_validate(recipe), already_exists=False)


# DEPRECATED: use /import-url instead. Kept for backwards compatibility.
@router.post("/scrape", response_model=RecipeOut, status_code=201)
async def scrape_and_save(
    body: ScrapeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        scraped = await scrape_recipe_url(str(body.url))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not scrape recipe from the provided URL",
        )

    create_body = RecipeCreate(
        title=scraped.title,
        description=scraped.description,
        source_url=scraped.source_url,
        image_url=scraped.image_url,
        prep_time_minutes=scraped.prep_time_minutes,
        cook_time_minutes=scraped.cook_time_minutes,
        total_time_minutes=scraped.total_time_minutes,
        servings=scraped.servings,
        ingredients=scraped.ingredients,
        instructions=scraped.instructions,
    )
    return await create_recipe(create_body, current_user, db)


@router.get("/{recipe_id}", response_model=RecipeOut)
async def get_recipe(
    recipe_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await set_tenant_context(db, current_user.tenant_id)
    result = await db.execute(
        select(Recipe)
        .where(Recipe.id == recipe_id, Recipe.tenant_id == current_user.tenant_id)
        .options(selectinload(Recipe.ingredients), selectinload(Recipe.instructions))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.delete("/{recipe_id}", status_code=204)
async def delete_recipe(
    recipe_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await set_tenant_context(db, current_user.tenant_id)
    result = await db.execute(
        select(Recipe).where(
            Recipe.id == recipe_id, Recipe.tenant_id == current_user.tenant_id
        )
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    await db.delete(recipe)
    await db.commit()


# ---------------------------------------------------------------------------
# Phase 15: Ingredient edit + checklist endpoints
# ---------------------------------------------------------------------------

@router.patch("/{recipe_id}/ingredients/{ingredient_id}", response_model=RecipeOut)
async def update_ingredient(
    recipe_id: uuid.UUID,
    ingredient_id: uuid.UUID,
    body: IngredientUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update structured fields on a single ingredient and re-score the recipe."""
    await set_tenant_context(db, current_user.tenant_id)

    # Fetch the recipe (with ingredients for scoring)
    recipe_result = await db.execute(
        select(Recipe)
        .where(Recipe.id == recipe_id, Recipe.tenant_id == current_user.tenant_id)
        .options(selectinload(Recipe.ingredients), selectinload(Recipe.instructions))
    )
    recipe = recipe_result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Fetch the ingredient
    ing_result = await db.execute(
        select(RecipeIngredient).where(
            RecipeIngredient.id == ingredient_id,
            RecipeIngredient.recipe_id == recipe_id,
            RecipeIngredient.tenant_id == current_user.tenant_id,
        )
    )
    ing = ing_result.scalar_one_or_none()
    if not ing:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    # Apply updates
    if body.quantity is not None:
        ing.quantity = body.quantity
    if body.unit is not None:
        ing.unit = body.unit
    if body.name is not None:
        ing.name = body.name
    if body.category is not None:
        ing.category = body.category
    if body.needs_review is not None:
        ing.needs_review = body.needs_review

    # Re-score
    _apply_score_to_recipe(recipe)

    await db.commit()
    await db.refresh(recipe, ["ingredients", "instructions"])
    return recipe


@router.post("/{recipe_id}/verify", response_model=RecipeOut)
async def verify_recipe(
    recipe_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a recipe as user-verified. Re-scores to potentially promote to 'verified' tier."""
    await set_tenant_context(db, current_user.tenant_id)

    result = await db.execute(
        select(Recipe)
        .where(Recipe.id == recipe_id, Recipe.tenant_id == current_user.tenant_id)
        .options(selectinload(Recipe.ingredients), selectinload(Recipe.instructions))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    recipe.user_verified = True
    _apply_score_to_recipe(recipe)

    await db.commit()
    await db.refresh(recipe, ["ingredients", "instructions"])
    return recipe


@router.get("/{recipe_id}/checklist", response_model=list[ChecklistItemOut])
async def get_checklist(
    recipe_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return checklist items for the current user and recipe.

    Lazily creates one row per ingredient on the first fetch.
    """
    await set_tenant_context(db, current_user.tenant_id)

    # Verify recipe exists and belongs to this tenant
    recipe_result = await db.execute(
        select(Recipe)
        .where(Recipe.id == recipe_id, Recipe.tenant_id == current_user.tenant_id)
        .options(selectinload(Recipe.ingredients))
    )
    recipe = recipe_result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Fetch existing checklist items for this user
    existing_result = await db.execute(
        select(RecipeChecklistItem).where(
            RecipeChecklistItem.recipe_id == recipe_id,
            RecipeChecklistItem.user_id == current_user.id,
        )
    )
    existing = {item.ingredient_id: item for item in existing_result.scalars().all()}

    # Lazy create missing rows
    created_any = False
    for ing in recipe.ingredients:
        if ing.id not in existing:
            item = RecipeChecklistItem(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                recipe_id=recipe_id,
                ingredient_id=ing.id,
                checked=False,
                checked_at=None,
            )
            db.add(item)
            existing[ing.id] = item
            created_any = True

    if created_any:
        await db.commit()
        # Re-fetch after commit so IDs are populated
        existing_result = await db.execute(
            select(RecipeChecklistItem).where(
                RecipeChecklistItem.recipe_id == recipe_id,
                RecipeChecklistItem.user_id == current_user.id,
            )
        )
        items = existing_result.scalars().all()
    else:
        items = list(existing.values())

    return items


@router.patch("/{recipe_id}/checklist/{ingredient_id}", response_model=ChecklistItemOut)
async def toggle_checklist_item(
    recipe_id: uuid.UUID,
    ingredient_id: uuid.UUID,
    body: ChecklistToggleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set checked state on a checklist item. Idempotent."""
    await set_tenant_context(db, current_user.tenant_id)

    # Verify recipe belongs to this tenant
    recipe_result = await db.execute(
        select(Recipe).where(
            Recipe.id == recipe_id, Recipe.tenant_id == current_user.tenant_id
        )
    )
    if not recipe_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Find or create the checklist item
    item_result = await db.execute(
        select(RecipeChecklistItem).where(
            RecipeChecklistItem.recipe_id == recipe_id,
            RecipeChecklistItem.ingredient_id == ingredient_id,
            RecipeChecklistItem.user_id == current_user.id,
        )
    )
    item = item_result.scalar_one_or_none()

    if not item:
        # Auto-create if missing (user toggled before GET checklist)
        item = RecipeChecklistItem(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            recipe_id=recipe_id,
            ingredient_id=ingredient_id,
            checked=False,
            checked_at=None,
        )
        db.add(item)
        await db.flush()

    item.checked = body.checked
    item.checked_at = datetime.now(timezone.utc) if body.checked else None

    await db.commit()
    await db.refresh(item)
    return item
