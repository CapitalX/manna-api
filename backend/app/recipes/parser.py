# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Ingredient line parser.

parse_line(raw: str) -> ParsedIngredient

Primary: ingredient_parser_nlp.parse_ingredient() (CRF model, ~6 MB).
Fallback: in-house regex parser when NLP import fails or returns low confidence.

The NLP import is wrapped in try/except ImportError so the service boots
without the wheel — every call goes to the regex fallback in that case.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.recipes.units import normalize_unit

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ParsedIngredient:
    quantity: float | None = None
    unit: str | None = None
    name: str | None = None
    confidence: float = 0.0
    needs_review: bool = True


# ---------------------------------------------------------------------------
# Unicode fraction map
# ---------------------------------------------------------------------------

_UNICODE_FRACTIONS: dict[str, float] = {
    "½": 0.5,
    "⅓": 1 / 3,
    "⅔": 2 / 3,
    "¼": 0.25,
    "¾": 0.75,
    "⅕": 0.2,
    "⅖": 0.4,
    "⅗": 0.6,
    "⅘": 0.8,
    "⅙": 1 / 6,
    "⅚": 5 / 6,
    "⅛": 0.125,
    "⅜": 0.375,
    "⅝": 0.625,
    "⅞": 0.875,
}

# ---------------------------------------------------------------------------
# NLP parser (optional)
# ---------------------------------------------------------------------------

try:
    from ingredient_parser import parse_ingredient as _nlp_parse  # type: ignore[import]
    _NLP_AVAILABLE = True
except ImportError:
    _NLP_AVAILABLE = False


