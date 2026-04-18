# SPDX-License-Identifier: AGPL-3.0-or-later
"""
TDD tests for app/recipes/units.py

Written FIRST — tests fail until implementation exists.
Covers: all canonical aliases, case-insensitive, plural forms, unknown units.
"""
import pytest
from app.recipes.units import normalize_unit


class TestNormalizeUnit:
    # --- tbsp aliases ---
    def test_tablespoon(self):
        assert normalize_unit("tablespoon") == ("tbsp", False)

    def test_tablespoons(self):
        assert normalize_unit("tablespoons") == ("tbsp", False)

    def test_tbsp(self):
        assert normalize_unit("tbsp") == ("tbsp", False)

    def test_T_uppercase(self):
        assert normalize_unit("T") == ("tbsp", False)

    # --- tsp aliases ---
    def test_teaspoon(self):
        assert normalize_unit("teaspoon") == ("tsp", False)

    def test_teaspoons(self):
        assert normalize_unit("teaspoons") == ("tsp", False)

    def test_tsp(self):
        assert normalize_unit("tsp") == ("tsp", False)

    # --- g aliases ---
    def test_gram(self):
        assert normalize_unit("gram") == ("g", False)

    def test_grams(self):
        assert normalize_unit("grams") == ("g", False)

    def test_g(self):
        assert normalize_unit("g") == ("g", False)

    # --- oz aliases ---
    def test_ounce(self):
        assert normalize_unit("ounce") == ("oz", False)

    def test_ounces(self):
        assert normalize_unit("ounces") == ("oz", False)

    def test_oz(self):
        assert normalize_unit("oz") == ("oz", False)

    # --- ml aliases ---
    def test_milliliter(self):
        assert normalize_unit("milliliter") == ("ml", False)

    def test_milliliters(self):
        assert normalize_unit("milliliters") == ("ml", False)

    def test_ml(self):
        assert normalize_unit("ml") == ("ml", False)

    # --- L aliases ---
    def test_liter(self):
        assert normalize_unit("liter") == ("L", False)

    def test_litre(self):
        assert normalize_unit("litre") == ("L", False)

    def test_liters(self):
        assert normalize_unit("liters") == ("L", False)

    def test_L(self):
        assert normalize_unit("L") == ("L", False)

    # --- cup aliases ---
    def test_cup(self):
        assert normalize_unit("cup") == ("cup", False)

    def test_cups(self):
        assert normalize_unit("cups") == ("cup", False)

    # --- lb aliases ---
    def test_pound(self):
        assert normalize_unit("pound") == ("lb", False)

    def test_pounds(self):
        assert normalize_unit("pounds") == ("lb", False)

    def test_lbs(self):
        assert normalize_unit("lbs") == ("lb", False)

    def test_lb(self):
        assert normalize_unit("lb") == ("lb", False)

    # --- pinch ---
    def test_pinch(self):
        assert normalize_unit("pinch") == ("pinch", False)

    def test_pinches(self):
        assert normalize_unit("pinches") == ("pinch", False)

    # --- clove ---
    def test_clove(self):
        assert normalize_unit("clove") == ("clove", False)

    def test_cloves(self):
        assert normalize_unit("cloves") == ("clove", False)

    # --- count ---
    def test_count(self):
        assert normalize_unit("count") == ("count", False)

    # --- Case insensitivity ---
    def test_uppercase_tablespoons(self):
        assert normalize_unit("Tablespoons") == ("tbsp", False)

    def test_mixed_case_ounces(self):
        assert normalize_unit("Ounces") == ("oz", False)

    # --- Trailing dot stripped ---
    def test_trailing_dot(self):
        assert normalize_unit("tsp.") == ("tsp", False)

    # --- Unknown units → needs_review ---
    def test_handful_needs_review(self):
        result = normalize_unit("handful")
        assert result[0] is None
        assert result[1] is True

    def test_splash_needs_review(self):
        result = normalize_unit("splash")
        assert result[0] is None
        assert result[1] is True

    def test_empty_string_needs_review(self):
        result = normalize_unit("")
        assert result[1] is True

    def test_none_input_needs_review(self):
        result = normalize_unit(None)  # type: ignore[arg-type]
        assert result[1] is True
