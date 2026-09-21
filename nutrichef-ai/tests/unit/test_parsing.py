import pytest

from app.nutrition.parsing import parse_ingredient


@pytest.mark.parametrize(
    ("line", "quantity", "unit", "name"),
    [
        ("1 c. firmly packed brown sugar", 1.0, "cup", "firmly packed brown sugar"),
        ("1/2 c. evaporated milk", 0.5, "cup", "evaporated milk"),
        ("3 1/2 c. flour", 3.5, "cup", "flour"),
        ("½ cup milk", 0.5, "cup", "milk"),
        ("1.5 kg chicken", 1.5, "kg", "chicken"),
        ("200 grams paneer", 200, "g", "paneer"),
        ("2 Tbsp. butter", 2, "tbsp", "butter"),
        ("1 T. sugar", 1, "tbsp", "sugar"),
        ("1 t. salt", 1, "tsp", "salt"),
        ("1/2 tsp. vanilla", 0.5, "tsp", "vanilla"),
        ("1 lb. ground beef", 1, "lb", "ground beef"),
        ("2 large eggs", 2, "piece", "large eggs"),
        ("10-12 almonds", 11, "piece", "almonds"),
        ("1 1/2 to 2 c. flour", 1.75, "cup", "flour"),
        ("1 stick butter", 1, "stick", "butter"),
        ("2 cups of water", 2, "cup", "water"),
    ],
)
def test_quantity_unit_name(line, quantity, unit, name):
    item = parse_ingredient(line)
    assert item.quantity == pytest.approx(quantity)
    assert item.unit == unit
    assert item.name == name


@pytest.mark.parametrize(
    ("line", "name"),
    [("1 garlic", "garlic"), ("2 lemons", "lemons"), ("1 gallon milk", "gallon milk")],
)
def test_reference_repo_unit_bug_is_fixed(line, name):
    """The old regex read '1 garlic' as unit 'g' + item 'arlic'."""
    item = parse_ingredient(line)
    assert item.unit == "piece"
    assert item.name == name


def test_package_size_in_brackets_is_used():
    item = parse_ingredient("1 (8 oz.) pkg. cream cheese, softened")
    assert (item.quantity, item.unit, item.name, item.note) == (8, "oz", "cream cheese", "softened")


def test_multiple_cans():
    item = parse_ingredient("2 (15 oz.) cans tomato sauce")
    assert (item.quantity, item.unit) == (30, "oz")


def test_notes_from_brackets_and_commas():
    item = parse_ingredient("200 g paneer (crumbled), at room temperature")
    assert item.name == "paneer"
    assert item.note == "at room temperature; crumbled"


def test_cloves_as_unit_only_when_food_follows():
    assert parse_ingredient("2 cloves garlic").unit == "clove"
    spice = parse_ingredient("2 cloves")
    assert (spice.unit, spice.name) == ("piece", "cloves")


def test_no_quantity():
    item = parse_ingredient("Salt to taste")
    assert item.quantity is None and item.unit is None
    assert item.name == "salt to taste"


def test_juice_of_lemon():
    item = parse_ingredient("Juice of 1 lemon")
    assert (item.quantity, item.unit, item.name) == (1, "piece", "lemon juice")
