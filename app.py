from flask import Flask, render_template, request
import requests
import re
import html
import json

app = Flask(__name__)

# =========================================================
# API SETTINGS
# =========================================================

OFF_API = "https://world.openfoodfacts.org/api/v2/product/{}.json"

USDA_API = "https://api.nal.usda.gov/fdc/v1/foods/search"
USDA_API_KEY = "DEMO_KEY"

HEADERS = {
    "User-Agent": "ProductLens/1.0 (Food Ingredient Analysis)"
}

# =========================================================
# ALLERGEN GUIDE
# =========================================================

ALLERGEN_GUIDE = {
    "Wheat / Gluten": [
        "wheat",
        "wheat flour",
        "whole wheat",
        "whole wheat flour",
        "maida",
        "atta",
        "gluten",
        "wheat starch",
        "wheat protein",
        "wheat gluten",
        "semolina",
        "suji",
        "rava",
        "durum",
        "barley",
        "rye",
        "malt"
    ],

    "Milk / Dairy": [
        "milk",
        "milk powder",
        "skimmed milk",
        "whole milk",
        "cream",
        "butter",
        "buttermilk",
        "cheese",
        "whey",
        "casein",
        "caseinate",
        "lactose",
        "curd",
        "yogurt",
        "yoghurt"
    ],

    "Soy": [
        "soy",
        "soya",
        "soybean",
        "soy protein",
        "soy flour",
        "soy lecithin",
        "soya lecithin"
    ],

    "Peanuts": [
        "peanut",
        "groundnut",
        "peanut flour",
        "peanut oil"
    ],

    "Tree Nuts": [
        "almond",
        "cashew",
        "walnut",
        "pistachio",
        "hazelnut",
        "pecan",
        "macadamia",
        "brazil nut"
    ],

    "Egg": [
        "egg",
        "egg white",
        "egg yolk",
        "albumin"
    ],

    "Fish": [
        "fish",
        "anchovy",
        "tuna",
        "salmon",
        "sardine"
    ],

    "Shellfish": [
        "shrimp",
        "prawn",
        "crab",
        "lobster",
        "shellfish"
    ],

    "Sesame": [
        "sesame",
        "sesame seed",
        "sesame oil",
        "til"
    ]
}


# =========================================================
# DYNAMIC INGREDIENT FUNCTION GUIDE
# =========================================================
# This is NOT used as a requirement.
# It simply gives better explanations when an ingredient is common.
# Unknown ingredients are handled dynamically below.

