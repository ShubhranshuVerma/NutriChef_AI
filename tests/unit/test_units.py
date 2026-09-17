import pytest

from app.nutrition.units import to_grams


def grams(quantity, unit, ingredient_id="x", density=1.0, piece=0):
    return to_grams(quantity, unit, ingredient_id, density, piece)


def test_weight_units():
    assert grams(200, "g") == 200
    assert grams(1.5, "kg") == 1500
    assert grams(1, "lb") == pytest.approx(453.6)


def test_volume_uses_density():
    assert grams(1, "cup", density=0.53) == pytest.approx(125.4, abs=0.1)  # flour
    assert grams(1, "tbsp", density=0.92) == pytest.approx(13.6, abs=0.1)  # oil


def test_count_uses_piece_weight():
    assert grams(2, "piece", piece=50) == 100  # eggs
    assert grams(3, "clove", piece=3) == 9  # garlic
    assert grams(1, "piece", piece=0) is None  # unknown piece weight


def test_butter_stick():
    assert grams(1, "stick", ingredient_id="butter") == 113


def test_defaults_and_unknowns():
    assert grams(1, "can") == 400
    assert grams(1, "package") is None
    assert grams(None, "g") is None
    assert grams(0, "g") is None
