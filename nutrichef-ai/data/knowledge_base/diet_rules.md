---
topic: diet_rules
title: Dietary patterns used by NutriChef
license: Summary written for NutriChef AI
---

# Dietary patterns

NutriChef uses these definitions when checking recipes. The deterministic rule table lives in `data/reference/diets.csv`; this document explains the reasoning.

## Vegetarian (Indian usage)
In India "vegetarian" normally means lacto-vegetarian: no meat, poultry, fish, seafood or eggs, while milk and milk products are allowed. FSSAI's labelling rules treat food containing eggs as non-vegetarian (brown mark), and vegetarian food carries the green mark. If a user says they are vegetarian but also lists eggs as something they eat, treat them as eggetarian and confirm.

## Eggetarian (lacto-ovo vegetarian)
No meat, poultry, fish or seafood. Dairy and eggs are allowed.

## Vegan
No animal products: no meat, poultry, fish, seafood, eggs, dairy (including ghee, paneer and curd), honey or gelatin. Plant proteins include dals, chickpeas, rajma, tofu and soya chunks (both soy), peanuts and seeds.

## Jain
No meat, poultry, fish, seafood, eggs or honey. Onion, garlic and root vegetables (such as potato, carrot, beetroot, radish and fresh ginger) are avoided. Dairy is allowed. Practices vary between families; asafoetida (hing) is commonly used for flavour instead of onion and garlic.

## Pescatarian
Vegetarian plus fish and seafood.

## Non-vegetarian
No diet-based exclusions; allergies and personal exclusions still apply.

## Gelatin and hidden animal ingredients
Gelatin (in some desserts and gummies) comes from animal collagen and is not vegetarian. Some cheeses are made with animal rennet; strict vegetarians may check labels.

## Sources
- FSSAI, Food Safety and Standards (Labelling and Display) Regulations, 2020: https://www.fssai.gov.in/upload/uploadfiles/files/Compendium_Labelling_Display_23_09_2021.pdf