INGREDIENT_FUNCTIONS = {

    # Starches / main ingredients
    "potato": (
        "Main food ingredient",
        "Provides bulk, starch and carbohydrate content."
    ),
    "potato starch": (
        "Thickener / starch",
        "Used to add body, improve texture and provide starch."
    ),
    "corn": (
        "Main food ingredient",
        "Provides carbohydrates and contributes to the product's structure."
    ),
    "corn starch": (
        "Thickener / starch",
        "Used to thicken mixtures and improve texture."
    ),
    "maize": (
        "Main food ingredient",
        "Provides carbohydrates and contributes to product structure."
    ),
    "rice": (
        "Main food ingredient",
        "Provides carbohydrates and bulk."
    ),
    "rice flour": (
        "Flour / structure",
        "Used to provide structure, texture and carbohydrate content."
    ),
    "tapioca": (
        "Starch / texture agent",
        "Used to provide starch, body and texture."
    ),
    "tapioca starch": (
        "Thickener / texture agent",
        "Helps improve thickness, texture and consistency."
    ),

    # Flours
    "wheat flour": (
        "Structure / flour",
        "Provides structure and bulk to the food product."
    ),
    "whole wheat flour": (
        "Structure / flour",
        "Provides structure, bulk and carbohydrate content."
    ),
    "maida": (
        "Refined flour",
        "Provides structure, bulk and carbohydrate content."
    ),
    "atta": (
        "Flour",
        "Provides structure, bulk and carbohydrate content."
    ),

    # Sugars
    "sugar": (
        "Sweetener",
        "Adds sweetness and contributes to the product's texture."
    ),
    "glucose": (
        "Sweetener / carbohydrate",
        "Adds sweetness and provides carbohydrate."
    ),
    "glucose syrup": (
        "Sweetener / texture agent",
        "Adds sweetness and helps control texture and consistency."
    ),
    "fructose": (
        "Sweetener",
        "Adds sweetness to the product."
    ),
    "maltodextrin": (
        "Bulking / texture agent",
        "Provides bulk and can improve texture and consistency."
    ),

    # Oils and fats
    "palm oil": (
        "Fat / cooking medium",
        "Provides fat and contributes to texture and mouthfeel."
    ),
    "sunflower oil": (
        "Fat / cooking medium",
        "Provides fat and contributes to texture and mouthfeel."
    ),
    "vegetable oil": (
        "Fat / cooking medium",
        "Provides fat and contributes to texture and mouthfeel."
    ),
    "coconut oil": (
        "Fat / cooking medium",
        "Provides fat and contributes to texture and mouthfeel."
    ),
    "butter": (
        "Fat / flavour",
        "Provides fat, richness and flavour."
    ),

    # Salt
    "salt": (
        "Flavouring / preservation",
        "Enhances flavour and can contribute to preservation."
    ),

    # Acids
    "citric acid": (
        "Acidity regulator",
        "Provides acidity and helps control the product's pH."
    ),
    "lactic acid": (
        "Acidity regulator",
        "Provides acidity and helps control pH."
    ),
    "malic acid": (
        "Acidity regulator",
        "Provides acidity and contributes to flavour balance."
    ),
    "acetic acid": (
        "Acidity regulator",
        "Provides acidity and contributes to preservation and flavour."
    ),

    # Leavening
    "baking soda": (
        "Leavening agent",
        "Helps baked products rise and improves texture."
    ),
    "sodium bicarbonate": (
        "Leavening agent",
        "Releases gas during baking and helps products rise."
    ),
    "baking powder": (
        "Leavening agent",
        "Helps the product rise and develop a lighter texture."
    ),

    # Emulsifiers
    "lecithin": (
        "Emulsifier",
        "Helps ingredients such as water and fat mix more evenly."
    ),
    "soy lecithin": (
        "Emulsifier",
        "Helps maintain a stable mixture of ingredients."
    ),
    "mono and diglycerides": (
        "Emulsifier",
        "Helps improve texture and maintain a stable mixture."
    ),

    # Thickeners / stabilizers
    "xanthan gum": (
        "Thickener / stabilizer",
        "Helps thicken the product and maintain consistency."
    ),
    "guar gum": (
        "Thickener / stabilizer",
        "Improves thickness and texture."
    ),
    "pectin": (
        "Gelling / thickening agent",
        "Helps create or maintain gel-like texture."
    ),
    "carrageenan": (
        "Thickener / stabilizer",
        "Helps improve texture and stability."
    ),

    # Preservatives
    "sodium benzoate": (
        "Preservative",
        "Helps prevent the growth of microorganisms and extend shelf life."
    ),
    "potassium sorbate": (
        "Preservative",
        "Helps inhibit microbial growth and extend shelf life."
    ),
    "sorbic acid": (
        "Preservative",
        "Helps prevent microbial growth."
    ),

    # Colours
    "curcumin": (
        "Food colouring",
        "Provides a yellow colour to the product."
    ),
    "turmeric": (
        "Colouring / flavouring",
        "Provides colour and contributes flavour."
    ),

    # Flavours
    "vanilla": (
        "Flavouring",
        "Adds vanilla flavour and aroma."
    ),
    "vanillin": (
        "Flavouring",
        "Provides vanilla-like flavour and aroma."
    ),

    # Cocoa
    "cocoa": (
        "Flavouring / main ingredient",
        "Provides cocoa flavour, colour and characteristic aroma."
    ),
    "cocoa powder": (
        "Flavouring / colour",
        "Provides cocoa flavour and colour."
    )
}


# =========================================================
# BASIC HELPERS
# =========================================================

def clean_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_ingredient(value):
    value = clean_text(value).lower()

    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"\[[^\]]*\]", "", value)

    value = value.replace("–", "-")
    value = value.replace("—", "-")

    value = re.sub(r"^\s*\d+[\.\)]\s*", "", value)
    value = re.sub(r"^\s*e[- ]?\d+\s*", "", value)

    return value.strip(" ,;:-")


# =========================================================
# INGREDIENT PARSER
# =========================================================