def _try_nlp(raw: str) -> ParsedIngredient | None:
    """Attempt NLP parse. Returns None if unavailable, raises, or low-confidence."""
    if not _NLP_AVAILABLE:
        return None
    try:
        result = _nlp_parse(raw)

        # Extract quantity
        qty: float | None = None
        if result.amount:
            # ingredient_parser returns amount as a list of ParsedAmount objects
            # Each has .quantity (str) and .unit (str)
            first_amount = result.amount[0]
            raw_qty = first_amount.quantity if hasattr(first_amount, "quantity") else None
            if raw_qty:
                qty = _parse_quantity_str(str(raw_qty))

        # Extract unit from first amount
        raw_unit: str | None = None
        if result.amount and hasattr(result.amount[0], "unit"):
            raw_unit = result.amount[0].unit

        canonical_unit: str | None = None
        unit_needs_review = False
        if raw_unit and raw_unit.strip():
            canonical_unit, unit_needs_review = normalize_unit(raw_unit)

        # Extract name
        name: str | None = None
        if hasattr(result, "name") and result.name:
            name_obj = result.name
            if isinstance(name_obj, list):
                name = " ".join(n.text for n in name_obj if hasattr(n, "text")).strip() or None
            elif hasattr(name_obj, "text"):
                name = name_obj.text.strip() or None
            else:
                name = str(name_obj).strip() or None

        # Compute confidence
        # Use NLP confidence if available; otherwise compute from parse completeness
        confidence = 0.0
        if hasattr(result, "confidence") and result.confidence is not None:
            confidence = float(result.confidence)
        else:
            # Estimate confidence from how much we extracted
            has_qty = qty is not None
            has_name = bool(name)
            confidence = 0.5 * has_qty + 0.5 * has_name

        # Low-confidence: fall through to regex
        if confidence < 0.3 and not (qty and name):
            return None

        needs_review = (qty is None) or (not name) or unit_needs_review

        return ParsedIngredient(
            quantity=qty,
            unit=canonical_unit,
            name=name,
            confidence=confidence,
            needs_review=needs_review,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Regex-based fallback parser
# ---------------------------------------------------------------------------

# Pinch pattern: "a pinch of salt"
_PINCH_RE = re.compile(
    r"^(?:a\s+)?pinch(?:es)?\s+of\s+(.+)$", re.IGNORECASE
)

# Main pattern: optional quantity + optional unit + name
# Quantity: integer, decimal, fraction (1/2), mixed number (1 1/2), or unicode fraction
_QTY_PART = r"(?:[½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]|\d+(?:\.\d+)?(?:/\d+)?(?:\s+\d+/\d+)?)"
_UNIT_WORDS = (
    r"cups?|tbsp\.?|tsp\.?|tablespoons?|teaspoons?|"
    r"g|grams?|oz|ounces?|ml|milliliters?|millilitres?|"
    r"l|liters?|litres?|lbs?|pounds?|"
    r"pinch(?:es)?|cloves?|count|pieces?|"
    r"cans?|package[ds]?|bunch(?:es)?|slice[ds]?|"
    r"inch(?:es)?|quart[ds]?|pint[ds]?"
)
_MAIN_RE = re.compile(
    rf"^({_QTY_PART})\s+({_UNIT_WORDS})\s+(?:of\s+)?(.+?)(?:,.*)?$",
    re.IGNORECASE,
)

# Quantity-only (no unit): "2 eggs"
_QTY_ONLY_RE = re.compile(
    rf"^({_QTY_PART})\s+(.+?)(?:,.*)?$",
    re.IGNORECASE,
)


def _parse_quantity_str(s: str) -> float | None:
    """Convert a quantity string to float. Handles: int, decimal, fraction, unicode."""
    if not s:
        return None

    # Check for unicode fraction character
    for char, val in _UNICODE_FRACTIONS.items():
        if char in s:
            # May be "1½" (mixed) — strip and add
            rest = s.replace(char, "").strip()
            try:
                return float(rest) + val if rest else val
            except ValueError:
                return val

    # Slash fraction: "1/2" or "3/4"
    slash_match = re.fullmatch(r"(\d+)\s*/\s*(\d+)", s.strip())
    if slash_match:
        num, den = int(slash_match.group(1)), int(slash_match.group(2))
        return num / den if den else None

    # Mixed number: "1 1/2" — already partially handled above via _QTY_PART matching
    mixed_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s+(\d+)\s*/\s*(\d+)", s.strip())
    if mixed_match:
        whole = float(mixed_match.group(1))
        num, den = int(mixed_match.group(2)), int(mixed_match.group(3))
        return whole + (num / den if den else 0)

    # Simple numeric
    try:
        return float(s.strip())
    except (ValueError, TypeError):
        return None


def _regex_parse(raw: str) -> ParsedIngredient:
    """Regex-based ingredient parser. Never raises."""
    if not raw or not raw.strip():
        return ParsedIngredient(needs_review=True, confidence=0.0, name=None)

    text = raw.strip()

    # Expand unicode fractions at start of string for mixed number handling
    for uf, val in _UNICODE_FRACTIONS.items():
        if text.startswith(uf):
            # Replace the unicode fraction with its decimal for matching
            text = f"{val}{text[len(uf):]}"
            break

    # "a pinch of X" pattern
    pinch_m = _PINCH_RE.match(text)
    if pinch_m:
        name = pinch_m.group(1).strip()
        return ParsedIngredient(
            quantity=None,
            unit="pinch",
            name=name,
            confidence=0.85,
            needs_review=False,
        )

    # Main pattern: qty + unit + name
    main_m = _MAIN_RE.match(text)
    if main_m:
        qty_str = main_m.group(1).strip()
        unit_raw = main_m.group(2).strip()
        name = main_m.group(3).strip()

        qty = _parse_quantity_str(qty_str)
        canonical_unit, unit_needs_review = normalize_unit(unit_raw)

        confidence = 0.85 if qty is not None else 0.5
        needs_review = unit_needs_review or qty is None

        return ParsedIngredient(
            quantity=qty,
            unit=canonical_unit,
            name=name,
            confidence=confidence,
            needs_review=needs_review,
        )

    # Quantity-only: "2 eggs" (no unit)
    qty_only_m = _QTY_ONLY_RE.match(text)
    if qty_only_m:
        qty_str = qty_only_m.group(1).strip()
        name = qty_only_m.group(2).strip()
        qty = _parse_quantity_str(qty_str)
        if qty is not None and name:
            return ParsedIngredient(
                quantity=qty,
                unit=None,
                name=name,
                confidence=0.65,
                needs_review=False,  # qty present, no unit is fine for count items
            )

    # No quantity — return name only, marked needs_review
    # Strip common prep phrases
    name = _strip_prep_phrases(text)
    return ParsedIngredient(
        quantity=None,
        unit=None,
        name=name or text,
        confidence=0.2,
        needs_review=True,
    )


def _strip_prep_phrases(text: str) -> str:
    """Strip trailing phrases like 'to taste', 'as needed', 'for garnish'."""
    phrases = ["to taste", "as needed", "for garnish", "optional", "for serving"]
    lower = text.lower()
    for phrase in phrases:
        if lower.endswith(phrase):
            text = text[: -len(phrase)].strip().rstrip(",").strip()
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_line(raw: str) -> ParsedIngredient:
    """Parse a single ingredient line.

    Tries the NLP parser first; falls back to regex on failure or low confidence.
    Never raises.
    """
    # NLP pass — handles well-structured lines with high accuracy
    nlp_result = _try_nlp(raw)
    if nlp_result is not None and nlp_result.confidence >= 0.4:
        return nlp_result

    # Regex fallback
    return _regex_parse(raw)
