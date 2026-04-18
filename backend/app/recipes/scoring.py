# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Recipe quality scoring module.

score_recipe(recipe) -> ScoreResult

Pure function — no side effects. Caller persists the result.

Formula (D4 from Phase 15 spec):
  parse_coverage    (40 pts) = 40 * (lines_parsed_with_qty_and_name / total_lines)
  unit_validity     (15 pts) = 15 * (lines_with_normalized_unit / lines_with_any_unit)
                             -- 15 if no units required (count-style ingredients are fine)
  servings_present  (15 pts) = 15 if recipe.servings contains a digit, else 0
  name_canonical    (15 pts) = 15 * (lines_with_category != "other" / total_lines)
  categorization    (15 pts) = 15 if all lines have a category assigned (any category),
                             else 0. In MVP the parser always assigns a category, so
                             this is effectively 15 for all parsed recipes.

Tier thresholds:
  verified:    score >= 90 AND user_verified == True
  processable: score >= 75
  needs_info:  score >= 50
  draft:       else
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class ScoreResult:
    score: int
    tier: str
    reasons: list[str]


def _has_digit(s: str | None) -> bool:
    """Return True if the string contains at least one digit."""
    return bool(s and re.search(r"\d", s))


def score_recipe(recipe) -> ScoreResult:
    """Compute quality score for a recipe.

    Args:
        recipe: A Recipe-like object with `servings`, `user_verified`, and
                `ingredients` (list of ingredient-like objects with
                `quantity`, `unit`, `name`, `category`, `needs_review`).

    Returns:
        ScoreResult(score, tier, reasons)
    """
    reasons: list[str] = []
    ingredients = recipe.ingredients if hasattr(recipe, "ingredients") else []
    total = len(ingredients)

    # ------------------------------------------------------------------
    # Component 1: parse_coverage (40 pts)
    # A line is "parsed" when both qty and name are present.
    # ------------------------------------------------------------------
    if total == 0:
        parse_coverage_pts = 0
        reasons.append("no_ingredients")
    else:
        parsed_lines = sum(
            1 for ing in ingredients
            if ing.quantity is not None and ing.name is not None
        )
        parse_ratio = parsed_lines / total
        parse_coverage_pts = round(40 * parse_ratio)
        unparsed = total - parsed_lines
        if unparsed > 0:
            reasons.append(f"{unparsed}_unparsed_lines")
        if parse_ratio < 1.0:
            pct = round(parse_ratio * 100)
            reasons.append(f"parse_coverage_{pct}pct")

    # ------------------------------------------------------------------
    # Component 2: unit_validity (15 pts)
    # Lines that have a quantity but no unit are treated as count-style
    # (e.g. "2 eggs") — no penalty. Only penalise when raw unit text is
    # present but couldn't be normalized (i.e. unit is None but some
    # indicator that a unit was attempted).
    #
    # Simpler MVP rule: full 15 pts if no ingredient has needs_review=True
    # purely because of unit issues. We use needs_review as the proxy:
    # if an ingredient has a qty but is marked needs_review AND has no
    # name, that's a parse failure already penalised above.
    #
    # Practical implementation: 15 pts if all ingredients with a quantity
    # also have a valid (normalized) unit OR have unit=None (count-style).
    # Penalty only when an ingredient has neither name nor quantity
    # (already counted in parse_coverage).
    # ------------------------------------------------------------------
    # For unit_validity we only look at ingredients that have a quantity.
    with_qty = [ing for ing in ingredients if ing.quantity is not None]
    if not with_qty:
        # No ingredients have quantities → no unit validity score possible
        # but also no penalty (already hurt by parse_coverage)
        unit_validity_pts = 15
    else:
        # Lines with a quantity and either a valid unit OR unit=None (count)
        valid_unit_lines = sum(
            1 for ing in with_qty
            if ing.unit is not None or (ing.unit is None and ing.name is not None)
        )
        unit_ratio = valid_unit_lines / len(with_qty)
        unit_validity_pts = round(15 * unit_ratio)

    # ------------------------------------------------------------------
    # Component 3: servings_present (15 pts)
    # ------------------------------------------------------------------
    if _has_digit(getattr(recipe, "servings", None)):
        servings_pts = 15
    else:
        servings_pts = 0
        reasons.append("no_servings")

    # ------------------------------------------------------------------
    # Component 4: name_canonical (15 pts)
    # Lines whose category is not "other" are canonical.
    # ------------------------------------------------------------------
    if total == 0:
        name_canonical_pts = 0
    else:
        canonical_lines = sum(
            1 for ing in ingredients if ing.category != "other"
        )
        canonical_ratio = canonical_lines / total
        name_canonical_pts = round(15 * canonical_ratio)
        other_count = total - canonical_lines
        if other_count > 0:
            reasons.append(f"{other_count}_other_category")

    # ------------------------------------------------------------------
    # Component 5: categorization (15 pts)
    # MVP: every line gets a category (even "other"), so this is always 15
    # for recipes that completed the parse pass. For recipes with no
    # ingredients (total == 0), give 0.
    # ------------------------------------------------------------------
    categorization_pts = 15 if total > 0 else 0

    # ------------------------------------------------------------------
    # Total score (clamped 0–100)
    # ------------------------------------------------------------------
    raw_score = (
        parse_coverage_pts
        + unit_validity_pts
        + servings_pts
        + name_canonical_pts
        + categorization_pts
    )
    score = max(0, min(100, raw_score))

    # ------------------------------------------------------------------
    # Tier
    # ------------------------------------------------------------------
    user_verified = getattr(recipe, "user_verified", False)
    if score >= 90 and user_verified:
        tier = "verified"
    elif score >= 75:
        tier = "processable"
    elif score >= 50:
        tier = "needs_info"
    else:
        tier = "draft"

    return ScoreResult(score=score, tier=tier, reasons=reasons)
