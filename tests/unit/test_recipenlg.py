from pathlib import Path

import pandas as pd
import pytest

from app.datasets import recipenlg

FIXTURE = Path(__file__).parents[1] / "fixtures" / "recipenlg_tiny.csv"


def test_validate_header_accepts_recipenlg_file():
    header = recipenlg.validate_header(FIXTURE)
    assert set(recipenlg.EXPECTED_COLUMNS) <= set(header)


def test_validate_header_rejects_other_csv(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError, match="missing RecipeNLG columns"):
        recipenlg.validate_header(bad)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('["1 c. sugar", "2 eggs"]', ["1 c. sugar", "2 eggs"]),
        ("['a', 'b']", ["a", "b"]),
        ("", []),
        (None, []),
        ("not a list", []),
    ],
)
def test_parse_list(raw, expected):
    assert recipenlg.parse_list(raw) == expected


def test_profile_counts_rows_by_source():
    stats = recipenlg.profile(FIXTURE, chunksize=5)
    assert stats["rows"] == 12
    assert stats["by_source"] == {"Gathered": 8, "Recipes1M": 4}


def test_sample_is_reproducible_and_filtered():
    a = recipenlg.sample(FIXTURE, n=5, seed=1, chunksize=4)
    b = recipenlg.sample(FIXTURE, n=5, seed=1, chunksize=4)
    c = recipenlg.sample(FIXTURE, n=5, seed=2, chunksize=4)
    assert len(a) == 5
    assert set(a["source"]) == {"Gathered"}
    pd.testing.assert_frame_equal(a, b)
    assert a["title"].tolist() != c["title"].tolist()


def test_sample_all_sources_and_small_files():
    df = recipenlg.sample(FIXTURE, n=100, seed=1, source=None, chunksize=4)
    assert len(df) == 12  # asking for more rows than exist returns everything


def test_save_and_load_sample_round_trip(tmp_path):
    df = recipenlg.sample(FIXTURE, n=3, seed=1)
    path = recipenlg.save_sample(df, tmp_path / "sample.csv")
    loaded = recipenlg.load_sample(path)
    assert isinstance(loaded.loc[0, "ingredients"], list)
    assert loaded.loc[0, "NER"] == ["flour", "eggs"]


def test_missing_csv_gives_clear_error(monkeypatch, tmp_path):
    monkeypatch.setenv("RECIPENLG_CSV_PATH", str(tmp_path / "nope.csv"))
    with pytest.raises(recipenlg.RecipeNLGNotFoundError, match="RECIPENLG_CSV_PATH"):
        recipenlg.csv_path()
