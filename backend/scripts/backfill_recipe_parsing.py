#!/usr/bin/env python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
One-shot backfill script: parse + score all existing recipe_ingredients rows.

Usage (from the backend/ directory):
    python scripts/backfill_recipe_parsing.py [--dry-run]

Options:
    --dry-run   Print what would change without writing to the database.
    --batch N   Batch size per commit (default: 50 recipes).

Safety:
    - Idempotent: skips ingredients where confidence > 0.0 (already parsed).
    - Rescores all recipes touched (even partially).
    - Prints a summary at the end.
    - DO NOT run against production without reviewing output first.

Prerequisites:
    - Run alembic upgrade head (migration 004) before this script.
    - DATABASE_URL env var must point to the target database.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

# Add backend/ to path so imports work when run from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.recipe import Recipe, RecipeIngredient
from app.recipes.parser import parse_line
from app.recipes.categorizer import categorize
from app.recipes.scoring import score_recipe


settings = get_settings()


async def backfill(dry_run: bool = False, batch_size: int = 50) -> None:
    """Main backfill coroutine."""
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    recipes_rescored = 0
    ingredients_reparsed = 0
    ingredients_needs_review = 0
    skipped = 0

    print(f"Starting backfill (dry_run={dry_run}, batch_size={batch_size})")
    print(f"Database: {settings.database_url}")
    print()

    async with session_factory() as session:
        # Fetch all recipes with their ingredients
        result = await session.execute(
            select(Recipe).options(selectinload(Recipe.ingredients))
        )
        recipes = result.scalars().all()

        print(f"Found {len(recipes)} recipes to process")
        print()

        batch: list[Recipe] = []

        for recipe in recipes:
            recipe_touched = False

            for ing in recipe.ingredients:
                # Skip already-parsed ingredients (confidence > 0 means they were parsed)
                if ing.confidence > 0.0:
                    skipped += 1
                    continue

                raw = ing.raw_text or ing.text
                if not raw:
                    skipped += 1
                    continue

                parsed = parse_line(raw)
                cat, _cat_conf = categorize(parsed.name or raw)

                if not dry_run:
                    ing.raw_text = raw
                    ing.quantity = parsed.quantity
                    ing.unit = parsed.unit
                    ing.name = parsed.name
                    ing.category = cat
                    ing.confidence = parsed.confidence
                    ing.needs_review = parsed.needs_review
                else:
                    print(
                        f"  Would parse: {raw!r} → qty={parsed.quantity}, "
                        f"unit={parsed.unit!r}, name={parsed.name!r}, "
                        f"cat={cat}, needs_review={parsed.needs_review}"
                    )

                ingredients_reparsed += 1
                if parsed.needs_review:
                    ingredients_needs_review += 1
                recipe_touched = True

            if recipe_touched or recipe.quality_score == 0:
                # Re-score this recipe
                class _Proxy:
                    def __init__(self, r):
                        self.servings = r.servings
                        self.user_verified = r.user_verified
                        self.ingredients = r.ingredients

                score_result = score_recipe(_Proxy(recipe))

                if not dry_run:
                    recipe.quality_score = score_result.score
                    recipe.quality_tier = score_result.tier
                    recipe.quality_reasons = score_result.reasons
                    recipe.last_scored_at = datetime.now(timezone.utc)
                else:
                    print(
                        f"  Would score recipe {recipe.id} ({recipe.title!r}): "
                        f"score={score_result.score}, tier={score_result.tier}"
                    )

                recipes_rescored += 1
                batch.append(recipe)

            # Commit in batches
            if not dry_run and len(batch) >= batch_size:
                await session.commit()
                print(f"  Committed batch of {len(batch)} recipes")
                batch = []

        # Final commit
        if not dry_run and batch:
            await session.commit()
            print(f"  Committed final batch of {len(batch)} recipes")

    await engine.dispose()

    print()
    print("=" * 60)
    print("Backfill complete:")
    print(f"  Recipes rescored:           {recipes_rescored}")
    print(f"  Ingredients reparsed:       {ingredients_reparsed}")
    print(f"  Ingredients marked review:  {ingredients_needs_review}")
    print(f"  Ingredients skipped:        {skipped}")
    if dry_run:
        print()
        print("  DRY RUN — no changes written")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Backfill recipe parsing and scoring")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--batch", type=int, default=50, help="Commit batch size (default: 50)")
    args = parser.parse_args()

    asyncio.run(backfill(dry_run=args.dry_run, batch_size=args.batch))


if __name__ == "__main__":
    main()