def parse_ingredients(product):
    """
    Open Food Facts can store ingredients in multiple fields.
    Try all useful fields instead of depending on one field.
    """

    ingredients = []

    # -----------------------------------------------------
    # 1. structured ingredients
    # -----------------------------------------------------

    structured = product.get("ingredients")

    if isinstance(structured, list):

        for item in structured:

            if isinstance(item, dict):

                name = (
                    item.get("text")
                    or item.get("id")
                    or item.get("name")
                    or ""
                )

                name = clean_text(name)

                if name:
                    ingredients.append(name)

    # -----------------------------------------------------
    # 2. ingredient text
    # -----------------------------------------------------

    possible_text_fields = [
        "ingredients_text",
        "ingredients_text_en",
        "ingredients_text_in",
        "ingredients_text_hi",
        "ingredients_text_fr"
    ]

    for field in possible_text_fields:

        text = product.get(field)

        if isinstance(text, str) and text.strip():

            text = clean_text(text)

            # Split common ingredient formats
            parts = re.split(
                r",|;|\n",
                text
            )

            for part in parts:

                part = clean_text(part)

                if part:
                    ingredients.append(part)

    # -----------------------------------------------------
    # Remove duplicates while preserving order
    # -----------------------------------------------------

    final = []

    seen = set()

    for ingredient in ingredients:

        cleaned = normalize_ingredient(ingredient)

        if not cleaned:
            continue

        # Ignore generic headings
        if cleaned in {
            "ingredients",
            "ingredient",
            "ingredients:",
            "ingredient:"
        }:
            continue

        if cleaned not in seen:

            seen.add(cleaned)
            final.append(ingredient.strip())

    return final


# =========================================================
# DYNAMIC INGREDIENT EXPLANATION
# =========================================================

def get_ingredient_explanation(ingredient):
    """
    Gives an explanation without requiring every ingredient
    to exist in a manually maintained dictionary.
    """

    original = clean_text(ingredient)
    name = normalize_ingredient(original)

    # -----------------------------------------------------
    # Exact known ingredient
    # -----------------------------------------------------

    if name in INGREDIENT_FUNCTIONS:

        function, explanation = INGREDIENT_FUNCTIONS[name]

        return {
            "name": original,
            "function": function,
            "used_for": explanation
        }

    # -----------------------------------------------------
    # Pattern-based intelligence
    # -----------------------------------------------------

    if "starch" in name:
        function = "Starch / thickener"
        explanation = (
            "Used to provide starch, improve thickness, "
            "or contribute to the product's texture."
        )

    elif "flour" in name:
        function = "Flour / structure"
        explanation = (
            "Provides bulk and structure and contributes "
            "to the product's carbohydrate content."
        )

    elif "syrup" in name:
        function = "Sweetener / texture agent"
        explanation = (
            "Commonly used to add sweetness, bulk or "
            "help control texture and consistency."
        )

    elif "oil" in name:
        function = "Fat / cooking medium"
        explanation = (
            "Provides fat and contributes to texture, "
            "mouthfeel or cooking characteristics."
        )

    elif "extract" in name:
        function = "Flavouring"
        explanation = (
            "Used to provide flavour or aroma derived "
            "from the named source."
        )

    elif "flavour" in name or "flavor" in name:
        function = "Flavouring"
        explanation = (
            "Used to provide or enhance the product's "
            "characteristic flavour and aroma."
        )

    elif "colour" in name or "color" in name:
        function = "Food colouring"
        explanation = (
            "Used to provide or enhance the colour "
            "of the food product."
        )

    elif "acid" in name:
        function = "Acidity regulator"
        explanation = (
            "Used to provide acidity or help control "
            "the product's pH."
        )

    elif "gum" in name:
        function = "Thickener / stabilizer"
        explanation = (
            "Usually used to improve thickness, texture "
            "and stability."
        )

    elif "emulsifier" in name:
        function = "Emulsifier"
        explanation = (
            "Helps ingredients such as oil and water "
            "remain evenly mixed."
        )

    elif "preservative" in name:
        function = "Preservative"
        explanation = (
            "Used to help maintain product quality and "
            "extend shelf life."
        )

    elif "sugar" in name:
        function = "Sweetener"
        explanation = (
            "Used mainly to add sweetness and contribute "
            "to product texture."
        )

    elif "salt" in name:
        function = "Flavouring / preservation"
        explanation = (
            "Enhances flavour and can also contribute "
            "to preservation."
        )

    elif "protein" in name:
        function = "Protein ingredient"
        explanation = (
            "Provides protein and can contribute to "
            "the structure or nutritional profile."
        )

    elif "milk" in name:
        function = "Dairy ingredient"
        explanation = (
            "Provides dairy solids, flavour, protein "
            "and contributes to texture."
        )

    elif "cocoa" in name:
        function = "Flavouring / colour"
        explanation = (
            "Provides cocoa flavour, colour and aroma."
        )

    elif "vanilla" in name:
        function = "Flavouring"
        explanation = (
            "Provides vanilla flavour and aroma."
        )

    elif "fruit" in name:
        function = "Fruit ingredient"
        explanation = (
            "Provides fruit-derived flavour, aroma and "
            "other natural food components."
        )

    elif "vegetable" in name:
        function = "Vegetable ingredient"
        explanation = (
            "Provides vegetable-derived flavour, "
            "texture and food solids."
        )

    elif "seed" in name:
        function = "Seed ingredient"
        explanation = (
            "Provides food solids, flavour and nutrients "
            "depending on the specific seed."
        )

    else:
        # IMPORTANT:
        # Never tell the user that ProductLens has no guide.
        function = "Food ingredient"
        explanation = (
            "This ingredient contributes to the product's "
            "overall composition, flavour, texture or "
            "nutritional profile. Its exact function depends "
            "on the specific form and amount used."
        )

    return {
        "name": original,
        "function": function,
        "used_for": explanation
    }


