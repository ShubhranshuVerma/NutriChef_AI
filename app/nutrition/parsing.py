"""Parse free-text ingredient lines into quantity, unit, name and note.

    "1 (8 oz.) pkg. cream cheese, softened" -> 8.0 oz | "cream cheese" | "softened"
    "3 1/2 c. flour"                        -> 3.5 cup | "flour"
    "200 g paneer (crumbled)"               -> 200 g   | "paneer" | "crumbled"
    "1 garlic"                              -> 1 piece | "garlic"   (the reference repo read this as "1 g arlic")
    "Salt to taste"                         -> None    | "salt to taste"

Only whole tokens are treated as units, which avoids the "garlic" -> "g" bug.
"""

import re
from dataclasses import dataclass

# canonical unit -> spellings (lower-case, without trailing dots)
_UNIT_SPELLINGS = {
    "cup": ["c", "cup", "cups"],
    "tbsp": ["tbsp", "tbsps", "tbs", "tbl", "tablespoon", "tablespoons"],
    "tsp": ["tsp", "tsps", "teaspoon", "teaspoons"],
    "oz": ["oz", "ozs", "ounce", "ounces"],
    "lb": ["lb", "lbs", "pound", "pounds"],
    "g": ["g", "gm", "gms", "gr", "gram", "grams", "gramme", "grammes"],
    "kg": ["kg", "kgs", "kilogram", "kilograms"],
    "ml": ["ml", "mls", "milliliter", "milliliters", "millilitre", "millilitres"],
    "l": ["l", "liter", "liters", "litre", "litres"],
    "qt": ["qt", "qts", "quart", "quarts"],
    "pt": ["pt", "pts", "pint", "pints"],
    "pinch": ["pinch", "pinches"],
    "dash": ["dash", "dashes"],
    "clove": ["clove", "cloves"],
    "slice": ["slice", "slices"],
    "stick": ["stick", "sticks"],
    "bunch": ["bunch", "bunches"],
    "sprig": ["sprig", "sprigs"],
    "inch": ["inch", "inches"],
    "piece": ["piece", "pieces", "pc", "pcs"],
    "can": ["can", "cans", "tin", "tins"],
    "package": ["pkg", "pkgs", "package", "packages", "packet", "packets", "pack", "packs",
                "box", "boxes", "bag", "bags", "carton", "cartons", "envelope", "envelopes",
                "container", "containers"],
    "jar": ["jar", "jars", "bottle", "bottles"],
}
UNIT_LOOKUP = {s: unit for unit, spellings in _UNIT_SPELLINGS.items() for s in spellings}
# Single capital T means tablespoon, lower-case t means teaspoon (old US recipes).
CASE_SENSITIVE_UNITS = {"T": "tbsp", "t": "tsp"}
CONTAINER_UNITS = {"can", "package", "jar"}
# "clove"/"cloves" is only a unit when more words follow ("2 cloves garlic");
# "2 cloves" alone means the spice.
_NEEDS_FOLLOWING_WORD = {"clove"}

_UNICODE_FRACTIONS = {
    "½": " 1/2", "⅓": " 1/3", "⅔": " 2/3", "¼": " 1/4", "¾": " 3/4",
    "⅕": " 1/5", "⅛": " 1/8", "⅜": " 3/8", "⅝": " 5/8", "⅞": " 7/8",
}

_NUMBER = r"\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?"
_QUANTITY_RE = re.compile(
    rf"^\s*(?P<a>{_NUMBER})(?:\s*(?:-|–|to|or)\s*(?P<b>{_NUMBER}))?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_PAREN_RE = re.compile(r"\(([^)]*)\)")
_JUICE_RE = re.compile(r"^juice of (?P<n>\d+(?:/\d+)?)\s+(?P<fruit>lemons?|limes?|oranges?)\b(?P<rest>.*)$", re.IGNORECASE)


@dataclass
class ParsedIngredient:
    raw: str
    quantity: float | None
    unit: str | None
    name: str
    note: str = ""


def _to_number(text: str) -> float:
    total = 0.0
    for part in text.split():
        if "/" in part:
            num, den = part.split("/")
            total += float(num) / float(den) if float(den) else 0.0
        else:
            total += float(part)
    return total


def _read_quantity(text: str) -> tuple[float | None, str]:
    match = _QUANTITY_RE.match(text)
    if not match:
        return None, text.strip()
    low = _to_number(match["a"])
    high = _to_number(match["b"]) if match["b"] else low
    return (low + high) / 2, match["rest"].strip()


def _read_unit(text: str) -> tuple[str | None, str]:
    parts = text.split(maxsplit=1)
    if not parts:
        return None, ""
    token = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    bare = token.rstrip(".,")
    if bare in CASE_SENSITIVE_UNITS:
        unit = CASE_SENSITIVE_UNITS[bare]
    else:
        unit = UNIT_LOOKUP.get(bare.lower())
    if unit is None or (unit in _NEEDS_FOLLOWING_WORD and not rest):
        return None, text
    rest = re.sub(r"^of\s+", "", rest.strip(), flags=re.IGNORECASE)
    return unit, rest


def parse_ingredient(line: str) -> ParsedIngredient:
    raw = line
    text = line.strip()
    for symbol, replacement in _UNICODE_FRACTIONS.items():
        text = text.replace(symbol, replacement)

    # Pull out parenthetical notes; remember a size like "(8 oz.)" for containers.
    inner_size: tuple[float, str] | None = None
    notes: list[str] = []
    for content in _PAREN_RE.findall(text):
        qty, rest = _read_quantity(content)
        unit, _ = _read_unit(rest) if qty is not None else (None, "")
        if qty is not None and unit and unit not in CONTAINER_UNITS and inner_size is None:
            inner_size = (qty, unit)
        else:
            notes.append(content.strip())
    text = _PAREN_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()

    juice = _JUICE_RE.match(text)  # "juice of 1 lemon" -> 1 piece lemon juice
    if juice:
        text = f"{juice['n']} {juice['fruit']} juice {juice['rest']}".strip()

    quantity, rest = _read_quantity(text)
    unit = None
    if quantity is not None:
        unit, rest = _read_unit(rest)
        if unit in CONTAINER_UNITS and inner_size:  # 1 (8 oz.) pkg. -> 8 oz
            quantity, unit = quantity * inner_size[0], inner_size[1]
        elif unit is None and inner_size:  # "2 (15 oz.) tomato sauce"
            quantity, unit = quantity * inner_size[0], inner_size[1]
        elif unit is None:
            unit = "piece"

    name, _, prep = rest.partition(",")
    if prep.strip():
        notes.insert(0, prep.strip())
    name = re.sub(r"^of\s+", "", name.strip(), flags=re.IGNORECASE)
    return ParsedIngredient(
        raw=raw,
        quantity=round(quantity, 4) if quantity is not None else None,
        unit=unit,
        name=name.lower().strip(" .-"),
        note="; ".join(n for n in notes if n),
    )
