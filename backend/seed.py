#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Seed script — populates a local Manna database with test data.
Run: docker compose exec api python seed.py
"""
import asyncio
import uuid

from sqlalchemy import text
from app.database import async_session, create_tables
from app.models.user import Tenant, User
from app.models.recipe import Recipe, RecipeIngredient, RecipeInstruction
from app.auth.service import hash_password


async def seed():
    await create_tables()

    async with async_session() as db:
        # ---- Tenant & User ----
        tenant = Tenant(id=uuid.uuid4(), name="Test Kitchen")
        db.add(tenant)
        await db.flush()

        user = User(
            email="chef@manna.dev",
            hashed_password=hash_password("password123"),
            full_name="Test Chef",
            tenant_id=tenant.id,
        )
        db.add(user)
        await db.flush()

        # ---- Recipes ----
        recipes_data = [
            {
                "title": "Classic Tomato Soup",
                "description": "A simple and comforting tomato soup.",
                "prep_time_minutes": 10,
                "cook_time_minutes": 30,
                "total_time_minutes": 40,
                "servings": "4 servings",
                "ingredients": [
                    "2 cans (28 oz) crushed tomatoes",
                    "1 medium onion, diced",
                    "3 cloves garlic, minced",
                    "2 cups vegetable broth",
                    "1 tbsp olive oil",
                    "1 tsp sugar",
                    "Salt and pepper to taste",
                    "Fresh basil for garnish",
                ],
                "instructions": [
                    "Heat olive oil in a large pot over medium heat.",
                    "Saut\u00e9 onion until soft, about 5 minutes. Add garlic and cook 1 minute.",
                    "Add crushed tomatoes, broth, sugar, salt, and pepper. Bring to a boil.",
                    "Reduce heat and simmer for 25 minutes.",
                    "Blend until smooth with an immersion blender. Garnish with basil.",
                ],
            },
            {
                "title": "Garlic Butter Shrimp",
                "description": "Quick pan-seared shrimp in garlic butter.",
                "prep_time_minutes": 5,
                "cook_time_minutes": 8,
                "total_time_minutes": 13,
                "servings": "2 servings",
                "ingredients": [
                    "1 lb large shrimp, peeled and deveined",
                    "4 tbsp unsalted butter",
                    "5 cloves garlic, minced",
                    "Juice of 1 lemon",
                    "1/4 tsp red pepper flakes",
                    "Fresh parsley, chopped",
                ],
                "instructions": [
                    "Melt butter in a large skillet over medium-high heat.",
                    "Add garlic and red pepper flakes, cook 30 seconds.",
                    "Add shrimp in a single layer. Cook 2 minutes per side until pink.",
                    "Squeeze lemon juice over the shrimp, toss, and garnish with parsley.",
                ],
            },
            {
                "title": "Overnight Oats",
                "description": "No-cook breakfast ready when you wake up.",
                "prep_time_minutes": 5,
                "cook_time_minutes": 0,
                "total_time_minutes": 5,
                "servings": "1 serving",
                "ingredients": [
                    "1/2 cup rolled oats",
                    "1/2 cup milk of choice",
                    "1/4 cup Greek yogurt",
                    "1 tbsp chia seeds",
                    "1 tbsp maple syrup",
                    "1/2 cup mixed berries",
                ],
                "instructions": [
                    "Combine oats, milk, yogurt, chia seeds, and maple syrup in a jar.",
                    "Stir well, cover, and refrigerate overnight (or at least 4 hours).",
                    "Top with mixed berries before serving.",
                ],
            },
        ]

        for data in recipes_data:
            recipe = Recipe(
                title=data["title"],
                description=data["description"],
                prep_time_minutes=data["prep_time_minutes"],
                cook_time_minutes=data["cook_time_minutes"],
                total_time_minutes=data["total_time_minutes"],
                servings=data["servings"],
                tenant_id=tenant.id,
            )
            db.add(recipe)
            await db.flush()

            for i, ing in enumerate(data["ingredients"]):
                db.add(RecipeIngredient(
                    recipe_id=recipe.id, text=ing, position=i, tenant_id=tenant.id
                ))
            for i, inst in enumerate(data["instructions"]):
                db.add(RecipeInstruction(
                    recipe_id=recipe.id, text=inst, position=i, tenant_id=tenant.id
                ))

        await db.commit()
        print(f"Seeded tenant '{tenant.name}' with user chef@manna.dev")
        print(f"Created {len(recipes_data)} test recipes.")


if __name__ == "__main__":
    asyncio.run(seed())
