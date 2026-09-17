"""Convert a quantity + unit into grams.

- Weight units (g, kg, oz, lb) convert directly.
- Volume units (cup, tbsp, tsp, ml, l) use the ingredient's density (g per ml).
- Count units (piece, clove, slice, inch) use the ingredient's weight per piece.
- If we cannot convert, we return None instead of guessing.
"""

GRAMS_PER_UNIT = {"g": 1, "kg": 1000, "oz": 28.35, "lb": 453.6}
ML_PER_UNIT = {"ml": 1, "l": 1000, "tsp": 4.93, "tbsp": 14.79, "cup": 236.6,
               "pint": 473.2, "pt": 473.2, "qt": 946.4, "pinch": 0.31, "dash": 0.62}
COUNT_UNITS = ["piece", "clove", "slice", "inch", "stick"]
DEFAULT_GRAMS = {"can": 400, "bunch": 100, "sprig": 1}  # rough sizes when none is given
BUTTER_STICK_GRAMS = 113


def to_grams(quantity, unit, ingredient_id, density, grams_per_piece):
    """Return the weight in grams, or None if it can't be worked out."""
    if quantity is None or unit is None or quantity <= 0:
        return None

    if unit in GRAMS_PER_UNIT:
        return quantity * GRAMS_PER_UNIT[unit]

    if unit in ML_PER_UNIT:
        return quantity * ML_PER_UNIT[unit] * density

    if unit == "stick" and ingredient_id in ("butter", "shortening"):
        return quantity * BUTTER_STICK_GRAMS

    if unit in COUNT_UNITS:
        if grams_per_piece > 0:
            return quantity * grams_per_piece
        return None

    if unit in DEFAULT_GRAMS:
        return quantity * DEFAULT_GRAMS[unit]

    return None  # e.g. "1 package" with no size
