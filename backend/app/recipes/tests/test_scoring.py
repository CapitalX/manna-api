# SPDX-License-Identifier: AGPL-3.0-or-later
"""
TDD tests for app/recipes/scoring.py

Written FIRST — tests fail until implementation exists.
Formula: parse_coverage(40) + unit_validity(15) + servings_present(15) +
         name_canonical(15) + categorization(15) = 100

Tier thresholds:
  verified:    score >= 90 AND user_verified == True
  processable: score >= 75
  needs_info:  score >= 50
  draft:       else
"""
import pytest
from dataclasses import dataclass, field
from typing import Optional
from decimal import Decimal


# ---------------------------------------------------------------------------
# Stub models (mirrors SQLAlchemy structure without DB dependency)
# ---------------------------------------------------------------------------

@dataclass
class StubIngredient:
    quantity: Optional[float] = None
    unit: Optional[str] = None
    name: Optional[str] = None
    category: str = "other"
    confidence: float = 0.0
    needs_review: bool = True


@dataclass
class StubRecipe:
    servings: Optional[str] = None
    user_verified: bool = False
    ingredients: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _good_ingredient(category: str = "vegetables") -> StubIngredient:
    """Ingredient that is fully parsed — qty, unit, name, non-other category."""
    return StubIngredient(
        quantity=2.0,
        unit="cup",
        name="broccoli",
        category=category,
        confidence=0.9,
        needs_review=False,
    )


