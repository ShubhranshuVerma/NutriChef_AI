"""The Requirement Agent, in plain Python: free text -> Constraints.

No LLM. It looks for words from fixed lists (diets, allergens, courses) and for
numbers next to units ("600 calories", "25 g protein", "30 minutes", "Rs 80").
The same text always gives the same Constraints.

What it cannot do: understand unusual wording. "I'm off dairy" is not on the
list, so it is missed - the person can pick allergies in the form instead, and
anything they have saved in their profile is always added.
"""

import re

from app.agents.schemas import Constraints

# ---------- word lists ----------

# First match wins, so the longer, more specific phrases come first.
# ("non-vegetarian" contains "vegetarian", so it must be checked before it.)
DIET_WORDS = [
    ("non_vegetarian", ["non-vegetarian", "non vegetarian", "nonvegetarian", "non-veg", "non veg",
                        "nonveg", "i eat meat", "i eat chicken"]),
    ("vegan", ["vegan", "plant-based", "plant based"]),
    ("jain", ["jain"]),
    ("pescatarian", ["pescatarian", "pescetarian"]),
    ("eggetarian", ["eggetarian", "i eat eggs", "i eat egg", "but eat eggs", "who eats eggs",
                    "vegetarian plus eggs", "vegetarian + eggs"]),
    ("vegetarian", ["vegetarian", "pure veg", "veg only"]),
]

# Every word that means an allergen. "nut" and "nuts" mean both kinds of nut: when
# someone says "nut allergy" we would rather avoid too much than too little.
ALLERGEN_WORDS = {
    "milk": ["milk", "dairy", "lactose"],
    "egg": ["egg", "eggs"],
    "fish": ["fish"],
    "crustacean": ["shellfish", "shrimp", "prawn", "prawns", "crab", "lobster", "crustacean"],
    "tree_nut": ["tree nut", "tree nuts", "nut", "nuts", "almond", "almonds", "cashew",
                 "cashews", "walnut", "walnuts", "pistachio", "pistachios"],
    "peanut": ["peanut", "peanuts", "groundnut", "groundnuts", "nut", "nuts"],
    "wheat_gluten": ["gluten", "wheat", "celiac", "coeliac"],
    "soy": ["soy", "soya", "tofu"],
    "sesame": ["sesame", "til"],
    "sulphite": ["sulphite", "sulphites", "sulfite", "sulfites"],
}

COURSE_WORDS = [  # first match wins
    ("breakfast", ["breakfast", "brunch"]),
    ("dessert", ["dessert", "sweet dish"]),
    ("beverage", ["drink", "smoothie", "shake", "beverage", "juice", "lassi"]),
    ("snack", ["snack"]),
    ("side", ["side dish"]),
    ("main", ["dinner", "lunch", "supper", "main course", "main dish"]),
]

CUISINE_WORDS = {
    "indian": ["indian", "punjabi", "gujarati", "bengali", "kerala", "tamil", "desi"],
    "italian": ["italian"],
    "mexican": ["mexican"],
    "asian": ["asian", "chinese", "thai", "japanese", "korean"],
}

# Words that start a list of foods, and what that list means.
ALLERGY_STARTS = ["allergic to", "allergy to", "allergies to", "intolerant to"]
EXCLUDE_STARTS = ["no", "without", "avoid", "skip", "don't want", "do not want", "don't like",
                  "do not like", "hate", "not a fan of"]
HAVE_STARTS = ["have", "i've got", "have got", "i got", "use up", "using up", "leftover",
               "something with", "made with", "using"]

# A list item is a short food name. These words mean the list has ended.
NOT_A_FOOD = {"no", "not", "more", "less", "than", "longer", "over", "too", "much", "added",
              "extra", "time", "minutes", "calories", "budget", "idea", "clue", "at", "in", "for",
              "to", "been", "had", "dinner", "lunch", "breakfast", "meal", "meals", "something",
              "food", "quick", "light", "high", "low", "allergies", "allergy",
              # the start of a new clause: "allergic to soy, don't want whey, have paneer"
              "i", "i'm", "im", "i'd", "we", "my", "am", "is", "are", "don't", "dont", "do",
              "have", "want", "would", "like", "need", "please", "but", "also", "allergic"}
# Lists, not sets: a set's order can change between runs, and this must not.
FILLER = ["some", "a", "an", "the", "any", "fresh", "leftover", "of", "at home", "in the fridge",
          "in my fridge",
          "please", "thanks"]

MAX_TEXT = 1000


# ---------- small helpers ----------

def has_phrase(text, phrase):
    """Whole-word match, so 'eggplant' does not count as 'egg'."""
    return re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text) is not None


def first_match(text, table):
    """The first label in `table` whose words appear in the text."""
    for label, words in table:
        if any(has_phrase(text, word) for word in words):
            return label
    return None


def number(text):
    return int(float(text.replace(",", "")))


