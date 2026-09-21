# Data sources & licenses

Every external dataset is listed here **before** it is used. Downloaded and generated data is never committed (`data/raw/`, `data/processed/`, `data/interactions/` are git-ignored). Small hand-curated files in `data/reference/` and `data/knowledge_base/` are committed.

## Overview

| Dataset | Location | Used for | License / terms | How to get it |
|---|---|---|---|---|
| USDA FoodData Central – SR Legacy (April 2018) | `data/raw/usda/` → `data/processed/usda_foods.csv` | Nutrient values per 100 g | Public domain (CC0 1.0) | `python -m scripts.download_usda` |
| RecipeNLG (Bień et al., 2020) | `data/raw/RecipeNLG_dataset.csv` (path set by `RECIPENLG_CSV_PATH`) → `data/processed/recipenlg_sample.csv` | RAG recipe knowledge base, recipe library | **Non-commercial research & educational use only.** No redistribution. | Official site or Kaggle mirror (terms still apply), then `python -m scripts.sample_recipenlg` |
| Allergen lists | `data/reference/allergen_keywords.csv`, `keyword_exceptions.csv` (the 10 codes are `ALLERGENS` in `app/agents/schemas.py`) | Allergen validation | Compiled from U.S. FDA and FSSAI public regulations - see below | Committed |
| Diet rules | `data/reference/diets.csv`, `food_group_keywords.csv` | Diet validation | Written for this project | Committed |
| Prices (₹) | `data/reference/prices_inr.csv` | Budget estimates | Seeded from the mealora-ai-agent reference repo (CC BY 4.0 per its README) plus NutriChef estimates. **Unverified** — update from a trusted source (e.g. Dept. of Consumer Affairs Price Monitoring Cell) before relying on them. | Committed |
| Curated Indian recipes (50) | `data/reference/curated_indian_recipes.csv` | Indian coverage for ranking and meal plans | Written for this project | Committed |
| Ingredient catalog (~155) | `data/reference/ingredient_catalog.csv` → `data/processed/ingredient_foods.csv` | Canonical ingredients, aliases (incl. Hindi names), USDA food link, piece weights, densities | Written for this project; USDA descriptions from SR Legacy. Rows marked `usda_proxy` use a stand-in food (e.g. paneer → whole-milk mozzarella) | Committed |
| Knowledge base (6 docs) | `data/knowledge_base/*.md` | RAG guidance: allergens, diets, nutrition, substitutions, food safety, cooking | Summaries written for this project; each file lists its sources | Committed |

## RecipeNLG

- Columns: `title, ingredients, directions, link, source, NER` (lists stored as JSON text) plus an unnamed index column.
- `source` is `Gathered` (collected by the RecipeNLG authors) or `Recipes1M` (from Recipe1M+, which has its own terms). The sampler keeps **Gathered** rows by default.
- The working sample is reproducible: same file + `--n` + `--seed` → same rows.

Citation:

> Bień, M., Gilski, M., Maciejewska, M., Taisner, W., Wiśniewski, D., & Ławrynowicz, A. (2020). RecipeNLG: A Cooking Recipes Dataset for Semi-Structured Text Generation. *Proceedings of INLG 2020*, 22–28.

## USDA SR Legacy

- Download page: https://fdc.nal.usda.gov/download-datasets (file "SR Legacy – CSV").
- Nutrients kept (per 100 g): Energy kcal (1008), Protein (1003), Carbohydrate by difference (1005), Total fat (1004), Dietary fibre (1079).
- Citation: U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, 2019. fdc.nal.usda.gov.

## Allergen regulations used

- **FDA (US):** milk, eggs, fish, crustacean shellfish, tree nuts, peanuts, wheat, soybeans, sesame (sesame since 1 Jan 2023).
- **FSSAI (India), Labelling & Display Regulations 2020:** cereals containing gluten, crustaceans, milk, eggs, fish, peanuts, tree nuts, soybeans, sulphite ≥ 10 mg/kg.

## Known gaps (handled in later phases)

- Proxy foods (`nutrition_source = usda_proxy`) are approximations; replace them with cited values (e.g. IFCT 2017) when available.

- Some Indian ingredients (e.g. paneer varieties, specific dals, spice blends) may have no exact SR Legacy match; Phase 4 maps names to the closest food and records any manual values with a citation.
- Prices are rough, unverified estimates.

NutriChef AI is a non-commercial educational project. Recipes derived from RecipeNLG keep a link to their original source.

## The 10 allergens, and where each comes from

| Code | Allergen | FDA major | FSSAI declared | Note |
|---|---|---|---|---|
| milk | Milk and milk products | ✓ | ✓ | Includes lactose. Ghee, paneer, curd, butter and cream are milk products. |
| egg | Eggs and egg products | ✓ | ✓ | |
| fish | Fish and fish products | ✓ | ✓ | |
| crustacean | Crustacean shellfish | ✓ | ✓ | Prawn, shrimp, crab, lobster. |
| tree_nut | Tree nuts | ✓ | ✓ | Almond, cashew, walnut, pistachio, etc. |
| peanut | Peanuts (groundnuts) | ✓ | ✓ | |
| wheat_gluten | Wheat / cereals containing gluten | ✓ | ✓ | FDA lists wheat; FSSAI lists cereals containing gluten (wheat, rye, barley, oats, spelt). |
| soy | Soybeans and soy products | ✓ | ✓ | |
| sesame | Sesame | ✓ | – | A major allergen in the US since 1 Jan 2023 (FASTER Act). Not on the FSSAI mandatory list, but common. |
| sulphite | Added sulphites (≥ 10 mg/kg) | – | ✓ | FSSAI declaration threshold 10 mg/kg. |