# =========================================================
# ALLERGEN DETECTION
# =========================================================

def detect_allergens(ingredients):
    detected = []

    for ingredient in ingredients:

        text = normalize_ingredient(ingredient)

        for allergen, keywords in ALLERGEN_GUIDE.items():

            for keyword in keywords:

                if keyword.lower() in text:

                    if allergen not in detected:
                        detected.append(allergen)

                    break

    return detected


# =========================================================
# INGREDIENT ORDER
# =========================================================

def get_ingredient_order(ingredients):
    result = []

    for index, ingredient in enumerate(ingredients, start=1):

        result.append({
            "number": index,
            "name": clean_text(ingredient)
        })

    return result


# =========================================================
# INGREDIENT CATEGORIES
# =========================================================

def classify_ingredient(ingredient):

    name = normalize_ingredient(ingredient)

    if any(x in name for x in [
        "sugar",
        "glucose",
        "fructose",
        "syrup",
        "maltodextrin"
    ]):
        return "Sweeteners", "🍬"

    if any(x in name for x in [
        "oil",
        "butter",
        "fat",
        "cream"
    ]):
        return "Fats & Oils", "🫒"

    if any(x in name for x in [
        "flour",
        "starch",
        "rice",
        "wheat",
        "potato",
        "corn",
        "maize",
        "oat"
    ]):
        return "Starches & Grains", "🌾"

    if any(x in name for x in [
        "milk",
        "whey",
        "casein",
        "cheese",
        "yogurt",
        "cream"
    ]):
        return "Dairy", "🥛"

    if any(x in name for x in [
        "gum",
        "pectin",
        "carrageenan",
        "gelatin",
        "thickener",
        "stabilizer"
    ]):
        return "Texture Agents", "🧩"

    if any(x in name for x in [
        "acid",
        "citrate",
        "sodium bicarbonate",
        "baking soda"
    ]):
        return "Acidity & Leavening", "⚗️"

    if any(x in name for x in [
        "preservative",
        "benzoate",
        "sorbate",
        "sorbic"
    ]):
        return "Preservatives", "🛡️"

    if any(x in name for x in [
        "colour",
        "color",
        "curcumin",
        "caramel"
    ]):
        return "Colours", "🎨"

    if any(x in name for x in [
        "flavour",
        "flavor",
        "vanilla",
        "extract",
        "cocoa"
    ]):
        return "Flavouring", "✨"

    if any(x in name for x in [
        "vitamin",
        "mineral",
        "iron",
        "calcium",
        "zinc"
    ]):
        return "Nutrients", "💊"

    return "Other Ingredients", "🔬"


