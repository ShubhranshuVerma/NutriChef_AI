"""RAG search over two ChromaDB collections.

  recipes  - one document per recipe (title + ingredients + directions),
             with tags stored alongside so we can filter before searching.
  guidance - chunks of the knowledge base documents (allergens, diets,
             nutrition, substitutions, food safety, cooking).

Search only helps the LLM write better recipes. The deterministic checks in
app/validation still decide what is safe.
"""
from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.core.config import get_settings
from app.datasets.reference import knowledge_base_files

RECIPES_COLLECTION = "recipes"
GUIDANCE_COLLECTION = "guidance"
CHUNK_SIZE = 1200  # characters, roughly 250-300 words
ALLERGEN_CODES = ["milk", "egg", "fish", "crustacean", "tree_nut", "peanut",
                  "wheat_gluten", "soy", "sesame", "sulphite"]
DIET_CODES = ["vegan", "vegetarian", "eggetarian", "pescatarian", "jain", "non_vegetarian"]


def get_embeddings():
    """HuggingFace MiniLM, running locally (downloads ~90 MB the first time)."""
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(model_name=get_settings().embedding_model)


def open_collection(name, embeddings=None, directory=None):
    """Open (or create) a Chroma collection stored on disk."""
    directory = str(directory or get_settings().chroma_dir)
    return Chroma(collection_name=name, embedding_function=embeddings or get_embeddings(),
                  persist_directory=directory)

# ---------- turning our data into documents ----------

def split_text(text, chunk_size=CHUNK_SIZE):
    """Split on blank lines, then join paragraphs up to about `chunk_size` characters."""
    chunks, current = [], ""
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current and len(current) + len(paragraph) > chunk_size:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks


def guidance_documents(files=None):
    documents = []
    for path in files if files is not None else knowledge_base_files():
        text = path.read_text(encoding="utf-8")
        for i, chunk in enumerate(split_text(text)):
            documents.append(Document(
                page_content=chunk,
                metadata={"source": path.name, "topic": path.stem, "chunk": i},
            ))
    return documents


def recipe_text(recipe):
    ingredients = ", ".join(i.get("raw", "") for i in recipe.get("ingredients", []))
    steps = " ".join(recipe.get("directions", []))
    return f"{recipe['title']}\nIngredients: {ingredients}\nMethod: {steps}"


def recipe_documents(recipes):
    """One document per recipe. Tags become metadata so we can filter on them."""
    documents = []
    for recipe in recipes:
        metadata = {
            "recipe_id": recipe["recipe_id"],
            "title": recipe["title"],
            "origin": recipe.get("origin", ""),
            "cuisine": recipe.get("cuisine_group", ""),
            "course": recipe.get("course", ""),
            "kcal": float(recipe.get("kcal") or 0),
            "protein_g": float(recipe.get("protein_g") or 0),
            "cost_inr": float(recipe.get("cost_per_serving_inr") or 0),
            "source_url": recipe.get("source_url", ""),
        }
        for code in ALLERGEN_CODES:
            metadata[f"has_{code}"] = code in (recipe.get("allergens") or [])
        for diet in DIET_CODES:
            metadata[f"ok_{diet}"] = diet in (recipe.get("suitable_diets") or [])
        documents.append(Document(page_content=recipe_text(recipe), metadata=metadata))
    return documents


# ---------- searching ----------

def build_filter(diet=None, avoid_allergens=(), cuisine=None, max_kcal=None):
    """Build a Chroma `where` filter from simple arguments."""
    conditions = []
    if diet:
        conditions.append({f"ok_{diet}": True})
    for code in avoid_allergens:
        conditions.append({f"has_{code}": False})
    if cuisine:
        conditions.append({"cuisine": cuisine})
    if max_kcal:
        conditions.append({"kcal": {"$lte": float(max_kcal)}})

    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def search(store, query, k=5, where=None):
    """Return [{text, metadata, score}] - lower score means a closer match."""
    results = store.similarity_search_with_score(query, k=k, filter=where)
    return [{"text": doc.page_content, "metadata": doc.metadata, "score": round(float(score), 4)}
            for doc, score in results]


def search_recipes(query, k=5, embeddings=None, directory=None, **filters):
    store = open_collection(RECIPES_COLLECTION, embeddings, directory)
    return search(store, query, k=k, where=build_filter(**filters))


def search_guidance(query, k=3, embeddings=None, directory=None, topic=None):
    store = open_collection(GUIDANCE_COLLECTION, embeddings, directory)
    return search(store, query, k=k, where={"topic": topic} if topic else None)
