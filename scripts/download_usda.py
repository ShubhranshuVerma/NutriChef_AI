"""Download USDA SR Legacy and build data/processed/usda_foods.csv.

Run from the project root:
    python -m scripts.download_usda

If the download fails (network/firewall), download the "SR Legacy - CSV" zip
manually from https://fdc.nal.usda.gov/download-datasets and save it as
data/raw/usda/FoodData_Central_sr_legacy_food_csv_2018-04.zip, then re-run.
"""

import argparse
import sys
import urllib.error

from app.core.logging import configure_logging, get_logger
from app.datasets import usda

log = get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="download again even if present")
    args = parser.parse_args()
    configure_logging()

    try:
        usda.download(force=args.force)
    except (urllib.error.URLError, TimeoutError) as exc:
        log.error("Download failed: %s", exc)
        print(__doc__)
        return 1

    table = usda.extract_foods()
    path = usda.save(table)
    print(f"\nSaved {len(table):,} foods -> {path}")
    print(table.head(5).to_string(index=False))
    print("\nFoods per category (top 10):")
    print(table["category"].value_counts().head(10).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