def build_categories(ingredients):

    categories = {}

    for ingredient in ingredients:

        category, icon = classify_ingredient(ingredient)

        if category not in categories:

            categories[category] = {
                "name": category,
                "icon": icon,
                "count": 0,
                "ingredients": []
            }

        categories[category]["count"] += 1
        categories[category]["ingredients"].append(
            clean_text(ingredient)
        )

    total = len(ingredients)

    result = []

    for category in categories.values():

        percentage = 0

        if total:
            percentage = round(
                (category["count"] / total) * 100
            )

        category["percentage"] = percentage

        result.append(category)

    return result


# =========================================================
# NUTRITION HELPERS
# =========================================================

def safe_number(value, default=0):

    if value is None:
        return default

    try:

        if isinstance(value, str):

            value = value.replace(",", "").strip()

            if not value:
                return default

        return float(value)

    except (ValueError, TypeError):

        return default


def nutrition_level(value, nutrient):

    value = safe_number(value)

    if nutrient == "energy":
        if value < 120:
            return "low"
        elif value < 250:
            return "medium"
        return "high"

    if nutrient == "sugars":
        if value < 5:
            return "low"
        elif value < 12.5:
            return "medium"
        return "high"

    if nutrient == "fat":
        if value < 3:
            return "low"
        elif value < 17.5:
            return "medium"
        return "high"

    if nutrient == "saturated-fat":
        if value < 1.5:
            return "low"
        elif value < 5:
            return "medium"
        return "high"

    if nutrient == "salt":
        if value < 0.3:
            return "low"
        elif value < 1.5:
            return "medium"
        return "high"

    return "neutral"


# =========================================================
# NUTRITION DATA
# =========================================================

def build_nutrition(product):

    nutriments = product.get("nutriments", {})

    if not isinstance(nutriments, dict):
        nutriments = {}

    energy = safe_number(
        nutriments.get("energy-kcal_100g")
        or nutriments.get("energy-kcal")
    )

    sugars = safe_number(
        nutriments.get("sugars_100g")
    )

    fat = safe_number(
        nutriments.get("fat_100g")
    )

    saturated = safe_number(
        nutriments.get("saturated-fat_100g")
    )

    protein = safe_number(
        nutriments.get("proteins_100g")
    )

    salt = safe_number(
        nutriments.get("salt_100g")
    )

    carbohydrates = safe_number(
        nutriments.get("carbohydrates_100g")
    )

    fiber = safe_number(
        nutriments.get("fiber_100g")
    )

    return {
        "energy": {
            "value": energy,
            "unit": "kcal",
            "level": nutrition_level(energy, "energy")
        },

        "sugars": {
            "value": sugars,
            "unit": "g",
            "level": nutrition_level(sugars, "sugars")
        },

        "fat": {
            "value": fat,
            "unit": "g",
            "level": nutrition_level(fat, "fat")
        },

        "saturated_fat": {
            "value": saturated,
            "unit": "g",
            "level": nutrition_level(
                saturated,
                "saturated-fat"
            )
        },

        "protein": {
            "value": protein,
            "unit": "g",
            "level": "neutral"
        },

        "carbohydrates": {
            "value": carbohydrates,
            "unit": "g",
            "level": "neutral"
        },

        "fiber": {
            "value": fiber,
            "unit": "g",
            "level": "neutral"
        },

        "salt": {
            "value": salt,
            "unit": "g",
            "level": nutrition_level(
                salt,
                "salt"
            )
        }
    }


# =========================================================
# PRODUCT ANALYSIS SCORE
# =========================================================

def calculate_score(product, ingredients, allergens):

    score = 75

    nutriments = product.get("nutriments", {})

    if not isinstance(nutriments, dict):
        nutriments = {}

    sugars = safe_number(
        nutriments.get("sugars_100g")
    )

    saturated = safe_number(
        nutriments.get("saturated-fat_100g")
    )

    salt = safe_number(
        nutriments.get("salt_100g")
    )

    fiber = safe_number(
        nutriments.get("fiber_100g")
    )

    protein = safe_number(
        nutriments.get("proteins_100g")
    )

    # Sugar
    if sugars > 20:
        score -= 12
    elif sugars > 12.5:
        score -= 7
    elif sugars > 5:
        score -= 3

    # Saturated fat
    if saturated > 5:
        score -= 10
    elif saturated > 1.5:
        score -= 4

    # Salt
    if salt > 1.5:
        score -= 10
    elif salt > 0.3:
        score -= 4

    # Protein
    if protein >= 10:
        score += 5

    # Fibre
    if fiber >= 5:
        score += 5

    # Allergens should not automatically mean unhealthy.
    # We do NOT penalize the score simply because an allergen exists.

    score = max(0, min(100, round(score)))

    if score >= 70:
        label = "Good"
        css = "good"
    elif score >= 45:
        label = "Moderate"
        css = "moderate"
    else:
        label = "Needs Attention"
        css = "attention"

    return {
        "score": score,
        "label": label,
        "css": css
    }