def _bad_ingredient() -> StubIngredient:
    """Ingredient that failed parsing — no qty, no unit, needs_review."""
    return StubIngredient(
        quantity=None,
        unit=None,
        name="mystery ingredient",
        category="other",
        confidence=0.1,
        needs_review=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestScoreRecipe:
    def test_import(self):
        from app.recipes.scoring import score_recipe, ScoreResult  # noqa: F401

    def test_perfect_recipe_score_100(self):
        """All 10 ingredients fully parsed, has servings, no 'other' category."""
        from app.recipes.scoring import score_recipe
        recipe = StubRecipe(
            servings="4 servings",
            ingredients=[_good_ingredient() for _ in range(10)],
        )
        result = score_recipe(recipe)
        assert result.score == 100
        assert result.tier == "processable"  # not verified — user_verified not set

    def test_verified_tier_requires_user_flag(self):
        """score >= 90 AND user_verified=True → tier = 'verified'."""
        from app.recipes.scoring import score_recipe
        recipe = StubRecipe(
            servings="4 servings",
            user_verified=True,
            ingredients=[_good_ingredient() for _ in range(10)],
        )
        result = score_recipe(recipe)
        assert result.score >= 90
        assert result.tier == "verified"

    def test_all_needs_review_low_score(self):
        """All ingredients need review → low parse_coverage component."""
        from app.recipes.scoring import score_recipe
        recipe = StubRecipe(
            servings="4 servings",
            ingredients=[_bad_ingredient() for _ in range(10)],
        )
        result = score_recipe(recipe)
        # parse_coverage = 0; unit_validity = 15 (no units = no penalty); name_canonical penalized
        # servings_present = 15; categorization = 0 (needs_review on all)
        # Expect a low score: 0 + 15 + 15 + 0 + 0 = 30 or similar range
        assert result.score <= 45
        assert result.tier in ("draft", "needs_info")

    def test_no_servings_reduces_score(self):
        """Missing servings → loses 15 points, reason includes 'no_servings'."""
        from app.recipes.scoring import score_recipe
        with_servings = StubRecipe(
            servings="4 servings",
            ingredients=[_good_ingredient() for _ in range(5)],
        )
        without_servings = StubRecipe(
            servings=None,
            ingredients=[_good_ingredient() for _ in range(5)],
        )
        r_with = score_recipe(with_servings)
        r_without = score_recipe(without_servings)
        assert r_with.score == r_without.score + 15
        assert "no_servings" in r_without.reasons

    def test_no_servings_digit_reduces_score(self):
        """'servings' without a digit is treated as missing."""
        from app.recipes.scoring import score_recipe
        recipe = StubRecipe(
            servings="multiple",  # no digit
            ingredients=[_good_ingredient() for _ in range(5)],
        )
        result = score_recipe(recipe)
        assert "no_servings" in result.reasons

    def test_servings_with_digit(self):
        """'4 servings' counts as present — no no_servings reason."""
        from app.recipes.scoring import score_recipe
        recipe = StubRecipe(
            servings="4 servings",
            ingredients=[_good_ingredient() for _ in range(5)],
        )
        result = score_recipe(recipe)
        assert "no_servings" not in result.reasons

    def test_other_category_reduces_name_canonical(self):
        """Ingredients with category='other' reduce the name_canonical component."""
        from app.recipes.scoring import score_recipe
        all_good = StubRecipe(
            servings="4",
            ingredients=[_good_ingredient("vegetables") for _ in range(5)],
        )
        all_other = StubRecipe(
            servings="4",
            ingredients=[StubIngredient(
                quantity=1.0, unit="cup", name="stuff",
                category="other", confidence=0.8, needs_review=False,
            ) for _ in range(5)],
        )
        r_good = score_recipe(all_good)
        r_other = score_recipe(all_other)
        assert r_good.score > r_other.score
        # Other-category reason should appear
        assert any("other_category" in r for r in r_other.reasons)

    def test_deterministic(self):
        """Same input → same output on repeated calls."""
        from app.recipes.scoring import score_recipe
        recipe = StubRecipe(
            servings="6",
            ingredients=[_good_ingredient() for _ in range(7)],
        )
        r1 = score_recipe(recipe)
        r2 = score_recipe(recipe)
        assert r1.score == r2.score
        assert r1.tier == r2.tier
        assert r1.reasons == r2.reasons

    def test_empty_ingredients_low_score(self):
        """No ingredients → parse_coverage is undefined; score should be very low."""
        from app.recipes.scoring import score_recipe
        recipe = StubRecipe(servings="4", ingredients=[])
        result = score_recipe(recipe)
        assert result.score <= 30

    def test_score_result_fields(self):
        """ScoreResult has score, tier, reasons fields."""
        from app.recipes.scoring import score_recipe, ScoreResult
        recipe = StubRecipe(servings="4", ingredients=[_good_ingredient()])
        result = score_recipe(recipe)
        assert isinstance(result.score, int)
        assert isinstance(result.tier, str)
        assert isinstance(result.reasons, list)

    def test_tier_needs_info_range(self):
        """Score in 50–74 → needs_info tier."""
        from app.recipes.scoring import score_recipe
        # Half good, half bad, no servings → lower score
        ingredients = (
            [_good_ingredient() for _ in range(5)]
            + [_bad_ingredient() for _ in range(5)]
        )
        recipe = StubRecipe(servings=None, ingredients=ingredients)
        result = score_recipe(recipe)
        if 50 <= result.score < 75:
            assert result.tier == "needs_info"

    def test_unparsed_lines_reason_included(self):
        """Unparsed lines count reported in reasons."""
        from app.recipes.scoring import score_recipe
        bad = [_bad_ingredient() for _ in range(3)]
        good = [_good_ingredient() for _ in range(7)]
        recipe = StubRecipe(servings="4", ingredients=bad + good)
        result = score_recipe(recipe)
        # Some reason about unparsed lines expected
        has_unparsed_reason = any(
            "unparsed" in r or "parse_coverage" in r for r in result.reasons
        )
        assert has_unparsed_reason

    def test_unit_validity_full_score_no_units(self):
        """If no ingredients require units, unit_validity = 15 (no penalty)."""
        from app.recipes.scoring import score_recipe
        # Count-style ingredients without units are fine
        ingredients = [
            StubIngredient(
                quantity=2.0, unit=None, name="eggs",
                category="pantry", confidence=0.8, needs_review=False,
            )
        ]
        recipe = StubRecipe(servings="2", ingredients=ingredients)
        result = score_recipe(recipe)
        # Should NOT lose points on unit_validity
        assert result.score >= 85
