# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Ingredient categorizer.

categorize(name: str) -> tuple[str, float]
  Returns (category, confidence).
  Uses a keyword dict with longest-match-first ordering.
  Falls back to ("other", 0.0) on no match.

Category vocabulary extends Daniel Fast categories with four shopping extras:
  Original: whole_grains, fruits, vegetables, legumes, nuts_seeds, oils, herbs_spices
  Added:    meat, dairy, pantry, other
"""
from __future__ import annotations

# Keyword → category mapping.
# Keys are lowercased; matching is substring/longest-match over the ingredient name.
_KEYWORD_CATEGORY: list[tuple[str, str]] = [
    # --- Meat (longest specific names first) ---
    ("chicken breast", "meat"),
    ("ground beef", "meat"),
    ("ground turkey", "meat"),
    ("ground chicken", "meat"),
    ("ground pork", "meat"),
    ("pork chop", "meat"),
    ("salmon fillet", "meat"),
    ("tuna steak", "meat"),
    ("lamb chop", "meat"),
    ("beef steak", "meat"),
    ("sirloin", "meat"),
    ("chicken thigh", "meat"),
    ("chicken drumstick", "meat"),
    ("chicken wing", "meat"),
    ("pork belly", "meat"),
    ("pork tenderloin", "meat"),
    ("bacon", "meat"),
    ("sausage", "meat"),
    ("ham", "meat"),
    ("salami", "meat"),
    ("pepperoni", "meat"),
    ("prosciutto", "meat"),
    ("turkey", "meat"),
    ("chicken", "meat"),
    ("beef", "meat"),
    ("pork", "meat"),
    ("lamb", "meat"),
    ("salmon", "meat"),
    ("tuna", "meat"),
    ("shrimp", "meat"),
    ("crab", "meat"),
    ("lobster", "meat"),
    ("cod", "meat"),
    ("tilapia", "meat"),
    ("halibut", "meat"),
    ("sardine", "meat"),
    ("anchovy", "meat"),
    ("venison", "meat"),
    ("bison", "meat"),

    # --- Dairy (longest specific names first) ---
    ("cream cheese", "dairy"),
    ("cottage cheese", "dairy"),
    ("parmesan cheese", "dairy"),
    ("cheddar cheese", "dairy"),
    ("mozzarella cheese", "dairy"),
    ("ricotta cheese", "dairy"),
    ("feta cheese", "dairy"),
    ("greek yogurt", "dairy"),
    ("heavy cream", "dairy"),
    ("sour cream", "dairy"),
    ("cream", "dairy"),
    ("yogurt", "dairy"),
    ("cheese", "dairy"),
    ("butter", "dairy"),
    ("milk", "dairy"),
    ("ghee", "dairy"),
    ("kefir", "dairy"),
    ("whey", "dairy"),

    # --- Vegetables ---
    ("bell pepper", "vegetables"),
    ("sweet potato", "vegetables"),
    ("green bean", "vegetables"),
    ("brussel sprout", "vegetables"),
    ("brussels sprout", "vegetables"),
    ("bok choy", "vegetables"),
    ("cherry tomato", "vegetables"),
    ("roma tomato", "vegetables"),
    ("sun-dried tomato", "vegetables"),
    ("broccoli", "vegetables"),
    ("spinach", "vegetables"),
    ("kale", "vegetables"),
    ("arugula", "vegetables"),
    ("lettuce", "vegetables"),
    ("cabbage", "vegetables"),
    ("carrot", "vegetables"),
    ("celery", "vegetables"),
    ("cucumber", "vegetables"),
    ("zucchini", "vegetables"),
    ("eggplant", "vegetables"),
    ("asparagus", "vegetables"),
    ("artichoke", "vegetables"),
    ("beet", "vegetables"),
    ("cauliflower", "vegetables"),
    ("peas", "vegetables"),
    ("corn", "vegetables"),
    ("tomato", "vegetables"),
    ("onion", "vegetables"),
    ("leek", "vegetables"),
    ("shallot", "vegetables"),
    ("radish", "vegetables"),
    ("turnip", "vegetables"),
    ("parsnip", "vegetables"),
    ("mushroom", "vegetables"),
    ("squash", "vegetables"),
    ("pumpkin", "vegetables"),
    ("okra", "vegetables"),
    ("fennel", "vegetables"),
    ("endive", "vegetables"),
    ("watercress", "vegetables"),
    ("rocket", "vegetables"),
    ("swiss chard", "vegetables"),
    ("collard", "vegetables"),

    # --- Fruits ---
    ("lemon juice", "fruits"),
    ("lime juice", "fruits"),
    ("orange juice", "fruits"),
    ("dried cranberry", "fruits"),
    ("dried apricot", "fruits"),
    ("dried fig", "fruits"),
    ("dried mango", "fruits"),
    ("medjool date", "fruits"),
    ("blueberry", "fruits"),
    ("blueberri", "fruits"),   # catches "blueberries"
    ("strawberry", "fruits"),
    ("strawberri", "fruits"),  # catches "strawberries"
    ("raspberry", "fruits"),
    ("raspberri", "fruits"),   # catches "raspberries"
    ("blackberry", "fruits"),
    ("blackberri", "fruits"),  # catches "blackberries"
    ("cranberry", "fruits"),
    ("cranberri", "fruits"),   # catches "cranberries"
    ("cherry", "fruits"),
    ("grape", "fruits"),
    ("mango", "fruits"),
    ("pineapple", "fruits"),
    ("peach", "fruits"),
    ("plum", "fruits"),
    ("apricot", "fruits"),
    ("fig", "fruits"),
    ("banana", "fruits"),
    ("apple", "fruits"),
    ("pear", "fruits"),
    ("orange", "fruits"),
    ("lemon", "fruits"),
    ("lime", "fruits"),
    ("avocado", "fruits"),
    ("watermelon", "fruits"),
    ("cantaloupe", "fruits"),
    ("kiwi", "fruits"),
    ("pomegranate", "fruits"),
    ("date", "fruits"),

    # --- Legumes ---
    ("black bean", "legumes"),
    ("kidney bean", "legumes"),
    ("pinto bean", "legumes"),
    ("navy bean", "legumes"),
    ("cannellini bean", "legumes"),
    ("garbanzo bean", "legumes"),
    ("edamame", "legumes"),
    ("chickpea", "legumes"),
    ("lentil", "legumes"),
    ("split pea", "legumes"),
    ("black-eyed pea", "legumes"),
    ("mung bean", "legumes"),
    ("adzuki bean", "legumes"),
    ("fava bean", "legumes"),
    ("tofu", "legumes"),
    ("tempeh", "legumes"),
    ("bean", "legumes"),

    # --- Whole grains ---
    ("brown rice", "whole_grains"),
    ("wild rice", "whole_grains"),
    ("whole wheat pasta", "whole_grains"),
    ("whole grain bread", "whole_grains"),
    ("rolled oat", "whole_grains"),
    ("steel cut oat", "whole_grains"),
    ("whole wheat flour", "whole_grains"),
    ("wheat flour", "whole_grains"),
    ("buckwheat", "whole_grains"),
    ("millet", "whole_grains"),
    ("amaranth", "whole_grains"),
    ("teff", "whole_grains"),
    ("barley", "whole_grains"),
    ("farro", "whole_grains"),
    ("bulgur", "whole_grains"),
    ("spelt", "whole_grains"),
    ("kamut", "whole_grains"),
    ("quinoa", "whole_grains"),
    ("oatmeal", "whole_grains"),
    ("oat", "whole_grains"),
    ("rice", "whole_grains"),
    ("pasta", "whole_grains"),
    ("bread", "whole_grains"),
    ("tortilla", "whole_grains"),
    ("couscous", "whole_grains"),
    ("polenta", "whole_grains"),
    ("cornmeal", "whole_grains"),

    # --- Nuts / seeds ---
    ("sunflower seed", "nuts_seeds"),
    ("pumpkin seed", "nuts_seeds"),
    ("sesame seed", "nuts_seeds"),
    ("flax seed", "nuts_seeds"),
    ("hemp seed", "nuts_seeds"),
    ("poppy seed", "nuts_seeds"),
    ("chia seed", "nuts_seeds"),
    ("almond butter", "nuts_seeds"),
    ("peanut butter", "nuts_seeds"),
    ("tahini", "nuts_seeds"),
    ("almond", "nuts_seeds"),
    ("walnut", "nuts_seeds"),
    ("pecan", "nuts_seeds"),
    ("cashew", "nuts_seeds"),
    ("pistachio", "nuts_seeds"),
    ("macadamia", "nuts_seeds"),
    ("hazelnut", "nuts_seeds"),
    ("peanut", "nuts_seeds"),
    ("pine nut", "nuts_seeds"),
    ("chestnut", "nuts_seeds"),
    ("brazil nut", "nuts_seeds"),
    ("coconut flake", "nuts_seeds"),
    ("shredded coconut", "nuts_seeds"),

    # --- Oils ---
    ("olive oil", "oils"),
    ("coconut oil", "oils"),
    ("avocado oil", "oils"),
    ("sesame oil", "oils"),
    ("vegetable oil", "oils"),
    ("canola oil", "oils"),
    ("sunflower oil", "oils"),
    ("peanut oil", "oils"),
    ("flaxseed oil", "oils"),
    ("grapeseed oil", "oils"),
    ("truffle oil", "oils"),
    ("cooking spray", "oils"),
    ("oil", "oils"),

    # --- Herbs / spices ---
    ("black pepper", "herbs_spices"),
    ("red pepper flake", "herbs_spices"),
    ("cayenne pepper", "herbs_spices"),
    ("chili powder", "herbs_spices"),
    ("garlic powder", "herbs_spices"),
    ("onion powder", "herbs_spices"),
    ("ground cinnamon", "herbs_spices"),
    ("ground cumin", "herbs_spices"),
    ("ground turmeric", "herbs_spices"),
    ("ground ginger", "herbs_spices"),
    ("ground nutmeg", "herbs_spices"),
    ("ground cardamom", "herbs_spices"),
    ("dried oregano", "herbs_spices"),
    ("dried thyme", "herbs_spices"),
    ("dried rosemary", "herbs_spices"),
    ("dried basil", "herbs_spices"),
    ("dried parsley", "herbs_spices"),
    ("italian seasoning", "herbs_spices"),
    ("smoked paprika", "herbs_spices"),
    ("cinnamon", "herbs_spices"),
    ("cumin", "herbs_spices"),
    ("turmeric", "herbs_spices"),
    ("paprika", "herbs_spices"),
    ("oregano", "herbs_spices"),
    ("thyme", "herbs_spices"),
    ("rosemary", "herbs_spices"),
    ("basil", "herbs_spices"),
    ("parsley", "herbs_spices"),
    ("cilantro", "herbs_spices"),
    ("dill", "herbs_spices"),
    ("mint", "herbs_spices"),
    ("sage", "herbs_spices"),
    ("bay leaf", "herbs_spices"),
    ("ginger", "herbs_spices"),
    ("garlic", "herbs_spices"),
    ("saffron", "herbs_spices"),
    ("vanilla", "herbs_spices"),
    ("cardamom", "herbs_spices"),
    ("clove", "herbs_spices"),
    ("nutmeg", "herbs_spices"),
    ("allspice", "herbs_spices"),
    ("pepper", "herbs_spices"),
    ("salt", "herbs_spices"),

    # --- Pantry ---
    ("all-purpose flour", "pantry"),
    ("baking powder", "pantry"),
    ("baking soda", "pantry"),
    ("vegetable broth", "pantry"),
    ("chicken broth", "pantry"),
    ("beef broth", "pantry"),
    ("soy sauce", "pantry"),
    ("worcestershire sauce", "pantry"),
    ("hot sauce", "pantry"),
    ("tomato paste", "pantry"),
    ("tomato sauce", "pantry"),
    ("canned tomato", "pantry"),
    ("diced tomato", "pantry"),
    ("coconut milk", "pantry"),
    ("apple cider vinegar", "pantry"),
    ("balsamic vinegar", "pantry"),
    ("red wine vinegar", "pantry"),
    ("white wine vinegar", "pantry"),
    ("dijon mustard", "pantry"),
    ("maple syrup", "pantry"),
    ("honey", "pantry"),
    ("brown sugar", "pantry"),
    ("powdered sugar", "pantry"),
    ("corn starch", "pantry"),
    ("cornstarch", "pantry"),
    ("vanilla extract", "pantry"),
    ("cocoa powder", "pantry"),
    ("chocolate chip", "pantry"),
    ("dark chocolate", "pantry"),
    ("broth", "pantry"),
    ("stock", "pantry"),
    ("vinegar", "pantry"),
    ("mustard", "pantry"),
    ("ketchup", "pantry"),
    ("mayonnaise", "pantry"),
    ("flour", "pantry"),
    ("sugar", "pantry"),
    ("syrup", "pantry"),
    ("jam", "pantry"),
    ("jelly", "pantry"),
    ("water", "pantry"),
    ("egg", "pantry"),
]

# Sort by key length descending for longest-match-first
_SORTED_KEYWORDS: list[tuple[str, str]] = sorted(
    _KEYWORD_CATEGORY, key=lambda kv: len(kv[0]), reverse=True
)


import re as _re


def _word_boundary_match(keyword: str, text: str) -> bool:
    """Check if keyword appears as a word (or beginning of a word) in text.

    Rules:
    - Keyword must be preceded by a non-letter character or start of string.
    - Keyword may be followed by letters (to match plurals: carrot→carrots,
      almond→almonds, blueberr→blueberry/blueberries) OR by a non-letter char
      or end of string.
    - Multi-word keywords (containing space) match as a phrase — each word
      is allowed to have trailing letters (for plurals).
    """
    escaped = _re.escape(keyword)
    # Allow trailing word characters (for plural/suffix) after the keyword
    pattern = r"(?<![a-z])" + escaped + r"(?:\w*\b)"
    return bool(_re.search(pattern, text))


def categorize(name: str) -> tuple[str, float]:
    """Categorize an ingredient name.

    Returns:
        (category, confidence)
        - category: one of the known category strings or "other"
        - confidence: 1.0 for a keyword match, 0.0 for no match

    Uses word-boundary matching so "corn" does not match "unicorn".
    Plurals are handled by allowing trailing word characters after the keyword
    (e.g. "almond" matches "almonds", "carrot" matches "carrots").
    """
    if not name or not isinstance(name, str):
        return ("other", 0.0)

    lowered = name.lower().strip()

    for keyword, category in _SORTED_KEYWORDS:
        if _word_boundary_match(keyword, lowered):
            return (category, 1.0)

    return ("other", 0.0)
