# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Unit normalization for ingredient parsing.

normalize_unit(raw: str | None) -> tuple[str | None, bool]
  Returns (canonical_unit, needs_review).
  needs_review is True when the unit is unrecognized.

Canonical unit set: g, oz, ml, L, tbsp, tsp, cup, count, pinch, lb, clove.
"""
from __future__ import annotations

# Map of lowercase aliases → canonical unit.
# Entries with trailing "." and plural "s" are handled programmatically below
# but explicit aliases are cleaner for ambiguous cases.
_ALIAS_MAP: dict[str, str] = {
    # tbsp
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tbsp": "tbsp",
    "tbs": "tbsp",
    "t": "tbsp",

    # tsp
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tsp": "tsp",
    "ts": "tsp",

    # g
    "gram": "g",
    "grams": "g",
    "g": "g",

    # oz
    "ounce": "oz",
    "ounces": "oz",
    "oz": "oz",

    # ml
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "ml": "ml",

    # L
    "liter": "L",
    "liters": "L",
    "litre": "L",
    "litres": "L",
    "l": "L",

    # cup
    "cup": "cup",
    "cups": "cup",
    "c": "cup",

    # lb
    "pound": "lb",
    "pounds": "lb",
    "lb": "lb",
    "lbs": "lb",

    # pinch
    "pinch": "pinch",
    "pinches": "pinch",

    # clove
    "clove": "clove",
    "cloves": "clove",

    # count
    "count": "count",
    "piece": "count",
    "pieces": "count",
    "item": "count",
    "items": "count",
}


def normalize_unit(raw: str | None) -> tuple[str | None, bool]:
    """Normalize a raw unit string to a canonical unit.

    Returns:
        (canonical_unit, needs_review)
        - canonical_unit: one of the canonical strings, or None if unrecognized.
        - needs_review: True when the unit is not recognized.
    """
    if raw is None or not isinstance(raw, str):
        return (None, True)

    cleaned = raw.strip().rstrip(".")
    if not cleaned:
        return (None, True)

    # Try exact lowercase match first (handles "T" → tbsp correctly with
    # the explicit alias, then falls to lowercase for everything else)
    canonical = _ALIAS_MAP.get(cleaned) or _ALIAS_MAP.get(cleaned.lower())
    if canonical:
        return (canonical, False)

    return (None, True)
