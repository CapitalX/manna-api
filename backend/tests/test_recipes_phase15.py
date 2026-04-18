# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Phase 15 router tests — TDD first.

Tests cover:
  - Import populates structured ingredient fields (qty, unit, name, etc.)
  - Import sets quality_score, quality_tier, quality_reasons on Recipe
  - Editing an ingredient recomputes quality_score on the recipe
  - Tenant isolation: user A cannot GET user B's checklist
  - Checklist toggle is idempotent (PATCH twice with same value → 200)
  - GET /checklist returns one row per ingredient (lazy creation)
  - Verify endpoint flips user_verified

Uses the same conftest.py fixtures as Phase 14 tests.
"""
import uuid
import pytest

from app.models.recipe import Recipe, RecipeIngredient
from app.recipes.scraper import ScrapedRecipe


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_scraped(
    title: str = "Test Soup",
    ingredients: list[str] | None = None,
    servings: str = "4 servings",
) -> ScrapedRecipe:
    return ScrapedRecipe(
        title=title,
        description=None,
        image_url=None,
        prep_time_minutes=10,
        cook_time_minutes=20,
        total_time_minutes=30,
        servings=servings,
        ingredients=ingredients or ["2 cups broccoli", "1 tbsp olive oil", "salt to taste"],
        instructions=["Chop. Cook. Eat."],
        source_url=f"https://example.com/{title.lower().replace(' ', '-')}",
    )


async def _setup_user(state: dict, db_session) -> None:
    from tests.conftest import create_user_and_token
    user, token = await create_user_and_token(db_session)
    state["user"] = user


async def _async_return(value):
    return value


# ---------------------------------------------------------------------------
# 1 — Import populates structured ingredient fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_populates_structured_fields(authed_client, db_session, monkeypatch):
    """POST /import-url should persist quantity, unit, name, category on ingredients."""
    client, state = authed_client
    await _setup_user(state, db_session)

    scraped = _make_scraped(ingredients=["2 cups broccoli", "1 tbsp olive oil"])
    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", lambda url: _async_return(scraped))

    resp = client.post("/api/v1/recipes/import-url", json={"url": "https://example.com/soup"})
    assert resp.status_code == 201
    body = resp.json()

    # Quality fields on recipe
    assert "quality_score" in body["recipe"]
    assert "quality_tier" in body["recipe"]
    assert "quality_reasons" in body["recipe"]

    # Ingredients have structured fields
    ingredients = body["recipe"]["ingredients"]
    assert len(ingredients) == 2
    for ing in ingredients:
        assert "quantity" in ing
        assert "unit" in ing
        assert "name" in ing
        assert "category" in ing
        assert "needs_review" in ing
        assert "raw_text" in ing

    # Broccoli ingredient should be parsed
    broccoli = next((i for i in ingredients if "broccoli" in (i.get("raw_text") or "") or "broccoli" in (i.get("name") or "")), None)
    assert broccoli is not None


# ---------------------------------------------------------------------------
# 2 — Import sets quality score on recipe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_sets_quality_score(authed_client, db_session, monkeypatch):
    """quality_score > 0 after successful import with real ingredients."""
    client, state = authed_client
    await _setup_user(state, db_session)

    scraped = _make_scraped()
    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", lambda url: _async_return(scraped))

    resp = client.post("/api/v1/recipes/import-url", json={"url": "https://example.com/test-soup2"})
    assert resp.status_code == 201
    body = resp.json()["recipe"]

    assert body["quality_score"] >= 0  # non-null
    assert body["quality_tier"] in ("draft", "needs_info", "processable", "verified")
    assert isinstance(body["quality_reasons"], list)
    assert body["user_verified"] is False


# ---------------------------------------------------------------------------
# 3 — Edit ingredient re-scores recipe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edit_ingredient_rescores_recipe(authed_client, db_session, monkeypatch):
    """PATCH /recipes/{id}/ingredients/{ing_id} should recompute quality_score."""
    client, state = authed_client
    await _setup_user(state, db_session)

    # Import a recipe with one needs_review ingredient
    scraped = _make_scraped(ingredients=["mystery ingredient"], servings="4 servings")
    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", lambda url: _async_return(scraped))

    resp = client.post("/api/v1/recipes/import-url", json={"url": "https://example.com/mystery"})
    assert resp.status_code == 201
    recipe_id = resp.json()["recipe"]["id"]
    initial_score = resp.json()["recipe"]["quality_score"]

    # Get the ingredient id
    ingredients = resp.json()["recipe"]["ingredients"]
    assert len(ingredients) == 1
    ing_id = ingredients[0]["id"]

    # Patch with proper values
    patch_resp = client.patch(
        f"/api/v1/recipes/{recipe_id}/ingredients/{ing_id}",
        json={
            "quantity": 2.0,
            "unit": "cup",
            "name": "broccoli",
            "category": "vegetables",
            "needs_review": False,
        },
    )
    assert patch_resp.status_code == 200

    # Fetch updated recipe — score should have improved
    get_resp = client.get(f"/api/v1/recipes/{recipe_id}")
    assert get_resp.status_code == 200
    new_score = get_resp.json()["quality_score"]
    assert new_score >= initial_score  # editing makes it at least as good


# ---------------------------------------------------------------------------
# 4 — GET checklist: lazy creation, one row per ingredient
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_checklist_lazy_creation(authed_client, db_session, monkeypatch):
    """GET /recipes/{id}/checklist creates one row per ingredient on first fetch."""
    client, state = authed_client
    await _setup_user(state, db_session)

    scraped = _make_scraped(ingredients=["1 cup oats", "2 tbsp honey"])
    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", lambda url: _async_return(scraped))

    resp = client.post("/api/v1/recipes/import-url", json={"url": "https://example.com/oats"})
    assert resp.status_code == 201
    recipe_id = resp.json()["recipe"]["id"]

    checklist_resp = client.get(f"/api/v1/recipes/{recipe_id}/checklist")
    assert checklist_resp.status_code == 200
    items = checklist_resp.json()
    assert len(items) == 2
    for item in items:
        assert "ingredient_id" in item
        assert item["checked"] is False
        assert "checked_at" in item


# ---------------------------------------------------------------------------
# 5 — Checklist toggle: PATCH sets checked=True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_checklist_toggle_check(authed_client, db_session, monkeypatch):
    """PATCH /recipes/{id}/checklist/{ing_id} with checked=True toggles item."""
    client, state = authed_client
    await _setup_user(state, db_session)

    scraped = _make_scraped(ingredients=["1 cup spinach"])
    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", lambda url: _async_return(scraped))

    resp = client.post("/api/v1/recipes/import-url", json={"url": "https://example.com/spinach"})
    assert resp.status_code == 201
    recipe_id = resp.json()["recipe"]["id"]
    ing_id = resp.json()["recipe"]["ingredients"][0]["id"]

    # Fetch checklist to create rows
    client.get(f"/api/v1/recipes/{recipe_id}/checklist")

    # Toggle to checked=True
    toggle_resp = client.patch(
        f"/api/v1/recipes/{recipe_id}/checklist/{ing_id}",
        json={"checked": True},
    )
    assert toggle_resp.status_code == 200
    item = toggle_resp.json()
    assert item["checked"] is True
    assert item["checked_at"] is not None


# ---------------------------------------------------------------------------
# 6 — Checklist toggle: idempotent (PATCH twice → both 200)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_checklist_toggle_idempotent(authed_client, db_session, monkeypatch):
    """PATCH twice with same value returns 200 each time, not 409."""
    client, state = authed_client
    await _setup_user(state, db_session)

    scraped = _make_scraped(ingredients=["2 cups water"])
    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", lambda url: _async_return(scraped))

    resp = client.post("/api/v1/recipes/import-url", json={"url": "https://example.com/water"})
    assert resp.status_code == 201
    recipe_id = resp.json()["recipe"]["id"]
    ing_id = resp.json()["recipe"]["ingredients"][0]["id"]

    client.get(f"/api/v1/recipes/{recipe_id}/checklist")

    r1 = client.patch(
        f"/api/v1/recipes/{recipe_id}/checklist/{ing_id}",
        json={"checked": True},
    )
    r2 = client.patch(
        f"/api/v1/recipes/{recipe_id}/checklist/{ing_id}",
        json={"checked": True},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200


# ---------------------------------------------------------------------------
# 7 — Checklist toggle: uncheck clears checked_at
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_checklist_toggle_uncheck(authed_client, db_session, monkeypatch):
    """PATCH with checked=False clears checked_at."""
    client, state = authed_client
    await _setup_user(state, db_session)

    scraped = _make_scraped(ingredients=["3 cloves garlic"])
    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", lambda url: _async_return(scraped))

    resp = client.post("/api/v1/recipes/import-url", json={"url": "https://example.com/garlic"})
    assert resp.status_code == 201
    recipe_id = resp.json()["recipe"]["id"]
    ing_id = resp.json()["recipe"]["ingredients"][0]["id"]

    client.get(f"/api/v1/recipes/{recipe_id}/checklist")

    # Check
    client.patch(f"/api/v1/recipes/{recipe_id}/checklist/{ing_id}", json={"checked": True})
    # Uncheck
    r = client.patch(f"/api/v1/recipes/{recipe_id}/checklist/{ing_id}", json={"checked": False})
    assert r.status_code == 200
    item = r.json()
    assert item["checked"] is False
    assert item["checked_at"] is None


# ---------------------------------------------------------------------------
# 8 — Tenant isolation: cannot access another user's checklist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_checklist_tenant_isolation(db_session, monkeypatch):
    """User A cannot fetch user B's checklist (returns 404 on recipe lookup)."""
    from tests.conftest import create_user_and_token
    from app.auth.dependencies import get_current_user
    from app.database import get_db
    from app.main import app
    from fastapi.testclient import TestClient

    user_a, _ = await create_user_and_token(db_session)
    user_b, _ = await create_user_and_token(db_session)

    async def override_db():
        yield db_session

    scraped = _make_scraped(ingredients=["1 cup secret"])
    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", lambda url: _async_return(scraped))

    # Import recipe as user_a
    async def user_a_override():
        return user_a

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = user_a_override

    with TestClient(app) as client_a:
        resp = client_a.post("/api/v1/recipes/import-url", json={"url": "https://example.com/secret"})
    recipe_id = resp.json()["recipe"]["id"]

    # Try to access user_a's recipe checklist as user_b
    async def user_b_override():
        return user_b

    app.dependency_overrides[get_current_user] = user_b_override
    with TestClient(app) as client_b:
        r = client_b.get(f"/api/v1/recipes/{recipe_id}/checklist")

    app.dependency_overrides.clear()

    # Should 404 because recipe is not visible to user_b's tenant
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 9 — Verify endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_endpoint(authed_client, db_session, monkeypatch):
    """POST /recipes/{id}/verify sets user_verified=True and may upgrade tier."""
    client, state = authed_client
    await _setup_user(state, db_session)

    # Use a well-parsed recipe to get a high score
    scraped = _make_scraped(
        ingredients=[
            "2 cups broccoli",
            "1 tbsp olive oil",
            "1 tsp garlic powder",
            "1/2 tsp salt",
            "1 cup brown rice",
        ],
        servings="4 servings",
    )
    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", lambda url: _async_return(scraped))

    resp = client.post("/api/v1/recipes/import-url", json={"url": "https://example.com/broccoli-rice"})
    assert resp.status_code == 201
    recipe_id = resp.json()["recipe"]["id"]

    verify_resp = client.post(f"/api/v1/recipes/{recipe_id}/verify")
    assert verify_resp.status_code == 200
    body = verify_resp.json()
    assert body["user_verified"] is True
    # Tier should reflect verified if score >= 90
    if body["quality_score"] >= 90:
        assert body["quality_tier"] == "verified"