# =========================================================
# NUTRITION INDICATORS
# =========================================================

def build_indicators(product):

    nutriments = product.get("nutriments", {})

    if not isinstance(nutriments, dict):
        nutriments = {}

    values = [
        (
            "Sugar",
            safe_number(
                nutriments.get("sugars_100g")
            ),
            "g"
        ),

        (
            "Fat",
            safe_number(
                nutriments.get("fat_100g")
            ),
            "g"
        ),

        (
            "Saturated Fat",
            safe_number(
                nutriments.get("saturated-fat_100g")
            ),
            "g"
        ),

        (
            "Salt",
            safe_number(
                nutriments.get("salt_100g")
            ),
            "g"
        ),

        (
            "Protein",
            safe_number(
                nutriments.get("proteins_100g")
            ),
            "g"
        ),

        (
            "Fibre",
            safe_number(
                nutriments.get("fiber_100g")
            ),
            "g"
        )
    ]

    indicators = []

    for name, value, unit in values:

        if name == "Sugar":
            level = nutrition_level(value, "sugars")
            percentage = min(100, round((value / 25) * 100))

        elif name == "Fat":
            level = nutrition_level(value, "fat")
            percentage = min(100, round((value / 30) * 100))

        elif name == "Saturated Fat":
            level = nutrition_level(
                value,
                "saturated-fat"
            )
            percentage = min(100, round((value / 15) * 100))

        elif name == "Salt":
            level = nutrition_level(value, "salt")
            percentage = min(100, round((value / 3) * 100))

        else:
            level = "neutral"
            percentage = min(100, round((value / 20) * 100))

        indicators.append({
            "name": name,
            "value": value,
            "unit": unit,
            "level": level,
            "percentage": percentage
        })

    return indicators


# =========================================================
# FETCH PRODUCT FROM OPEN FOOD FACTS
# =========================================================

def fetch_open_food_facts(barcode):

    barcode = re.sub(r"\D", "", str(barcode))

    if not barcode:
        return None, "Please enter a valid barcode."

    # -----------------------------------------------------
    # Important:
    # Keep the original barcode exactly as entered.
    # Do NOT remove leading zeroes.
    # -----------------------------------------------------

    url = OFF_API.format(barcode)

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15
        )

    except requests.RequestException as error:

        return None, (
            "Unable to connect to the food database. "
            "Please check your internet connection and try again."
        )

    if response.status_code != 200:

        return None, (
            f"Food database returned HTTP "
            f"{response.status_code}."
        )

    try:
        data = response.json()

    except ValueError:

        return None, (
            "The food database returned an invalid response."
        )

    # -----------------------------------------------------
    # Open Food Facts uses status = 1 for found products.
    # But don't depend ONLY on status.
    # -----------------------------------------------------

    product = data.get("product")

    if not isinstance(product, dict):
        product = {}

    status = data.get("status")

    # Some valid responses can contain useful product data
    # even when status handling is inconsistent.
    has_product_data = any([
        product.get("product_name"),
        product.get("product_name_en"),
        product.get("ingredients_text"),
        product.get("ingredients")
    ])

    if status != 1 and not has_product_data:

        return None, (
            "No product was found for this barcode in "
            "the Open Food Facts database."
        )

    return product, None


# =========================================================
# BUILD COMPLETE PRODUCT RESULT
# =========================================================

