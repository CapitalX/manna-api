# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Tests for the recipes router — Phase 14 (Recipe URL Import, Mealie-backed).

TDD: these tests are written first; they will fail until the implementation
in router.py and scraper.py is complete.

Pattern: uses the existing `authed_client` fixture from conftest.py.
Scraper is mocked at the import boundary where the router binds it:
  app.recipes.router.scrape_recipe_url

The router uses `from ... import scrape_recipe_url`, so the reference lives in
the router module's namespace — patching the scraper module would have no effect.

This avoids any real HTTP requests and keeps tests deterministic.
"""
import uuid
import pytest
import httpx

from app.models.recipe import Recipe, RecipeIngredient, RecipeInstruction
from app.recipes.scraper import ScrapedRecipe, normalize_source_url


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

def _make_scraped(title: str = "Roasted Carrots", url: str = "https://example.com/roasted-carrots") -> ScrapedRecipe:
    return ScrapedRecipe(
        title=title,
        description="A simple roasted carrot recipe.",
        image_url="https://example.com/carrot.jpg",
        prep_time_minutes=10,
        cook_time_minutes=30,
        total_time_minutes=40,
        servings="4 servings",
        ingredients=["1 lb carrots", "2 tbsp olive oil", "salt and pepper"],
        instructions=["Preheat oven to 400°F.", "Toss carrots with oil.", "Roast 25-30 min."],
        source_url=url,
    )


async def _setup_user(state: dict, db_session) -> None:
    """Populate the authed_client state dict with a fresh user."""
    from tests.conftest import create_user_and_token
    user, token = await create_user_and_token(db_session)
    state["user"] = user


# ---------------------------------------------------------------------------
# 1 — URL normalization unit tests (pure function, no DB)
# ---------------------------------------------------------------------------

class TestNormalizeSourceUrl:
    def test_strips_fragment(self):
        assert normalize_source_url("https://example.com/recipe#top") == "https://example.com/recipe"

    def test_strips_utm_source(self):
        result = normalize_source_url("https://example.com/recipe?utm_source=twitter")
        assert "utm_source" not in result
        assert "example.com/recipe" in result

    def test_strips_multiple_tracking_params(self):
        result = normalize_source_url(
            "https://example.com/r?utm_source=fb&utm_medium=social&fbclid=abc123&gclid=xyz"
        )
        assert "utm_source" not in result
        assert "fbclid" not in result
        assert "gclid" not in result

    def test_preserves_non_tracking_query_params(self):
        result = normalize_source_url("https://example.com/r?recipe_id=42&page=2")
        assert "recipe_id=42" in result
        assert "page=2" in result

    def test_lowercases_scheme_and_host(self):
        result = normalize_source_url("HTTPS://Example.COM/recipe")
        assert result.startswith("https://example.com")

    def test_removes_trailing_slash_on_path(self):
        result = normalize_source_url("https://example.com/recipe/")
        assert not result.endswith("/")

    def test_preserves_root_path(self):
        # Root path — stripping trailing slash from https://example.com/ would
        # yield https://example.com which is still valid
        result = normalize_source_url("https://example.com/")
        assert result == "https://example.com"

    def test_strips_mc_tracking_params(self):
        result = normalize_source_url("https://example.com/r?mc_cid=abc&mc_eid=def&id=5")
        assert "mc_cid" not in result
        assert "mc_eid" not in result
        assert "id=5" in result

    def test_strips_ref_param(self):
        result = normalize_source_url("https://example.com/r?ref=homepage&page=2")
        assert "ref=" not in result
        assert "page=2" in result


# ---------------------------------------------------------------------------
# 2 — Import happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_url_happy_path(authed_client, db_session, monkeypatch):
    client, state = authed_client
    await _setup_user(state, db_session)

    scraped = _make_scraped()
    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", lambda url: _async_return(scraped))

    resp = client.post("/api/v1/recipes/import-url", json={"url": "https://example.com/roasted-carrots"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["already_exists"] is False
    assert body["recipe"]["title"] == "Roasted Carrots"
    assert body["recipe"]["id"] is not None

    # Row must exist in DB scoped to tenant
    from sqlalchemy import select
    result = await db_session.execute(
        select(Recipe).where(Recipe.tenant_id == state["user"].tenant_id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].title == "Roasted Carrots"
    # source_url stored normalized
    assert rows[0].source_url == "https://example.com/roasted-carrots"


# ---------------------------------------------------------------------------
# 3 — Dedupe: exact same URL twice
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_url_dedupe_exact(authed_client, db_session, monkeypatch):
    client, state = authed_client
    await _setup_user(state, db_session)

    call_count = {"n": 0}

    async def mock_scrape(url: str) -> ScrapedRecipe:
        call_count["n"] += 1
        return _make_scraped(url=url)

    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", mock_scrape)

    url = "https://example.com/roasted-carrots"

    resp1 = client.post("/api/v1/recipes/import-url", json={"url": url})
    assert resp1.status_code == 201
    assert resp1.json()["already_exists"] is False

    resp2 = client.post("/api/v1/recipes/import-url", json={"url": url})
    assert resp2.status_code == 200
    assert resp2.json()["already_exists"] is True
    # Same recipe id
    assert resp1.json()["recipe"]["id"] == resp2.json()["recipe"]["id"]
    # Scraper called only once
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# 4 — Dedupe: URL variant forms all resolve to same row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_url_dedupe_variants(authed_client, db_session, monkeypatch):
    client, state = authed_client
    await _setup_user(state, db_session)

    call_count = {"n": 0}

    async def mock_scrape(url: str) -> ScrapedRecipe:
        call_count["n"] += 1
        return _make_scraped(url=url)

    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", mock_scrape)

    # Three variant forms of the same URL
    variants = [
        "https://example.com/x?utm_source=foo#top",
        "https://example.com/x/",
        "HTTPS://Example.com/x",
    ]

    responses = []
    for v in variants:
        r = client.post("/api/v1/recipes/import-url", json={"url": v})
        responses.append(r)

    # First must be 201
    assert responses[0].status_code == 201
    # Second and third must be 200 dedupe
    assert responses[1].status_code == 200
    assert responses[2].status_code == 200
    assert responses[1].json()["already_exists"] is True
    assert responses[2].json()["already_exists"] is True

    # All return same recipe id
    ids = {r.json()["recipe"]["id"] for r in responses}
    assert len(ids) == 1

    # Scraper called only once
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# 5 — Scraper failure → 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_url_scraper_failure(authed_client, db_session, monkeypatch):
    client, state = authed_client
    await _setup_user(state, db_session)

    async def mock_scrape_fail(url: str):
        raise Exception("unsupported site")

    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", mock_scrape_fail)

    resp = client.post("/api/v1/recipes/import-url", json={"url": "https://example.com/recipe"})

    assert resp.status_code == 422
    assert "Couldn't read that recipe" in resp.json()["detail"]

    # No DB row created
    from sqlalchemy import select
    result = await db_session.execute(
        select(Recipe).where(Recipe.tenant_id == state["user"].tenant_id)
    )
    assert result.scalars().all() == []


# ---------------------------------------------------------------------------
# 6 — Upstream timeout → 504
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_url_timeout(authed_client, db_session, monkeypatch):
    client, state = authed_client
    await _setup_user(state, db_session)

    async def mock_scrape_timeout(url: str):
        raise httpx.TimeoutException("timed out", request=None)

    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", mock_scrape_timeout)

    resp = client.post("/api/v1/recipes/import-url", json={"url": "https://example.com/recipe"})

    assert resp.status_code == 504
    assert "didn't respond in time" in resp.json()["detail"].lower()

    # No DB row
    from sqlalchemy import select
    result = await db_session.execute(
        select(Recipe).where(Recipe.tenant_id == state["user"].tenant_id)
    )
    assert result.scalars().all() == []


# ---------------------------------------------------------------------------
# 7 — Invalid URL shape → 422 (pydantic)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_url_invalid_url(authed_client, db_session, monkeypatch):
    client, state = authed_client
    await _setup_user(state, db_session)

    monkeypatch.setattr("app.recipes.scraper.scrape_recipe_url", lambda url: _async_return(_make_scraped()))

    resp = client.post("/api/v1/recipes/import-url", json={"url": "not-a-url"})

    assert resp.status_code == 422

    # No DB row
    from sqlalchemy import select
    result = await db_session.execute(
        select(Recipe).where(Recipe.tenant_id == state["user"].tenant_id)
    )
    assert result.scalars().all() == []


# ---------------------------------------------------------------------------
# 8 — Unauthorized → 401
# ---------------------------------------------------------------------------

def test_import_url_unauthorized(client):
    resp = client.post("/api/v1/recipes/import-url", json={"url": "https://example.com/recipe"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 9 — Tenant isolation: two users same URL → two separate rows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_url_tenant_isolation(authed_client, db_session, monkeypatch):
    from tests.conftest import create_user_and_token
    from app.auth.dependencies import get_current_user
    from app.database import get_db
    from app.main import app
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    import os

    # We need two separate authed clients with different users
    # Build them manually using the same db_session override pattern
    engine_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    user_a, _ = await create_user_and_token(db_session)
    user_b, _ = await create_user_and_token(db_session)

    async def mock_scrape(url: str) -> ScrapedRecipe:
        return _make_scraped(url=url)

    monkeypatch.setattr("app.recipes.router.scrape_recipe_url", mock_scrape)

    url = "https://example.com/carrot-soup"

    from fastapi.testclient import TestClient

    async def override_db():
        yield db_session

    results = {}
    for label, user in [("a", user_a), ("b", user_b)]:
        async def override_user(u=user):
            return u

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user

        with TestClient(app) as c:
            r = c.post("/api/v1/recipes/import-url", json={"url": url})
        results[label] = r

    app.dependency_overrides.clear()

    assert results["a"].status_code == 201
    assert results["b"].status_code == 201

    # Different recipe ids
    assert results["a"].json()["recipe"]["id"] != results["b"].json()["recipe"]["id"]

    # Confirm each user sees only their own recipe via list
    from sqlalchemy import select
    rows_a = (await db_session.execute(
        select(Recipe).where(Recipe.tenant_id == user_a.tenant_id)
    )).scalars().all()
    rows_b = (await db_session.execute(
        select(Recipe).where(Recipe.tenant_id == user_b.tenant_id)
    )).scalars().all()

    assert len(rows_a) == 1
    assert len(rows_b) == 1
    assert rows_a[0].id != rows_b[0].id


# ---------------------------------------------------------------------------
# 10 — List ordering: newest first
#
# SQLite's func.now() has second-level precision, so two rows inserted in
# rapid succession share the same `created_at` value. We seed rows with
# explicit timestamps to guarantee ordering is tested correctly.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_recipes_newest_first(authed_client, db_session, monkeypatch):
    from datetime import datetime, timezone, timedelta
    from app.models.recipe import Recipe as RecipeModel

    client, state = authed_client
    await _setup_user(state, db_session)

    user = state["user"]
    now = datetime.now(timezone.utc)

    # Seed two recipes with distinct created_at values
    older = RecipeModel(
        title="Older Recipe",
        source_url="https://example.com/older",
        tenant_id=user.tenant_id,
        created_at=now - timedelta(hours=1),
        updated_at=now - timedelta(hours=1),
    )
    newer = RecipeModel(
        title="Newer Recipe",
        source_url="https://example.com/newer",
        tenant_id=user.tenant_id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(older)
    db_session.add(newer)
    await db_session.commit()

    resp = client.get("/api/v1/recipes/")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    # Newest (created_at = now) must be first in the list
    assert items[0]["title"] == "Newer Recipe"
    assert items[1]["title"] == "Older Recipe"


# ---------------------------------------------------------------------------
# Helper: wrap a value in a coroutine (for monkeypatching async functions)
# ---------------------------------------------------------------------------

async def _async_return(value):
    return value