def list_after(text, start):
    """The short food names listed right after `start`.

    "allergic to soy, milk and peanuts. I have eggs" -> ["soy", "milk", "peanuts"]
    The list stops at a full stop, or at the first item that is not a short food name.
    """
    items = []
    for match in re.finditer(rf"(?<![a-z]){re.escape(start)}\s+([^.;!?\n]*)", text):
        for part in re.split(r",|\band\b|\bor\b|\bbut\b|\bi'm\b|\bi\b|&|/|\bnor\b", match.group(1)):
            item = part.strip()
            for word in FILLER:
                item = re.sub(rf"^{word}\s+|\s+{word}$", "", item).strip()
            words = item.split()
            if not words or len(words) > 3 or re.search(r"\d", item) or words[0] in NOT_A_FOOD:
                break
            items.append(item)
    return items


def allergen_codes(words):
    """Turn food words into allergen codes: ["dairy", "nuts"] -> ["milk", "peanut", "tree_nut"]."""
    codes = set()
    for word in words:
        for code, names in ALLERGEN_WORDS.items():
            if any(has_phrase(word, name) for name in names):
                codes.add(code)
    return codes


# ---------- the agent ----------

def read_allergies(text):
    words = []
    for start in ALLERGY_STARTS:
        words += list_after(text, start)
    # "soy allergy", "nut allergies", "lactose intolerant", "gluten-free", "dairy free"
    for match in re.finditer(r"([a-z]+(?: [a-z]+)?)[ -](?:allergy|allergies|allergic|intolerant|"
                             r"intolerance|free)(?![a-z])", text):
        words.append(match.group(1))
    return allergen_codes(words)


def read_numbers(text):
    found = {}
    # Calories: "under 600 calories", "600 kcal". A "minimum" of calories is not a limit.
    match = re.search(r"(?:(?<![a-z])(at least|over|more than|minimum)\s*)?([\d,]{2,5})[\s-]*"
                      r"(?:k?cals?|calories|calorie)(?![a-z])", text)
    if match and not match.group(1):
        found["max_kcal"] = number(match.group(2))
    elif re.search(r"low[ -]cal", text):
        found["max_kcal"] = 400
    # Protein: "25 g protein", "25g of protein", "protein of at least 25 g"
    match = (re.search(r"(\d{1,3})\s*g(?:rams?)?\s*(?:of\s+)?protein", text)
             or re.search(r"protein\D{0,20}?(\d{1,3})\s*g(?:rams?)?(?![a-z])", text))
    if match:
        found["min_protein_g"] = number(match.group(1))
    elif re.search(r"(high|rich in|more)[ -]protein|protein[ -]rich", text):
        found["min_protein_g"] = 25
    # Time: "30 minutes", "20 min", "1 hour"
    match = re.search(r"(\d{1,3})[\s-]*(?:minutes|minute|mins|min)(?![a-z])", text)
    if match:
        found["max_cook_minutes"] = number(match.group(1))
    else:
        match = re.search(r"(\d{1,2})[\s-]*(?:hours|hour|hrs|hr)(?![a-z])", text)
        if match:
            found["max_cook_minutes"] = number(match.group(1)) * 60
    # Cost per serving: "Rs 80", "₹80", "80 rupees"
    match = (re.search(r"(?:₹|rs\.?|inr|rupees)\s*([\d,]+)", text)
             or re.search(r"([\d,]+)\s*(?:₹|rs|inr|rupees)(?![a-z])", text))
    if match:
        found["max_cost_inr"] = number(match.group(1))
    # Servings: "for 4 people", "serves 2", "3 servings"
    match = (re.search(r"(?:serves|feeds?)\s+(\d{1,2})(?!\d)", text)
             or re.search(r"(\d{1,2})\s*(?:servings|portions|people|persons)(?![a-z])", text))
    if match and 1 <= number(match.group(1)) <= 12:
        found["servings"] = number(match.group(1))
    return found


def extract_requirements(request_text):
    """Free text -> Constraints. Plain Python: the same text always gives the same answer."""
    text = " ".join(str(request_text)[:MAX_TEXT].lower().replace("’", "'").split())

    allergies = read_allergies(text)
    exclude = []
    for start in EXCLUDE_STARTS:
        for item in list_after(text, start):
            # "no soy" for someone allergic to soy is already covered by the allergy
            if not allergen_codes([item]) & allergies and item not in exclude:
                exclude.append(item)

    have = []
    for start in HAVE_STARTS:
        have += [item for item in list_after(text, start) if item not in have]

    cuisine = next((name for name, words in CUISINE_WORDS.items()
                    if any(has_phrase(text, w) for w in words)), None)

    return Constraints(
        diet=first_match(text, DIET_WORDS),
        allergies=sorted(allergies),
        exclude=exclude,
        have_ingredients=have,
        course=first_match(text, COURSE_WORDS),
        cuisine=cuisine,
        **read_numbers(text),
    )
