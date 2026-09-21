"""Build the ChromaDB search index (recipes + knowledge base).

Run from the project root (after scripts.tag_recipes):
    python -m scripts.build_index                # 2,000 recipes
    python -m scripts.build_index --recipes 500  # quicker

The first run downloads the MiniLM embedding model (~90 MB).
Output: the folder set by CHROMA_DIR in .env (default data/processed/chroma_db).
"""

import argparse
import shutil
import time

import pandas as pd

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.rag import store
from scripts.tag_recipes import OUTPUT_PATH as TAGGED_PATH

BATCH_SIZE = 500


def add_in_batches(collection, documents):
    for start in range(0, len(documents), BATCH_SIZE):
        batch = documents[start : start + BATCH_SIZE]
        collection.add_documents(batch)
        print(f"  added {start + len(batch):,} / {len(documents):,}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipes", type=int, default=2000, help="how many recipes to index")
    parser.add_argument("--rebuild", action="store_true", help="delete the existing index first")
    args = parser.parse_args()
    configure_logging()

    if not TAGGED_PATH.exists():
        print("Run scripts.tag_recipes first.")
        return

    directory = get_settings().chroma_dir
    if args.rebuild and directory.exists():
        shutil.rmtree(directory)
        print(f"Deleted the old index at {directory}")

    started = time.perf_counter()
    embeddings = store.get_embeddings()

    # --- knowledge base ---
    guidance = store.guidance_documents()
    print(f"Knowledge base: {len(guidance)} chunks")
    add_in_batches(store.open_collection(store.GUIDANCE_COLLECTION, embeddings), guidance)

    # --- recipes (library-ready ones first) ---
    recipes = pd.read_json(TAGGED_PATH, lines=True)
    recipes = recipes[recipes["library_ready"]].head(args.recipes).to_dict("records")
    documents = store.recipe_documents(recipes)
    print(f"Recipes: {len(documents):,} documents")
    add_in_batches(store.open_collection(store.RECIPES_COLLECTION, embeddings), documents)

    print(f"\nIndex built in {time.perf_counter() - started:.0f}s -> {directory}")

    # --- quick check ---
    print("\nExample search: 'high protein paneer dinner' (vegetarian, no soy)")
    for hit in store.search_recipes("high protein paneer dinner", k=3, embeddings=embeddings,
                                    diet="vegetarian", avoid_allergens=["soy"]):
        m = hit["metadata"]
        print(f"  {m['title'][:45]:45} {m['kcal']:.0f} kcal, {m['protein_g']:.0f} g protein")

    print("\nExample guidance search: 'what can replace paneer if allergic to milk'")
    for hit in store.search_guidance("what can replace paneer if allergic to milk", k=2,
                                     embeddings=embeddings):
        print(f"  [{hit['metadata']['topic']}] {hit['text'][:120].replace(chr(10), ' ')}...")


if __name__ == "__main__":
    main()
