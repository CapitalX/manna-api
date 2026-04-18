# SPDX-License-Identifier: AGPL-3.0-or-later
"""
TDD tests for app/recipes/categorizer.py

Written FIRST — tests fail until implementation exists.
Covers: known ingredients map to correct buckets, longest-match ordering,
 unknown ingredients → "other", case insensitivity.
"""
import pytest
from app.recipes.categorizer import categorize


class TestCategorize:
    # --- Meat ---
    def test_chicken_breast(self):
        cat, conf = categorize("chicken breast")
        assert cat == "meat"
        assert conf > 0.5

    def test_ground_beef(self):
        cat, conf = categorize("ground beef")
        assert cat == "meat"
        assert conf > 0.5

    def test_salmon_fillet(self):
        cat, conf = categorize("salmon fillet")
        assert cat == "meat"
        assert conf > 0.5

    def test_turkey(self):
        cat, conf = categorize("turkey")
        assert cat == "meat"
        assert conf > 0.5

    # --- Dairy ---
    def test_milk(self):
        cat, conf = categorize("milk")
        assert cat == "dairy"
        assert conf > 0.5

    def test_butter(self):
        cat, conf = categorize("butter")
        assert cat == "dairy"
        assert conf > 0.5

    def test_greek_yogurt(self):
        cat, conf = categorize("greek yogurt")
        assert cat == "dairy"
        assert conf > 0.5

    def test_parmesan_cheese(self):
        cat, conf = categorize("parmesan cheese")
        assert cat == "dairy"
        assert conf > 0.5

    # --- Vegetables ---
    def test_broccoli(self):
        cat, conf = categorize("broccoli")
        assert cat == "vegetables"
        assert conf > 0.5

    def test_spinach(self):
        cat, conf = categorize("spinach")
        assert cat == "vegetables"
        assert conf > 0.5

    def test_carrots(self):
        cat, conf = categorize("carrots")
        assert cat == "vegetables"
        assert conf > 0.5

    def test_onion(self):
        cat, conf = categorize("onion")
        assert cat == "vegetables"
        assert conf > 0.5

    # --- Fruits ---
    def test_apple(self):
        cat, conf = categorize("apple")
        assert cat == "fruits"
        assert conf > 0.5

    def test_blueberries(self):
        cat, conf = categorize("blueberries")
        assert cat == "fruits"
        assert conf > 0.5

    # --- Legumes ---
    def test_chickpeas(self):
        cat, conf = categorize("chickpeas")
        assert cat == "legumes"
        assert conf > 0.5

    def test_black_beans(self):
        cat, conf = categorize("black beans")
        assert cat == "legumes"
        assert conf > 0.5

    def test_lentils(self):
        cat, conf = categorize("lentils")
        assert cat == "legumes"
        assert conf > 0.5

    # --- Whole grains ---
    def test_brown_rice(self):
        cat, conf = categorize("brown rice")
        assert cat == "whole_grains"
        assert conf > 0.5

    def test_oats(self):
        cat, conf = categorize("oats")
        assert cat == "whole_grains"
        assert conf > 0.5

    def test_quinoa(self):
        cat, conf = categorize("quinoa")
        assert cat == "whole_grains"
        assert conf > 0.5

    # --- Nuts / seeds ---
    def test_almonds(self):
        cat, conf = categorize("almonds")
        assert cat == "nuts_seeds"
        assert conf > 0.5

    def test_chia_seeds(self):
        cat, conf = categorize("chia seeds")
        assert cat == "nuts_seeds"
        assert conf > 0.5

    # --- Oils ---
    def test_olive_oil(self):
        cat, conf = categorize("olive oil")
        assert cat == "oils"
        assert conf > 0.5

    def test_coconut_oil(self):
        cat, conf = categorize("coconut oil")
        assert cat == "oils"
        assert conf > 0.5

    # --- Herbs / spices ---
    def test_cinnamon(self):
        cat, conf = categorize("cinnamon")
        assert cat == "herbs_spices"
        assert conf > 0.5

    def test_basil(self):
        cat, conf = categorize("basil")
        assert cat == "herbs_spices"
        assert conf > 0.5

    def test_garlic(self):
        cat, conf = categorize("garlic")
        assert cat == "herbs_spices"
        assert conf > 0.5

    # --- Pantry ---
    def test_flour(self):
        cat, conf = categorize("flour")
        assert cat == "pantry"
        assert conf > 0.5

    def test_sugar(self):
        cat, conf = categorize("sugar")
        assert cat == "pantry"
        assert conf > 0.5

    def test_vegetable_broth(self):
        cat, conf = categorize("vegetable broth")
        assert cat == "pantry"
        assert conf > 0.5

    # --- Other (unknown) ---
    def test_unicorn_dust(self):
        cat, conf = categorize("unicorn dust")
        assert cat == "other"
        assert conf == 0.0

    def test_empty_string(self):
        cat, conf = categorize("")
        assert cat == "other"
        assert conf == 0.0

    # --- Longest match first (brown rice > rice) ---
    def test_longest_match_brown_rice(self):
        """'brown rice' should match 'whole_grains' via longest-match, not just 'rice'."""
        cat, conf = categorize("brown rice")
        assert cat == "whole_grains"

    # --- Case insensitivity ---
    def test_case_insensitive(self):
        cat1, _ = categorize("Chicken Breast")
        cat2, _ = categorize("chicken breast")
        assert cat1 == cat2

    # --- Partial name match (name contains keyword) ---
    def test_fresh_basil(self):
        cat, conf = categorize("fresh basil")
        assert cat == "herbs_spices"

    def test_canned_chickpeas(self):
        cat, conf = categorize("canned chickpeas")
        assert cat == "legumes"
