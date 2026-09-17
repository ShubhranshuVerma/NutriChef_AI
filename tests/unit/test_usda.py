import zipfile

import pandas as pd
import pytest

from app.datasets import usda


@pytest.fixture
def fake_sr_zip(tmp_path):
    """A miniature SR Legacy zip with the same file layout and columns."""
    folder = "FoodData_Central_sr_legacy_food_csv_2018-04/"
    food = pd.DataFrame(
        {
            "fdc_id": [1, 2, 3],
            "data_type": ["sr_legacy_food"] * 3,
            "description": ["Cheese, paneer ", "Egg, whole, raw, fresh", "Mystery food"],
            "food_category_id": [1, 1, 2],
            "publication_date": ["2019-04-01"] * 3,
        }
    )
    category = pd.DataFrame(
        {"id": [1, 2], "code": ["0100", "0200"], "description": ["Dairy and Egg Products", "Spices"]}
    )
    nutrients = pd.DataFrame(
        {
            "id": range(1, 11),
            "fdc_id": [1, 1, 1, 1, 1, 2, 2, 2, 2, 3],
            "nutrient_id": [1008, 1003, 1005, 1004, 1079, 1008, 1003, 1004, 1062, 1003],
            "amount": [321, 25.0, 3.6, 25.0, 0.0, 143, 12.6, 9.5, 598, 1.0],
        }
    )
    path = tmp_path / "sr.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(folder + "food.csv", food.to_csv(index=False))
        zf.writestr(folder + "food_category.csv", category.to_csv(index=False))
        zf.writestr(folder + "food_nutrient.csv", nutrients.to_csv(index=False))
    return path


def test_extract_foods_builds_tidy_table(fake_sr_zip):
    table = usda.extract_foods(fake_sr_zip)
    assert list(table.columns) == usda.OUTPUT_COLUMNS
    paneer = table.set_index("fdc_id").loc[1]
    assert paneer["description"] == "Cheese, paneer"  # whitespace stripped
    assert paneer["category"] == "Dairy and Egg Products"
    assert (paneer["kcal"], paneer["protein_g"], paneer["fat_g"]) == (321, 25.0, 25.0)


def test_missing_nutrient_is_nan_and_food_without_energy_dropped(fake_sr_zip):
    table = usda.extract_foods(fake_sr_zip).set_index("fdc_id")
    assert pd.isna(table.loc[2, "carbs_g"])  # egg row has no carbs value in the fixture
    assert 3 not in table.index  # no energy value -> removed


def test_save_writes_csv(fake_sr_zip, tmp_path):
    out = usda.save(usda.extract_foods(fake_sr_zip), tmp_path / "foods.csv")
    assert pd.read_csv(out).shape[0] == 2


def test_download_skips_existing_file(tmp_path):
    existing = tmp_path / "already.zip"
    existing.write_bytes(b"x")
    assert usda.download(url="http://invalid.invalid/x.zip", dest=existing) == existing


def test_missing_member_raises(tmp_path):
    path = tmp_path / "empty.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("readme.txt", "hi")
    with pytest.raises(FileNotFoundError, match="food.csv"):
        usda.extract_foods(path)
