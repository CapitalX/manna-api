# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Ingredient categorizer.

categorize(name: str) -> tuple[str, float]
  Returns (category, confidence).
  Uses a keyword dict with longest-match-first ordering.
  Falls back to ("other", 0.0) on no match.

Category vocabulary covers Phase 16 guardrails:
  Plant:      whole_grains, fruits, vegetables, legumes, nuts_seeds, oils, herbs_spices
  Animal:     beef, pork, poultry, fish, seafood, processed_meat, dairy, eggs
  Other:      refined_grains, leavened_bread, refined_sugar, alcohol, caffeine,
              pantry, other
  Legacy catchall: meat (only for ambiguous mentions like "meat sauce")
"""
from __future__ import annotations

# Keyword → category mapping.
# Keys are lowercased; matching is substring/longest-match over the ingredient name.
_KEYWORD_CATEGORY: list[tuple[str, str]] = [
    # --- Processed meat (cured / smoked / preserved) ---
    ("bacon", "processed_meat"),
    ("sausage", "processed_meat"),
    ("ham", "processed_meat"),
    ("salami", "processed_meat"),
    ("pepperoni", "processed_meat"),
    ("prosciutto", "processed_meat"),
    ("hot dog", "processed_meat"),
    ("bratwurst", "processed_meat"),
    ("chorizo", "processed_meat"),
    ("deli meat", "processed_meat"),

    # --- Poultry ---
    ("chicken breast", "poultry"),
    ("chicken thigh", "poultry"),
    ("chicken drumstick", "poultry"),
    ("chicken wing", "poultry"),
    ("ground chicken", "poultry"),
    ("ground turkey", "poultry"),
    ("turkey breast", "poultry"),
    ("turkey", "poultry"),
    ("chicken", "poultry"),
    ("duck", "poultry"),
    ("quail", "poultry"),

    # --- Fish ---
    ("salmon fillet", "fish"),
    ("tuna steak", "fish"),
    ("salmon", "fish"),
    ("tuna", "fish"),
    ("cod", "fish"),
    ("tilapia", "fish"),
    ("halibut", "fish"),
    ("sardine", "fish"),
    ("anchovy", "fish"),
    ("mackerel", "fish"),
    ("trout", "fish"),
    ("sea bass", "fish"),

    # --- Seafood (shellfish) ---
    ("shrimp", "seafood"),
    ("crab", "seafood"),
    ("lobster", "seafood"),
    ("scallop", "seafood"),
    ("mussel", "seafood"),
    ("clam", "seafood"),
    ("oyster", "seafood"),
    ("squid", "seafood"),
    ("octopus", "seafood"),

    # --- Beef ---
    ("ground beef", "beef"),
    ("beef steak", "beef"),
    ("sirloin", "beef"),
    ("beef", "beef"),
    ("bison", "beef"),
    ("venison", "beef"),

    # --- Pork (and lamb/red meat) ---
    ("ground pork", "pork"),
    ("pork chop", "pork"),
    ("pork belly", "pork"),
    ("pork tenderloin", "pork"),
    ("lamb chop", "pork"),
    ("pork", "pork"),
    ("lamb", "pork"),

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

    # --- Eggs ---
    ("egg yolk", "eggs"),
    ("egg white", "eggs"),
    ("eggs", "eggs"),
    ("egg", "eggs"),

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
    ("whole wheat pasta", "whole_grains"),
    ("whole grain bread", "whole_grains"),
    ("whole wheat flour", "whole_grains"),
    ("brown rice", "whole_grains"),
    ("wild rice", "whole_grains"),
    ("rolled oat", "whole_grains"),
    ("steel cut oat", "whole_grains"),
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
    ("tortilla", "whole_grains"),  # unleavened flatbread
    ("polenta", "whole_grains"),
    ("cornmeal", "whole_grains"),

    # --- Refined grains ---
    ("all-purpose flour", "refined_grains"),
    ("all purpose flour", "refined_grains"),
    ("white flour", "refined_grains"),
    ("white rice", "refined_grains"),
    ("jasmine rice", "refined_grains"),
    ("basmati rice", "refined_grains"),
    ("wheat flour", "refined_grains"),  # plain "wheat flour" — usually refined
    ("pasta", "refined_grains"),  # default unless "whole wheat pasta" (matched above)
    ("couscous", "refined_grains"),
    ("rice", "refined_grains"),  # default unless "brown/wild rice" (matched above)
    ("flour", "refined_grains"),  # default unless "whole wheat flour" (matched above)

    # --- Leavened bread (yeast-risen) ---
    ("whole wheat bread", "leavened_bread"),
    ("sandwich bread", "leavened_bread"),
    ("white bread", "leavened_bread"),
    ("pita bread", "leavened_bread"),
    ("hamburger bun", "leavened_bread"),
    ("hot dog bun", "leavened_bread"),
    ("dinner roll", "leavened_bread"),
    ("english muffin", "leavened_bread"),
    ("pizza dough", "leavened_bread"),
    ("sourdough", "leavened_bread"),
    ("ciabatta", "leavened_bread"),
    ("focaccia", "leavened_bread"),
    ("baguette", "leavened_bread"),
    ("croissant", "leavened_bread"),
    ("brioche", "leavened_bread"),
    ("bagel", "leavened_bread"),
    ("pita", "leavened_bread"),
    ("naan", "leavened_bread"),
    ("bread", "leavened_bread"),  # catchall (most unspecified bread is leavened)

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

    # --- Refined sugar ---
    ("high fructose corn syrup", "refined_sugar"),
    ("confectioners sugar", "refined_sugar"),
    ("powdered sugar", "refined_sugar"),
    ("granulated sugar", "refined_sugar"),
    ("brown sugar", "refined_sugar"),
    ("white sugar", "refined_sugar"),
    ("cane sugar", "refined_sugar"),
    ("corn syrup", "refined_sugar"),
    ("agave syrup", "refined_sugar"),
    ("agave nectar", "refined_sugar"),
    ("sugar", "refined_sugar"),  # default — usually refined unless "coconut/date sugar"

    # --- Alcohol ---
    ("red wine", "alcohol"),
    ("white wine", "alcohol"),
    ("cooking wine", "alcohol"),
    ("dry vermouth", "alcohol"),
    ("wine", "alcohol"),
    ("beer", "alcohol"),
    ("vodka", "alcohol"),
    ("gin", "alcohol"),
    ("rum", "alcohol"),
    ("bourbon", "alcohol"),
    ("whiskey", "alcohol"),
    ("whisky", "alcohol"),
    ("tequila", "alcohol"),
    ("brandy", "alcohol"),
    ("cognac", "alcohol"),
    ("champagne", "alcohol"),
    ("prosecco", "alcohol"),
    ("sake", "alcohol"),
    ("liqueur", "alcohol"),
    ("sherry", "alcohol"),
    ("port", "alcohol"),

    # --- Caffeine ---
    ("instant coffee", "caffeine"),
    ("cold brew", "caffeine"),
    ("espresso", "caffeine"),
    ("coffee", "caffeine"),
    ("matcha", "caffeine"),

    # --- Pantry ---
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
    ("red wine vinegar", "pantry"),  # "wine vinegar" is non-alcoholic
    ("white wine vinegar", "pantry"),
    ("wine vinegar", "pantry"),  # prevents fall-through match of "wine" → alcohol
    ("dijon mustard", "pantry"),
    ("maple syrup", "pantry"),  # natural sweetener
    ("honey", "pantry"),  # natural sweetener
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
    ("syrup", "pantry"),
    ("jam", "pantry"),
    ("jelly", "pantry"),
    ("water", "pantry"),
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
