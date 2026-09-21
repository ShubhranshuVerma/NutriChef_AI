"""Profile RecipeNLG and save a reproducible working sample.

Run from the project root:
    python -m scripts.sample_recipenlg                 # 50,000 'Gathered' rows
    python -m scripts.sample_recipenlg --n 20000 --seed 7
    python -m scripts.sample_recipenlg --all-sources   # include Recipe1M rows
    python -m scripts.sample_recipenlg --profile       # also count rows per source (slower)

Output: data/processed/recipenlg_sample.csv (git-ignored).
"""

import argparse
import sys
import time

from app.core.logging import configure_logging, get_logger
from app.datasets import recipenlg

log = get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=50_000, help="rows to keep")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--all-sources", action="store_true")
    parser.add_argument("--profile", action="store_true", help="count rows per source first")
    args = parser.parse_args()
    configure_logging()

    try:
        path = recipenlg.csv_path()
    except recipenlg.RecipeNLGNotFoundError as exc:
        log.error("%s", exc)
        return 1

    header = recipenlg.validate_header(path)
    print(f"File: {path} ({path.stat().st_size / 1e9:.2f} GB), columns: {header}")

    if args.profile:
        started = time.perf_counter()
        stats = recipenlg.profile(path)
        print(f"Rows: {stats['rows']:,}  by source: {stats['by_source']}  "
              f"({time.perf_counter() - started:.0f}s)")

    started = time.perf_counter()
    source = None if args.all_sources else "Gathered"
    df = recipenlg.sample(path, n=args.n, seed=args.seed, source=source)
    out = recipenlg.save_sample(df)
    print(f"\nSaved {len(df):,} rows -> {out} ({time.perf_counter() - started:.0f}s)")
    print(df[["title", "source"]].head(5).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
