"""Static recipe features that need no nutrition data or user history.

Nutrition-based features (calories, protein, cost) are added in Phase 5, and
user-specific features (preference matches) in Phase 7.
"""

import re

MIN_WORD_MATCH = re.compile(r"\b(\d+)\s*(?:-|to)?\s*(\d+)?\s*(minutes?|mins?|hours?|hrs?)\b", re.I)
MAX_MINUTES = 600

CUISINE_KEYWORDS = {
    "indian": ["masala", "dal", "daal", "paneer", "curry", "tikka", "biryani", "chapati", "roti",
               "paratha", "raita", "sambar", "upma", "poha", "chilla", "bhurji", "pulao", "sabzi",
               "bhaji", "chana", "rajma", "palak", "aloo", "gobi", "bhindi", "baingan", "korma",
               "tandoori", "naan", "dosa", "idli", "khichdi", "halwa", "ladoo", "kheer", "jeera"],
    "italian": ["pasta", "spaghetti", "lasagna", "lasagne", "pizza", "risotto", "parmesan",
                "pesto", "marinara", "alfredo", "bruschetta", "fettuccine", "ravioli", "gnocchi"],
    "mexican": ["taco", "tacos", "tortilla", "enchilada", "enchiladas", "salsa", "burrito",
                "quesadilla", "guacamole", "fajita", "fajitas", "nacho", "nachos", "tamale"],
    "asian": ["stir-fry", "stir fry", "teriyaki", "chow mein", "fried rice", "wonton", "szechuan",
              "sesame", "lo mein", "pad thai", "sushi", "ramen", "kung pao"],
}
INDIAN_INGREDIENTS = {"garam_masala", "ghee", "paneer", "toor_dal", "moong_dal", "masoor_dal",
                      "urad_dal", "chana_dal", "besan", "atta", "curry_leaves", "poha", "suji"}

MEAL_TYPE_KEYWORDS = [  # first match wins
    ("beverage", ["punch", "lemonade", "tea", "coffee", "shake", "milkshake", "drink", "cocktail",
                  "lassi", "smoothie", "hot chocolate", "hot cocoa", "chai", "latte", "mocktail"]),
    ("dessert", ["cake", "cakes", "cookie", "cookies", "brownie", "brownies", "pie", "pudding",
                 "fudge", "candy", "frosting", "icing", "cheesecake", "cobbler", "tart", "dessert",
                 "halwa", "ladoo", "kheer", "ice cream", "bars", "cupcakes", "truffles", "crisp"]),
    ("breakfast", ["pancake", "pancakes", "waffle", "waffles", "omelette", "omelet", "oatmeal",
                   "granola", "muffin", "muffins", "french toast", "poha", "upma", "chilla",
                   "paratha", "porridge", "scramble", "breakfast", "bhurji", "oats"]),
    ("snack", ["dip", "chips", "cracker", "crackers", "popcorn", "chaat", "snack", "appetizer",
               "spread", "tikka", "salad", "queso", "hummus", "guacamole", "nachos", "pakora"]),
    ("side", ["raita", "sauce", "dressing", "rolls", "biscuits", "bread", "gravy", "relish",
              "pickle", "chutney", "rice", "salsa", "creamed", "pickles", "slaw", "coleslaw"]),
]


def _contains(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


def estimate_minutes(directions: list[str]) -> int | None:
    """Add up times mentioned in the directions ("bake 30 minutes", "chill 2 hours")."""
    total = 0
    for step in directions:
        for low, high, unit in MIN_WORD_MATCH.findall(step):
            value = (int(low) + int(high)) / 2 if high else int(low)
            total += value * 60 if unit.lower().startswith("h") else value
    return int(min(total, MAX_MINUTES)) if total else None


def guess_cuisine(title: str, ingredient_ids: list[str]) -> str:
    text = title.lower()
    for cuisine, words in CUISINE_KEYWORDS.items():
        if any(_contains(text, w) for w in words):
            return cuisine
    if len(INDIAN_INGREDIENTS.intersection(ingredient_ids)) >= 2:
        return "indian"
    return "other"


def guess_meal_type(title: str) -> str:
    text = title.lower()
    for meal_type, words in MEAL_TYPE_KEYWORDS:
        if any(_contains(text, w) for w in words):
            return meal_type
    return "main"


def difficulty(n_ingredients: int, n_steps: int) -> str:
    if n_ingredients <= 7 and n_steps <= 4:
        return "easy"
    if n_ingredients >= 14 or n_steps >= 10:
        return "hard"
    return "medium"


INDIAN_REGIONAL = {"indian", "north_indian", "south_indian", "maharashtrian", "bengali", "gujarati",
                   "punjabi"}
COURSES = {"main", "breakfast", "snack", "side", "dessert", "beverage"}


def cuisine_group(cuisine: str) -> str:
    """Regional Indian labels (from curated recipes) all group under 'indian'."""
    return "indian" if cuisine in INDIAN_REGIONAL else cuisine


def course(meal_type: str) -> str:
    """Curated recipes say lunch/dinner; the rest of the pipeline uses 'main'."""
    if meal_type in ("lunch", "dinner"):
        return "main"
    return meal_type if meal_type in COURSES else "main"
