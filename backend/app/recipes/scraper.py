# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Recipe scraper module — wraps the open-source `recipe-scrapers` library
(the same engine Mealie uses) to extract structured recipe data from URLs.
"""
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl

from recipe_scrapers import scrape_html
import httpx

# ---------------------------------------------------------------------------
# Tracking / campaign query parameters to strip during URL normalization.
# All utm_* variants are handled by prefix matching; these are exact names.
# ---------------------------------------------------------------------------
_STRIP_PARAMS = frozenset(
    ["fbclid", "gclid", "mc_cid", "mc_eid", "ref"]
)


def normalize_source_url(raw: str) -> str:
    """
    Normalize a recipe URL for deduplication.

    Rules applied (per Phase 14 spec):
    - Lowercase scheme and host.
    - Strip fragment (#...).
    - Remove tracking query params: all utm_* prefixed params, plus the
      exact names in _STRIP_PARAMS (fbclid, gclid, mc_cid, mc_eid, ref).
    - Preserve all other query params.
    - Remove trailing slash from path (unless path is just "/", which is
      collapsed to empty string for a cleaner canonical form).
    """
    parsed = urlparse(raw)

    # Lowercase scheme and host
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip fragment
    fragment = ""

    # Filter tracking query params
    kept_params = [
        (k, v) for k, v in parse_qsl(parsed.query)
        if k.lower() not in _STRIP_PARAMS and not k.lower().startswith("utm_")
    ]
    query = urlencode(kept_params)

    # Remove trailing slash from path
    path = parsed.path.rstrip("/")

    return urlunparse((scheme, netloc, path, parsed.params, query, fragment))


@dataclass
class ScrapedRecipe:
    title: str
    description: str | None
    image_url: str | None
    prep_time_minutes: int | None
    cook_time_minutes: int | None
    total_time_minutes: int | None
    servings: str | None
    ingredients: list[str]
    instructions: list[str]
    source_url: str


def _safe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def scrape_recipe_url(url: str) -> ScrapedRecipe:
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        response = await client.get(url, headers={"User-Agent": "Manna/1.0"})
        response.raise_for_status()

    scraper = scrape_html(html=response.text, org_url=url)

    return ScrapedRecipe(
        title=scraper.title(),
        description=_safe_attr(scraper, "description"),
        image_url=_safe_attr(scraper, "image"),
        prep_time_minutes=_safe_int(_safe_attr(scraper, "prep_time")),
        cook_time_minutes=_safe_int(_safe_attr(scraper, "cook_time")),
        total_time_minutes=_safe_int(_safe_attr(scraper, "total_time")),
        servings=_safe_attr(scraper, "yields"),
        ingredients=scraper.ingredients(),
        instructions=_split_instructions(scraper.instructions()),
        source_url=url,
    )


def _safe_attr(scraper, attr: str) -> str | None:
    try:
        val = getattr(scraper, attr)()
        return val if val else None
    except Exception:
        return None


def _split_instructions(raw: str) -> list[str]:
    if not raw:
        return []
    return [step.strip() for step in raw.split("\n") if step.strip()]
