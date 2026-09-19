"""RAG tests use a fake embedder, so they are fast and need no model download."""

import pytest

from app.rag import store

CHROMA = pytest.importorskip("chromadb")


class FakeEmbeddings:
    """Turns text into 3 numbers: does it mention paneer, chicken or allergy?"""

    WORDS = ["paneer", "chicken", "allergy"]

    def _vector(self, text):
        text = text.lower()
        return [1.0 if word in text else 0.0 for word in self.WORDS]

    def embed_documents(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)


RECIPES = [
    {"recipe_id": "r1", "title": "Paneer Bhurji", "origin": "curated", "cuisine_group": "indian",
     "course": "main", "kcal": 380, "protein_g": 23, "cost_per_serving_inr": 45,
     "allergens": ["milk"], "suitable_diets": ["vegetarian", "eggetarian"],
     "ingredients": [{"raw": "200 g paneer"}, {"raw": "80 g onion"}],
     "directions": ["Cook the paneer."], "source_url": ""},
    {"recipe_id": "r2", "title": "Chicken Curry", "origin": "recipenlg", "cuisine_group": "indian",
     "course": "main", "kcal": 500, "protein_g": 30, "cost_per_serving_inr": 90,
     "allergens": [], "suitable_diets": ["non_vegetarian"],
     "ingredients": [{"raw": "500 g chicken"}], "directions": ["Cook the chicken."],
     "source_url": "http://example.com/r2"},
    {"recipe_id": "r3", "title": "Tofu Bhurji", "origin": "curated", "cuisine_group": "indian",
     "course": "main", "kcal": 200, "protein_g": 18, "cost_per_serving_inr": 43,
     "allergens": ["soy"], "suitable_diets": ["vegan", "vegetarian", "eggetarian"],
     "ingredients": [{"raw": "200 g tofu"}], "directions": ["Cook the tofu."], "source_url": ""},
]


@pytest.fixture
def recipe_store(tmp_path):
    collection = store.open_collection("recipes_test", FakeEmbeddings(), tmp_path)
    collection.add_documents(store.recipe_documents(RECIPES))
    return collection


def test_split_text_keeps_paragraphs_together():
    text = "a" * 500 + "\n\n" + "b" * 500 + "\n\n" + "c" * 500
    chunks = store.split_text(text, chunk_size=1200)
    assert len(chunks) == 2
    assert all(len(c) <= 1300 for c in chunks)


def test_guidance_documents_have_topics():
    documents = store.guidance_documents()
    assert len(documents) >= 6
    topics = {d.metadata["topic"] for d in documents}
    assert {"allergens", "diet_rules", "substitutions"} <= topics


def test_recipe_documents_carry_tags():
    document = store.recipe_documents(RECIPES)[0]
    assert "Paneer Bhurji" in document.page_content
    assert "200 g paneer" in document.page_content
    assert document.metadata["has_milk"] is True
    assert document.metadata["has_soy"] is False
    assert document.metadata["ok_vegetarian"] is True
    assert document.metadata["ok_vegan"] is False


def test_build_filter():
    assert store.build_filter() is None
    assert store.build_filter(diet="vegan") == {"ok_vegan": True}
    combined = store.build_filter(diet="vegetarian", avoid_allergens=["soy"], max_kcal=600)
    assert combined == {"$and": [{"ok_vegetarian": True}, {"has_soy": False},
                                {"kcal": {"$lte": 600.0}}]}


def test_search_finds_the_matching_recipe(recipe_store):
    hits = store.search(recipe_store, "paneer", k=1)
    assert hits[0]["metadata"]["recipe_id"] == "r1"
    assert "score" in hits[0]


def test_filter_excludes_allergens_and_wrong_diets(recipe_store):
    where = store.build_filter(diet="vegetarian", avoid_allergens=["soy"])
    hits = store.search(recipe_store, "bhurji", k=5, where=where)
    ids = [h["metadata"]["recipe_id"] for h in hits]
    assert ids == ["r1"]  # tofu (soy) and chicken (not vegetarian) are filtered out


def test_calorie_filter(recipe_store):
    hits = store.search(recipe_store, "bhurji", k=5, where=store.build_filter(max_kcal=300))
    assert [h["metadata"]["recipe_id"] for h in hits] == ["r3"]


def test_header_is_stripped_from_guidance():
    text = "---\ntopic: allergens\ntitle: x\n---\n\n# Food allergens\n\nMilk is an allergen."
    assert store.strip_header(text).startswith("# Food allergens")
    documents = store.guidance_documents()
    assert not documents[0].page_content.startswith("---")
