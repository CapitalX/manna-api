# SPDX-License-Identifier: AGPL-3.0-or-later
"""
TDD tests for app/recipes/parser.py

Written FIRST — these tests fail until the implementation exists.
Covers: common units, unicode fractions, "to taste" edge case,
confidence thresholds, and the regex fallback path.
"""
import pytest
from app.recipes.parser import parse_line


class TestParseLineBasic:
    def test_quantity_unit_name(self):
        """Standard: '2 cups olive oil' → structured."""
        result = parse_line("2 cups olive oil")
        assert result.quantity == pytest.approx(2.0)
        assert result.unit == "cup"
        assert "olive oil" in result.name.lower()
        assert result.confidence >= 0.6
        assert result.needs_review is False

    def test_decimal_quantity(self):
        """'1.5 tbsp honey' → quantity = 1.5."""
        result = parse_line("1.5 tbsp honey")
        assert result.quantity == pytest.approx(1.5)
        assert result.unit == "tbsp"
        assert "honey" in result.name.lower()

    def test_unicode_fraction_half(self):
        """'½ tsp cinnamon' → quantity = 0.5."""
        result = parse_line("½ tsp cinnamon")
        assert result.quantity == pytest.approx(0.5)
        assert result.unit == "tsp"
        assert "cinnamon" in result.name.lower()

    def test_unicode_fraction_quarter(self):
        """'¼ cup milk' → quantity = 0.25."""
        result = parse_line("¼ cup milk")
        assert result.quantity == pytest.approx(0.25)
        assert result.unit == "cup"

    def test_unicode_fraction_three_quarters(self):
        """'¾ oz dark chocolate' → quantity = 0.75."""
        result = parse_line("¾ oz dark chocolate")
        assert result.quantity == pytest.approx(0.75)
        assert result.unit == "oz"

    def test_fraction_slash(self):
        """'1/2 tsp salt' → quantity = 0.5."""
        result = parse_line("1/2 tsp salt")
        assert result.quantity == pytest.approx(0.5)

    def test_mixed_number(self):
        """'1 1/2 cups flour' → quantity = 1.5."""
        result = parse_line("1 1/2 cups flour")
        assert result.quantity == pytest.approx(1.5)

    def test_no_quantity_to_taste(self):
        """'salt to taste' → no quantity, no unit, needs_review=True."""
        result = parse_line("salt to taste")
        assert result.quantity is None
        assert result.unit is None
        assert "salt" in result.name.lower()
        assert result.needs_review is True

    def test_no_quantity_bare_name(self):
        """'fresh parsley' with no qty → needs_review=True."""
        result = parse_line("fresh parsley")
        assert result.quantity is None
        assert result.needs_review is True
        assert result.name is not None
        assert len(result.name) > 0

    def test_tablespoon_variants(self):
        """'2 tablespoons butter' → unit normalized to 'tbsp'."""
        result = parse_line("2 tablespoons butter")
        assert result.unit == "tbsp"

    def test_gram_variant(self):
        """'100 grams chickpeas' → unit normalized to 'g'."""
        result = parse_line("100 grams chickpeas")
        assert result.unit == "g"

    def test_pound_variant(self):
        """'1 lb ground beef' → unit normalized to 'lb'."""
        result = parse_line("1 lb ground beef")
        assert result.unit == "lb"

    def test_pinch_unit(self):
        """'a pinch of salt' → unit = 'pinch', name contains 'salt'."""
        result = parse_line("a pinch of salt")
        assert result.unit == "pinch"
        assert "salt" in result.name.lower()

    def test_clove_unit(self):
        """'3 cloves garlic' → unit = 'clove'."""
        result = parse_line("3 cloves garlic")
        assert result.unit == "clove"
        assert "garlic" in result.name.lower()

    def test_returns_dataclass(self):
        """parse_line always returns a ParsedIngredient with required fields."""
        result = parse_line("2 cups water")
        assert hasattr(result, "quantity")
        assert hasattr(result, "unit")
        assert hasattr(result, "name")
        assert hasattr(result, "confidence")
        assert hasattr(result, "needs_review")

    def test_empty_string_does_not_crash(self):
        """Empty string → returns a ParsedIngredient with needs_review=True."""
        result = parse_line("")
        assert result.needs_review is True

    def test_count_unit(self):
        """'2 eggs' — no explicit unit → unit may be None or 'count', name contains 'eggs'."""
        result = parse_line("2 eggs")
        # eggs may be parsed as count or unitless — either is fine
        assert result.quantity == pytest.approx(2.0)
        assert result.name is not None
        assert "egg" in result.name.lower()