def build_product_result(product, barcode):

    product_name = (
        product.get("product_name")
        or product.get("product_name_en")
        or product.get("generic_name")
        or "Unknown Product"
    )

    brand = (
        product.get("brands")
        or product.get("brand_owner")
        or "Brand not available"
    )

    image = (
        product.get("image_front_url")
        or product.get("image_url")
        or product.get("image_front_small_url")
        or ""
    )

    ingredients = parse_ingredients(product)

    explanations = [
        get_ingredient_explanation(item)
        for item in ingredients
    ]

    allergens = detect_allergens(ingredients)

    ingredient_order = get_ingredient_order(
        ingredients
    )

    categories = build_categories(
        ingredients
    )

    nutrition = build_nutrition(
        product
    )

    score = calculate_score(
        product,
        ingredients,
        allergens
    )

    indicators = build_indicators(
        product
    )

    return {
        "product": product,

        "product_name": clean_text(product_name),

        "brand": clean_text(brand),

        "barcode": barcode,

        "image": image,

        "ingredients": ingredients,

        "ingredient_explanations": explanations,

        "ingredient_order": ingredient_order,

        "ingredient_categories": categories,

        "allergens": allergens,

        "nutrition": nutrition,

        "indicators": indicators,

        "analysis": score,

        "categories": product.get(
            "categories",
            ""
        ),

        "quantity": product.get(
            "quantity",
            ""
        ),

        "serving_size": product.get(
            "serving_size",
            ""
        ),

        "countries": product.get(
            "countries",
            ""
        ),

        "nova_group": product.get(
            "nova_group",
            ""
        ),

        "nutriscore": product.get(
            "nutriscore_grade",
            ""
        )
    }


# =========================================================
# HOME
# =========================================================

@app.route("/", methods=["GET"])
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# SEARCH / BARCODE
# =========================================================

@app.route("/search", methods=["POST"])
def search():

    barcode = (
        request.form.get("barcode")
        or request.form.get("code")
        or request.form.get("query")
        or ""
    )

    barcode = re.sub(
        r"\D",
        "",
        barcode
    )

    if not barcode:

        return render_template(
            "index.html",
            error="Please enter or scan a valid barcode."
        )

    product, error = fetch_open_food_facts(
        barcode
    )

    if error:

        return render_template(
            "index.html",
            error=error,
            barcode=barcode
        )

    result = build_product_result(
        product,
        barcode
    )

    return render_template(
        "index.html",
        result=result,
        product=result,
        barcode=barcode
    )


# =========================================================
# MANUAL PRODUCT INPUT
# =========================================================

@app.route("/manual", methods=["POST"])
def manual():

    product_name = clean_text(
        request.form.get("product_name")
        or request.form.get("name")
        or "Manual Product"
    )

    brand = clean_text(
        request.form.get("brand")
        or "Manual Entry"
    )

    ingredients_text = (
        request.form.get("ingredients")
        or request.form.get("ingredient_list")
        or ""
    )

    ingredients = [
        clean_text(x)
        for x in re.split(
            r",|;|\n",
            ingredients_text
        )
        if clean_text(x)
    ]

    product = {
        "product_name": product_name,
        "brands": brand,
        "ingredients_text": ingredients_text,
        "ingredients": [
            {
                "text": ingredient
            }
            for ingredient in ingredients
        ]
    }

    # Optional nutrition values
    nutrition_fields = [
        "energy-kcal_100g",
        "sugars_100g",
        "fat_100g",
        "saturated-fat_100g",
        "proteins_100g",
        "carbohydrates_100g",
        "fiber_100g",
        "salt_100g"
    ]

    nutriments = {}

    for field in nutrition_fields:

        value = request.form.get(field)

        if value not in (None, ""):

            nutriments[field] = value

    product["nutriments"] = nutriments

    result = build_product_result(
        product,
        "Manual Entry"
    )

    return render_template(
        "index.html",
        result=result,
        product=result
    )


# =========================================================
# OPTIONAL API ENDPOINT
# =========================================================

@app.route("/api/product/<barcode>", methods=["GET"])
def api_product(barcode):

    barcode = re.sub(
        r"\D",
        "",
        barcode
    )

    if not barcode:

        return {
            "success": False,
            "error": "Invalid barcode"
        }, 400

    product, error = fetch_open_food_facts(
        barcode
    )

    if error:

        return {
            "success": False,
            "error": error,
            "barcode": barcode
        }, 404

    result = build_product_result(
        product,
        barcode
    )

    return {
        "success": True,
        "data": result
    }


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def not_found(error):

    return render_template(
        "index.html",
        error="Page not found."
    ), 404


@app.errorhandler(500)
def server_error(error):

    return render_template(
        "index.html",
        error="Something went wrong while processing the product."
    ), 500


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    print("=" * 60)
    print("PRODUCTLENS — Food Intelligence")
    print("=" * 60)
    print("Server running at:")
    print("http://127.0.0.1:5000")
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
