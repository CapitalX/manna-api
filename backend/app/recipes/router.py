# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db, set_tenant_context
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.recipe import Recipe, RecipeIngredient, RecipeInstruction
from sqlalchemy import desc
from app.recipes.schemas import RecipeCreate, RecipeOut, ScrapeRequest, ImportUrlRequest, ImportUrlResponse
from app.recipes.scraper import scrape_recipe_url, normalize_source_url

router = APIRouter(prefix="/recipes", tags=["recipes"])


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

    for i, text in enumerate(scraped.ingredients):
        db.add(RecipeIngredient(
            recipe_id=recipe.id, text=text, position=i, tenant_id=current_user.tenant_id
        ))
    for i, text in enumerate(scraped.instructions):
        db.add(RecipeInstruction(
            recipe_id=recipe.id, text=text, position=i, tenant_id=current_user.tenant_id
        ))

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
