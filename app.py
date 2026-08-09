from flask import Flask, render_template, request
import requests
import re
import html
from urllib.parse import quote

app = Flask(__name__)

# ============================================================
# API SETTINGS
# ============================================================

OFF_API = "https://world.openfoodfacts.org/api/v2/product/{}.json"

USDA_API = "https://api.nal.usda.gov/fdc/v1/foods/search"
USDA_API_KEY = "DEMO_KEY"

HEADERS = {
    "User-Agent": "ProductLens/2.0 (Food Ingredient Analysis App)",
    "Accept": "application/json",
}

REQUEST_TIMEOUT = 12


# ============================================================
# INGREDIENT EXPLANATION GUIDE
# ============================================================

INGREDIENT_GUIDE = {

    # ---------------- FLOURS / GRAINS ----------------

    "wheat": {
        "category": "Grain / Cereal",
        "used_for": "Provides structure, bulk and carbohydrates in bakery and cereal products.",
    },

    "wheat flour": {
        "category": "Flour",
        "used_for": "Used as a main flour for structure, texture and bulk.",
    },

    "whole wheat": {
        "category": "Whole Grain",
        "used_for": "Provides grain structure, carbohydrates and naturally occurring fibre.",
    },

    "maida": {
        "category": "Refined Flour",
        "used_for": "Used to provide structure, softness and bulk in baked and processed foods.",
    },

    "atta": {
        "category": "Whole Grain Flour",
        "used_for": "Used as a grain-based flour and provides carbohydrates and fibre.",
    },

    "rice": {
        "category": "Grain",
        "used_for": "Provides carbohydrates and bulk.",
    },

    "rice flour": {
        "category": "Flour",
        "used_for": "Used for texture, binding, crispness and bulk.",
    },

    "corn": {
        "category": "Grain",
        "used_for": "Provides carbohydrates and bulk.",
    },

    "corn flour": {
        "category": "Flour / Thickener",
        "used_for": "Used for thickening, coating and improving texture.",
    },

    "corn starch": {
        "category": "Starch / Thickener",
        "used_for": "Primarily used as a thickener and texture modifier.",
    },

    "potato": {
        "category": "Vegetable / Starch",
        "used_for": "Provides starch, bulk and texture; commonly used in snacks, processed foods and starch-based products.",
    },

    "potato starch": {
        "category": "Starch / Thickener",
        "used_for": "Used to provide thickness, binding and a smooth or crisp texture.",
    },

    "tapioca": {
        "category": "Starch",
        "used_for": "Provides starch and is commonly used for texture, binding and thickening.",
    },

    "tapioca starch": {
        "category": "Starch / Thickener",
        "used_for": "Used for thickening, binding and improving texture.",
    },

    # ---------------- SUGARS ----------------

    "sugar": {
        "category": "Sweetener",
        "used_for": "Adds sweetness, contributes to texture and can help with browning.",
    },

    "glucose": {
        "category": "Sugar / Sweetener",
        "used_for": "Provides sweetness and carbohydrates and can influence texture and browning.",
    },

    "glucose syrup": {
        "category": "Sweetener / Syrup",
        "used_for": "Adds sweetness and helps control texture and crystallisation.",
    },

    "fructose": {
        "category": "Sugar",
        "used_for": "Provides sweetness and carbohydrates.",
    },

    "maltose": {
        "category": "Sugar",
        "used_for": "Provides sweetness and carbohydrates.",
    },

    "dextrose": {
        "category": "Sugar / Sweetener",
        "used_for": "Provides sweetness and carbohydrates and is commonly used in processed foods.",
    },

    "invert sugar": {
        "category": "Sweetener",
        "used_for": "Provides sweetness and helps maintain moisture and texture.",
    },

    "molasses": {
        "category": "Sweetener",
        "used_for": "Adds sweetness, colour and flavour.",
    },

    # ---------------- OILS / FATS ----------------

    "palm oil": {
        "category": "Vegetable Oil",
        "used_for": "Provides fat and is used for texture, cooking stability and mouthfeel.",
    },

    "palmolein": {
        "category": "Vegetable Oil",
        "used_for": "Used as a cooking and food-processing fat.",
    },

    "sunflower oil": {
        "category": "Vegetable Oil",
        "used_for": "Provides fat and is commonly used for cooking and food processing.",
    },

    "soybean oil": {
        "category": "Vegetable Oil",
        "used_for": "Provides fat and is used for cooking, texture and food processing.",
    },

    "canola oil": {
        "category": "Vegetable Oil",
        "used_for": "Used as a vegetable cooking oil and provides fat.",
    },

    "rapeseed oil": {
        "category": "Vegetable Oil",
        "used_for": "Used as a vegetable cooking oil and provides fat.",
    },

    "coconut oil": {
        "category": "Vegetable Oil",
        "used_for": "Provides fat and contributes to texture and flavour.",
    },

    "butter": {
        "category": "Dairy / Fat",
        "used_for": "Provides fat, flavour and contributes to texture.",
    },

    "vegetable oil": {
        "category": "Vegetable Oil",
        "used_for": "Provides fat and is used for cooking and texture.",
    },

    # ---------------- DAIRY ----------------

    "milk": {
        "category": "Dairy",
        "used_for": "Provides proteins, carbohydrates, minerals and contributes to texture.",
    },

    "milk powder": {
        "category": "Dairy",
        "used_for": "Provides milk solids, proteins and dairy flavour while improving texture.",
    },

    "skimmed milk powder": {
        "category": "Dairy",
        "used_for": "Provides milk proteins and solids with relatively less fat.",
    },

    "whey": {
        "category": "Dairy Protein",
        "used_for": "Provides dairy proteins and contributes to nutritional and textural properties.",
    },

    "whey powder": {
        "category": "Dairy Protein",
        "used_for": "Used to provide dairy proteins, solids and texture.",
    },

    "cheese": {
        "category": "Dairy",
        "used_for": "Provides dairy fat, proteins and flavour.",
    },

    "cream": {
        "category": "Dairy",
        "used_for": "Provides dairy fat and contributes to richness and texture.",
    },

    "casein": {
        "category": "Dairy Protein",
        "used_for": "Milk protein used for nutritional value, texture and emulsification.",
    },

    "lactose": {
        "category": "Milk Sugar",
        "used_for": "Naturally occurring milk sugar used for sweetness and food formulation.",
    },

    # ---------------- SALTS / MINERALS ----------------

    "salt": {
        "category": "Mineral / Seasoning",
        "used_for": "Adds flavour and can help control moisture and preserve foods.",
    },

    "sodium chloride": {
        "category": "Mineral / Salt",
        "used_for": "Used as salt for flavour and food preservation.",
    },

    "sodium bicarbonate": {
        "category": "Leavening Agent",
        "used_for": "Releases carbon dioxide during baking, helping foods rise.",
    },

    "baking soda": {
        "category": "Leavening Agent",
        "used_for": "Helps baked foods rise by producing carbon dioxide.",
    },

    "calcium carbonate": {
        "category": "Mineral / Food Additive",
        "used_for": "Used as a calcium source, acidity regulator or food additive.",
    },

    # ---------------- LEAVENING / ACIDITY ----------------

    "citric acid": {
        "category": "Acidity Regulator",
        "used_for": "Adds acidity and helps control flavour and product stability.",
    },

    "malic acid": {
        "category": "Acidity Regulator",
        "used_for": "Provides acidity and contributes to flavour.",
    },

    "lactic acid": {
        "category": "Acidity Regulator",
        "used_for": "Used to regulate acidity and contribute to flavour.",
    },

    "tartaric acid": {
        "category": "Acidity Regulator",
        "used_for": "Provides acidity and is commonly used in baking and food formulation.",
    },

    "ammonium bicarbonate": {
        "category": "Leavening Agent",
        "used_for": "Produces gas during baking to help create a light texture.",
    },

    # ---------------- EMULSIFIERS ----------------

    "lecithin": {
        "category": "Emulsifier",
        "used_for": "Helps oil and water-based ingredients mix and improves texture.",
    },

    "soy lecithin": {
        "category": "Emulsifier",
        "used_for": "Helps ingredients mix evenly and improves texture and processing.",
    },

    "mono and diglycerides": {
        "category": "Emulsifier",
        "used_for": "Helps maintain a uniform mixture and improves texture and stability.",
    },

    "mono- and diglycerides": {
        "category": "Emulsifier",
        "used_for": "Helps maintain a uniform mixture and improves texture and stability.",
    },

    # ---------------- THICKENERS / STABILIZERS ----------------

    "xanthan gum": {
        "category": "Thickener / Stabilizer",
        "used_for": "Improves thickness, texture and stability.",
    },

    "guar gum": {
        "category": "Thickener / Stabilizer",
        "used_for": "Adds viscosity and helps stabilize food mixtures.",
    },

    "pectin": {
        "category": "Gelling Agent",
        "used_for": "Helps create gel structure and improve texture.",
    },

    "carrageenan": {
        "category": "Thickener / Stabilizer",
        "used_for": "Used to thicken and stabilize food products.",
    },

    "cellulose": {
        "category": "Food Texture Agent",
        "used_for": "Can provide structure, bulk and texture in processed foods.",
    },

    "modified starch": {
        "category": "Starch / Thickener",
        "used_for": "Modified to improve thickening, stability or texture.",
    },

    # ---------------- PRESERVATIVES ----------------

    "sodium benzoate": {
        "category": "Preservative",
        "used_for": "Helps inhibit the growth of microorganisms and extend shelf life.",
    },

    "potassium sorbate": {
        "category": "Preservative",
        "used_for": "Helps prevent mould and yeast growth and extend shelf life.",
    },

    "sodium metabisulfite": {
        "category": "Preservative / Antioxidant",
        "used_for": "Helps prevent oxidation and microbial spoilage.",
    },

    "sorbic acid": {
        "category": "Preservative",
        "used_for": "Helps control mould and yeast growth.",
    },

    "benzoic acid": {
        "category": "Preservative",
        "used_for": "Helps inhibit microbial growth in food products.",
    },

    # ---------------- FLAVOURS / COLOURS ----------------

    "vanilla": {
        "category": "Flavouring",
        "used_for": "Adds vanilla flavour and aroma.",
    },

    "vanilla extract": {
        "category": "Flavouring",
        "used_for": "Adds vanilla flavour and aroma.",
    },

    "cocoa": {
        "category": "Flavouring / Cocoa",
        "used_for": "Provides chocolate flavour, colour and aroma.",
    },

    "cocoa powder": {
        "category": "Flavouring / Cocoa",
        "used_for": "Provides chocolate flavour, colour and aroma.",
    },

    "natural flavour": {
        "category": "Flavouring",
        "used_for": "Adds or enhances the characteristic flavour of the food.",
    },

    "artificial flavour": {
        "category": "Flavouring",
        "used_for": "Adds or enhances a desired flavour profile.",
    },

    "caramel": {
        "category": "Colour / Flavour",
        "used_for": "Adds brown colour and can contribute caramel-like flavour.",
    },

    # ---------------- PROTEINS ----------------

    "soy protein": {
        "category": "Plant Protein",
        "used_for": "Provides plant-based protein and can improve texture.",
    },

    "pea protein": {
        "category": "Plant Protein",
        "used_for": "Provides plant-based protein and contributes to nutritional content.",
    },

    "milk protein": {
        "category": "Dairy Protein",
        "used_for": "Provides milk-derived protein and contributes to texture.",
    },

    # ---------------- FIBRE ----------------

    "dietary fiber": {
        "category": "Fibre",
        "used_for": "Provides dietary fibre and can contribute to texture and bulk.",
    },

    "fibre": {
        "category": "Fibre",
        "used_for": "Provides dietary fibre and can contribute to texture and bulk.",
    },

    "inulin": {
        "category": "Fibre",
        "used_for": "A type of soluble fibre used for fibre enrichment and texture.",
    },
}


# ============================================================
# ALLERGEN DATABASE
# ============================================================

ALLERGEN_GUIDE = {

    "Milk / Dairy": [
        "milk",
        "milk powder",
        "skimmed milk",
        "skimmed milk powder",
        "whey",
        "whey powder",
        "casein",
        "caseinate",
        "lactose",
        "cream",
        "butter",
        "cheese",
        "milk protein",
    ],

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
        "sooji",
    ],

    "Soy": [
        "soy",
        "soya",
        "soybean",
        "soy protein",
        "soy lecithin",
        "soya lecithin",
    ],

    "Peanut": [
        "peanut",
        "groundnut",
        "peanut flour",
        "peanut butter",
    ],

    "Tree Nuts": [
        "almond",
        "cashew",
        "walnut",
        "pistachio",
        "hazelnut",
        "pecan",
        "macadamia",
    ],

    "Sesame": [
        "sesame",
        "sesame seed",
        "til",
    ],

    "Egg": [
        "egg",
        "egg white",
        "egg yolk",
        "albumen",
    ],
}


# ============================================================
# INGREDIENT CATEGORIES
# ============================================================

CATEGORY_KEYWORDS = {

    "🌾 Grains & Flours": [
        "wheat",
        "flour",
        "rice",
        "corn",
        "maida",
        "atta",
        "oat",
        "barley",
        "rye",
        "semolina",
        "suji",
        "sooji",
    ],

    "🍬 Sugars & Sweeteners": [
        "sugar",
        "glucose",
        "fructose",
        "dextrose",
        "syrup",
        "maltose",
        "sweetener",
        "molasses",
    ],

    "🧈 Fats & Oils": [
        "oil",
        "butter",
        "fat",
        "palmolein",
        "margarine",
    ],

    "🥛 Dairy": [
        "milk",
        "whey",
        "casein",
        "lactose",
        "cream",
        "cheese",
    ],

    "🧂 Salt & Minerals": [
        "salt",
        "sodium",
        "calcium",
        "potassium",
        "magnesium",
    ],

    "🧪 Additives & Preservatives": [
        "benzoate",
        "sorbate",
        "preservative",
        "metabisulfite",
        "sulphite",
        "sulfite",
    ],

    "🧴 Thickeners & Stabilizers": [
        "gum",
        "pectin",
        "carrageenan",
        "starch",
        "cellulose",
        "thickener",
        "stabilizer",
    ],

    "🧬 Emulsifiers": [
        "lecithin",
        "emulsifier",
        "diglyceride",
        "monoglyceride",
    ],

    "🌿 Flavourings": [
        "flavour",
        "flavor",
        "vanilla",
        "cocoa",
        "extract",
        "aroma",
    ],
}


# ============================================================
# SAFE TEXT HELPERS
# ============================================================

def clean_text(value):
    """Safely convert any value into readable text."""
    if value is None:
        return ""

    if isinstance(value, (list, tuple)):
        return ", ".join(str(x) for x in value if x)

    return str(value).strip()


def clean_barcode(barcode):
    """
    Clean barcode input.

    Supports:
    8901234567890
    8901234567890.0
    spaces
    hyphens
    scanner prefixes
    """
    if barcode is None:
        return ""

    barcode = str(barcode).strip()

    # Remove Excel-style .0
    if barcode.endswith(".0"):
        barcode = barcode[:-2]

    # Keep only digits
    digits = re.sub(r"\D", "", barcode)

    return digits


def normalize_ingredient(text):
    """Normalize ingredient name for guide matching."""
    text = clean_text(text).lower()

    text = html.unescape(text)

    text = text.replace("_", " ")
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)

    text = re.sub(r"\s+", " ", text)
    text = text.strip(" ,;:-")

    return text


# ============================================================
# PRODUCT LOOKUP
# ============================================================

def lookup_openfoodfacts(barcode):
    """
    Robust Open Food Facts lookup.

    Returns:
        product dictionary
        or None
    """

    barcode = clean_barcode(barcode)

    if not barcode:
        return None

    urls = [
        OFF_API.format(quote(barcode)),
        f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json",
    ]

    for url in urls:

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code != 200:
                continue

            data = response.json()

            if not isinstance(data, dict):
                continue

            # Open Food Facts normally returns status=1
            if data.get("status") == 1 and data.get("product"):
                return data["product"]

        except requests.exceptions.Timeout:
            continue

        except requests.exceptions.ConnectionError:
            continue

        except requests.exceptions.RequestException:
            continue

        except ValueError:
            continue

        except Exception:
            continue

    return None


# ============================================================
# USDA FALLBACK
# ============================================================

def lookup_usda(product_name):
    """
    USDA fallback for nutrition data.

    This does NOT replace Open Food Facts product identity.
    It is only used when nutrition information is missing.
    """

    if not product_name:
        return None

    try:

        params = {
            "api_key": USDA_API_KEY,
            "query": product_name,
            "pageSize": 1,
        }

        response = requests.get(
            USDA_API,
            params=params,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code != 200:
            return None

        data = response.json()

        foods = data.get("foods", [])

        if foods:
            return foods[0]

    except Exception:
        return None

    return None


# ============================================================
# INGREDIENT EXTRACTION
# ============================================================

def get_ingredient_list(product):
    """
    Extract ingredients from Open Food Facts in several possible formats.
    """

    ingredients = []

    raw = product.get("ingredients", [])

    if isinstance(raw, list):

        for item in raw:

            if isinstance(item, dict):

                text = (
                    item.get("text")
                    or item.get("id")
                    or item.get("ingredient")
                    or ""
                )

            else:
                text = str(item)

            text = clean_text(text)

            if text:
                ingredients.append(text)

    # Fallback to ingredient text
    if not ingredients:

        raw_text = (
            product.get("ingredients_text")
            or product.get("ingredients_text_en")
            or product.get("ingredients_text_fr")
            or ""
        )

        if raw_text:

            # Basic split
            parts = re.split(r",|;|\n", raw_text)

            for part in parts:

                part = part.strip()

                if part:
                    ingredients.append(part)

    # Last fallback: empty list
    return ingredients


# ============================================================
# INGREDIENT EXPLANATION ENGINE
# ============================================================

def get_ingredient_explanation(ingredient):
    """
    Intelligent ingredient explanation.

    First checks exact guide.
    Then checks partial matches.
    Then generates a safe category-based explanation.

    This prevents unknown ingredients from breaking the result page.
    """

    original = clean_text(ingredient)

    normalized = normalize_ingredient(original)

    if not normalized:
        return {
            "name": original,
            "category": "Ingredient",
            "used_for": "Ingredient information is not available.",
        }

    # --------------------------------------------------------
    # Exact match
    # --------------------------------------------------------

    if normalized in INGREDIENT_GUIDE:

        info = INGREDIENT_GUIDE[normalized]

        return {
            "name": original,
            "category": info["category"],
            "used_for": info["used_for"],
        }

    # --------------------------------------------------------
    # Partial match
    # --------------------------------------------------------

    for key, info in INGREDIENT_GUIDE.items():

        if key in normalized or normalized in key:

            return {
                "name": original,
                "category": info["category"],
                "used_for": info["used_for"],
            }

    # --------------------------------------------------------
    # Intelligent generic classification
    # --------------------------------------------------------

    category = "Ingredient"
    explanation = (
        "Used as part of the product's formulation to contribute "
        "to its ingredients, texture, flavour or nutritional composition."
    )

    if any(word in normalized for word in ["starch", "flour"]):

        category = "Starch / Flour"
        explanation = (
            "Provides carbohydrate-based bulk and is commonly used "
            "to contribute to texture, structure or binding."
        )

    elif any(word in normalized for word in ["oil", "fat"]):

        category = "Fat / Oil"
        explanation = (
            "Provides fat and can contribute to texture, mouthfeel "
            "and cooking or processing properties."
        )

    elif any(word in normalized for word in ["sugar", "syrup", "sweetener"]):

        category = "Sweetener"
        explanation = (
            "Used to provide sweetness and may also contribute "
            "to texture, moisture and browning."
        )

    elif any(word in normalized for word in ["acid", "citrate"]):

        category = "Acidity Regulator"
        explanation = (
            "Used to control acidity and can contribute to flavour "
            "and product stability."
        )

    elif any(word in normalized for word in ["gum", "pectin"]):

        category = "Thickener / Stabilizer"
        explanation = (
            "Used to improve thickness, texture or stability."
        )

    elif any(word in normalized for word in [
        "preservative",
        "benzoate",
        "sorbate",
        "sulfite",
        "sulphite",
    ]):

        category = "Preservative"
        explanation = (
            "Used to help maintain product stability and extend shelf life."
        )

    elif any(word in normalized for word in [
        "lecithin",
        "emulsifier",
        "diglyceride",
        "monoglyceride",
    ]):

        category = "Emulsifier"
        explanation = (
            "Helps ingredients that normally do not mix easily "
            "remain evenly distributed."
        )

    elif any(word in normalized for word in [
        "flavour",
        "flavor",
        "aroma",
        "extract",
    ]):

        category = "Flavouring"
        explanation = (
            "Used to provide or enhance the flavour or aroma of the product."
        )

    elif any(word in normalized for word in [
        "vitamin",
        "mineral",
        "iron",
        "calcium",
        "zinc",
        "magnesium",
    ]):

        category = "Nutrient / Fortification"
        explanation = (
            "Used as a nutrient source or for nutritional fortification."
        )

    elif any(word in normalized for word in [
        "protein",
        "peptide",
    ]):

        category = "Protein"
        explanation = (
            "Provides protein and may contribute to the nutritional "
            "or structural properties of the product."
        )

    return {
        "name": original,
        "category": category,
        "used_for": explanation,
    }


# ============================================================
# INGREDIENT ORDER
# ============================================================

def build_ingredient_order(ingredients):
    """
    Open Food Facts generally lists ingredients in descending
    order by quantity.

    The first ingredient is therefore highlighted.
    """

    result = []

    total = len(ingredients)

    for index, ingredient in enumerate(ingredients):

        explanation = get_ingredient_explanation(ingredient)

        if total:
            percentage = round(
                ((total - index) / total) * 100
            )
        else:
            percentage = 0

        explanation["position"] = index + 1
        explanation["percentage"] = percentage

        if index == 0:
            explanation["importance"] = "Primary ingredient"

        elif index < 3:
            explanation["importance"] = "Major ingredient"

        else:
            explanation["importance"] = "Later-listed ingredient"

        result.append(explanation)

    return result


# ============================================================
# ALLERGEN DETECTION
# ============================================================

def detect_allergens(ingredients, product):
    """
    Detect allergens from:
    1. ingredient text
    2. Open Food Facts allergen fields
    """

    detected = []

    ingredient_text = " ".join(
        normalize_ingredient(x)
        for x in ingredients
    )

    # --------------------------------------------------------
    # Built-in guide
    # --------------------------------------------------------

    for allergen, keywords in ALLERGEN_GUIDE.items():

        for keyword in keywords:

            if keyword in ingredient_text:

                if allergen not in detected:
                    detected.append(allergen)

                break

    # --------------------------------------------------------
    # Open Food Facts allergen tags
    # --------------------------------------------------------

    off_allergens = product.get("allergens_tags", [])

    if isinstance(off_allergens, list):

        for item in off_allergens:

            item = clean_text(item).lower()

            mapping = {
                "en:milk": "Milk / Dairy",
                "en:wheat": "Wheat / Gluten",
                "en:gluten": "Wheat / Gluten",
                "en:soybeans": "Soy",
                "en:soya": "Soy",
                "en:peanuts": "Peanut",
                "en:sesame-seeds": "Sesame",
                "en:eggs": "Egg",
                "en:nuts": "Tree Nuts",
            }

            if item in mapping:

                name = mapping[item]

                if name not in detected:
                    detected.append(name)

    return detected


# ============================================================
# CATEGORY DETECTION
# ============================================================

def build_categories(ingredients):
    """
    Groups ingredients into useful smart categories.
    """

    result = []

    for category, keywords in CATEGORY_KEYWORDS.items():

        matches = []

        for ingredient in ingredients:

            normalized = normalize_ingredient(ingredient)

            for keyword in keywords:

                if keyword in normalized:

                    matches.append(ingredient)
                    break

        if matches:

            unique_matches = []

            for item in matches:
                if item not in unique_matches:
                    unique_matches.append(item)

            percentage = min(
                100,
                max(
                    15,
                    len(unique_matches) * 25
                )
            )

            result.append({
                "name": category,
                "ingredients": unique_matches,
                "count": len(unique_matches),
                "percentage": percentage,
            })

    return result


# ============================================================
# NUTRITION HELPERS
# ============================================================

def safe_float(value):
    try:

        if value is None:
            return None

        if isinstance(value, str):

            value = (
                value
                .replace(",", ".")
                .replace("g", "")
                .strip()
            )

        return float(value)

    except Exception:
        return None


def get_nutrient(nutrients, *keys):
    for key in keys:

        value = nutrients.get(key)

        if value is not None:
            return safe_float(value)

    return None


def nutrition_level(value, low, high):
    """
    General visual classification only.
    """

    if value is None:
        return "neutral"

    if value < low:
        return "low"

    if value < high:
        return "medium"

    return "high"


def build_nutrition(product):
    nutrients = product.get("nutriments", {}) or {}

    energy = get_nutrient(
        nutrients,
        "energy-kcal_100g",
        "energy-kcal"
    )

    fat = get_nutrient(
        nutrients,
        "fat_100g",
        "fat"
    )

    saturated = get_nutrient(
        nutrients,
        "saturated-fat_100g",
        "saturated-fat"
    )

    carbohydrates = get_nutrient(
        nutrients,
        "carbohydrates_100g",
        "carbohydrates"
    )

    sugars = get_nutrient(
        nutrients,
        "sugars_100g",
        "sugars"
    )

    fiber = get_nutrient(
        nutrients,
        "fiber_100g",
        "fiber"
    )

    proteins = get_nutrient(
        nutrients,
        "proteins_100g",
        "proteins"
    )

    salt = get_nutrient(
        nutrients,
        "salt_100g",
        "salt"
    )

    sodium = get_nutrient(
        nutrients,
        "sodium_100g",
        "sodium"
    )

    # Salt fallback from sodium
    if salt is None and sodium is not None:
        salt = sodium * 2.5

    items = [

        {
            "name": "Energy",
            "icon": "⚡",
            "value": energy,
            "unit": "kcal",
            "level": (
                "low" if energy is not None and energy < 150
                else "medium" if energy is not None and energy < 400
                else "high" if energy is not None
                else "neutral"
            ),
        },

        {
            "name": "Fat",
            "icon": "🥑",
            "value": fat,
            "unit": "g",
            "level": nutrition_level(fat, 3, 17.5),
        },

        {
            "name": "Saturated Fat",
            "icon": "🧈",
            "value": saturated,
            "unit": "g",
            "level": nutrition_level(saturated, 1.5, 5),
        },

        {
            "name": "Carbohydrates",
            "icon": "🌾",
            "value": carbohydrates,
            "unit": "g",
            "level": nutrition_level(carbohydrates, 10, 50),
        },

        {
            "name": "Sugars",
            "icon": "🍬",
            "value": sugars,
            "unit": "g",
            "level": nutrition_level(sugars, 5, 22.5),
        },

        {
            "name": "Protein",
            "icon": "💪",
            "value": proteins,
            "unit": "g",
            "level": (
                "high" if proteins is not None and proteins >= 10
                else "medium" if proteins is not None and proteins >= 5
                else "low" if proteins is not None
                else "neutral"
            ),
        },

        {
            "name": "Fibre",
            "icon": "🌿",
            "value": fiber,
            "unit": "g",
            "level": (
                "high" if fiber is not None and fiber >= 6
                else "medium" if fiber is not None and fiber >= 3
                else "low" if fiber is not None
                else "neutral"
            ),
        },

        {
            "name": "Salt",
            "icon": "🧂",
            "value": salt,
            "unit": "g",
            "level": nutrition_level(salt, 0.3, 1.5),
        },
    ]

    # Formatting
    for item in items:

        if item["value"] is None:
            item["display"] = "Not available"

        else:
            value = item["value"]

            if abs(value - round(value)) < 0.01:
                value = int(round(value))

            else:
                value = round(value, 1)

            item["display"] = f"{value} {item['unit']}"

    return items


# ============================================================
# NUTRITION INDICATORS
# ============================================================

def build_indicators(product):
    nutrients = product.get("nutriments", {}) or {}

    sugar = get_nutrient(nutrients, "sugars_100g", "sugars")
    saturated = get_nutrient(
        nutrients,
        "saturated-fat_100g",
        "saturated-fat"
    )
    salt = get_nutrient(nutrients, "salt_100g", "salt")

    if salt is None:

        sodium = get_nutrient(
            nutrients,
            "sodium_100g",
            "sodium"
        )

        if sodium is not None:
            salt = sodium * 2.5

    fiber = get_nutrient(
        nutrients,
        "fiber_100g",
        "fiber"
    )

    protein = get_nutrient(
        nutrients,
        "proteins_100g",
        "proteins"
    )

    def indicator(
        name,
        value,
        max_value,
        low,
        medium,
        icon
    ):

        if value is None:

            return {
                "name": name,
                "value": "Not available",
                "percentage": 3,
                "level": "neutral",
                "icon": icon,
            }

        percentage = min(
            100,
            max(
                3,
                round((value / max_value) * 100)
            )
        )

        if value < low:
            level = "low"

        elif value < medium:
            level = "medium"

        else:
            level = "high"

        return {
            "name": name,
            "value": f"{round(value, 1)} g",
            "percentage": percentage,
            "level": level,
            "icon": icon,
        }

    return [

        indicator(
            "Sugar",
            sugar,
            30,
            5,
            15,
            "🍬"
        ),

        indicator(
            "Saturated Fat",
            saturated,
            15,
            1.5,
            5,
            "🧈"
        ),

        indicator(
            "Salt",
            salt,
            3,
            0.3,
            1.5,
            "🧂"
        ),

        indicator(
            "Fibre",
            fiber,
            10,
            3,
            6,
            "🌿"
        ),

        indicator(
            "Protein",
            protein,
            25,
            5,
            10,
            "💪"
        ),
    ]


# ============================================================
# PRODUCT SCORE
# ============================================================

def calculate_score(product, ingredients, allergens):
    """
    Simple transparent visual score.

    This is NOT a medical or official nutrition rating.
    """

    score = 70

    nutrients = product.get("nutriments", {}) or {}

    sugar = get_nutrient(
        nutrients,
        "sugars_100g",
        "sugars"
    )

    saturated = get_nutrient(
        nutrients,
        "saturated-fat_100g",
        "saturated-fat"
    )

    salt = get_nutrient(
        nutrients,
        "salt_100g",
        "salt"
    )

    fiber = get_nutrient(
        nutrients,
        "fiber_100g",
        "fiber"
    )

    protein = get_nutrient(
        nutrients,
        "proteins_100g",
        "proteins"
    )

    # Positive
    if fiber is not None and fiber >= 3:
        score += 7

    if protein is not None and protein >= 5:
        score += 5

    # Negative
    if sugar is not None:

        if sugar >= 22.5:
            score -= 15

        elif sugar >= 15:
            score -= 8

    if saturated is not None:

        if saturated >= 5:
            score -= 10

        elif saturated >= 1.5:
            score -= 4

    if salt is not None:

        if salt >= 1.5:
            score -= 10

        elif salt >= 0.3:
            score -= 4

    # Allergen presence isn't treated as "bad nutrition"
    # but we can mention it separately.
    score = max(0, min(100, score))

    if score >= 75:

        label = "Good"

        description = (
            "The available nutrition information gives this product "
            "a relatively favourable overall profile."
        )

        css = "good"

    elif score >= 50:

        label = "Moderate"

        description = (
            "Some nutritional factors deserve attention when considering "
            "this product."
        )

        css = "moderate"

    else:

        label = "Needs Attention"

        description = (
            "Several available nutritional factors are relatively high "
            "or the overall profile needs closer attention."
        )

        css = "attention"

    return {
        "score": score,
        "label": label,
        "description": description,
        "css": css,
    }


# ============================================================
# COMPLETE PRODUCT ANALYSIS
# ============================================================

def analyze_product(product, barcode=None):
    """
    Build every dataset required by the existing result interface.
    """

    ingredients = get_ingredient_list(product)

    ingredient_details = build_ingredient_order(
        ingredients
    )

    allergens = detect_allergens(
        ingredients,
        product
    )

    categories = build_categories(
        ingredients
    )

    nutrition = build_nutrition(
        product
    )

    indicators = build_indicators(
        product
    )

    score = calculate_score(
        product,
        ingredients,
        allergens
    )

    # Product name
    product_name = (
        product.get("product_name")
        or product.get("product_name_en")
        or product.get("generic_name")
        or "Unknown Product"
    )

    brand = (
        product.get("brands")
        or "Brand not available"
    )

    image = (
        product.get("image_front_url")
        or product.get("image_url")
        or product.get("image_small_url")
        or ""
    )

    product_code = (
        clean_barcode(barcode)
        or clean_barcode(product.get("code"))
    )

    ingredients_text = (
        product.get("ingredients_text")
        or product.get("ingredients_text_en")
        or ""
    )

    return {
        "product": product,

        "product_name": product_name,
        "brand": brand,
        "image": image,
        "barcode": product_code,

        "ingredients": ingredients,
        "ingredients_text": ingredients_text,

        "ingredient_details": ingredient_details,
        "ingredient_order": ingredient_details,

        "allergens": allergens,
        "detected_allergens": allergens,

        "categories": categories,
        "ingredient_categories": categories,

        "nutrition": nutrition,
        "nutrition_items": nutrition,

        "indicators": indicators,
        "nutrition_indicators": indicators,

        "score": score,
        "analysis": score,

        "quantity": product.get("quantity", ""),
        "serving_size": product.get("serving_size", ""),
        "countries": product.get("countries", ""),
        "categories_text": product.get("categories", ""),
        "brands": brand,

        "nutriscore": (
            product.get("nutriscore_grade")
            or product.get("nutriscore_score")
            or "N/A"
        ),

        "nova": (
            product.get("nova_group")
            or "N/A"
        ),
    }


# ============================================================
# ERROR PAGE DATA
# ============================================================

def error_context(message, barcode=""):
    return {
        "error": message,
        "barcode": barcode,
    }


# ============================================================
# HOME
# ============================================================

@app.route("/", methods=["GET"])
def index():

    return render_template(
        "index.html",
        product=None,
        result=None,
        error=None,
        comparison=None,
    )


# ============================================================
# BARCODE / PRODUCT SEARCH
# ============================================================

@app.route("/search", methods=["POST"])
def search():

    try:

        barcode = (
            request.form.get("barcode")
            or request.form.get("code")
            or request.form.get("product_code")
            or ""
        )

        barcode = clean_barcode(barcode)

        if not barcode:

            return render_template(
                "index.html",
                product=None,
                result=None,
                error="Please enter a valid barcode.",
                comparison=None,
            )

        # ----------------------------------------------------
        # Open Food Facts
        # ----------------------------------------------------

        product = lookup_openfoodfacts(barcode)

        if product is None:

            return render_template(
                "index.html",
                product=None,
                result=None,
                error=(
                    f"No product was found for barcode {barcode}. "
                    "Please check the barcode and try again."
                ),
                comparison=None,
            )

        # ----------------------------------------------------
        # Analyze
        # ----------------------------------------------------

        result = analyze_product(
            product,
            barcode
        )

        return render_template(
            "index.html",
            product=product,
            result=result,
            error=None,
            comparison=None,
        )

    except Exception as e:

        print("SEARCH ERROR:", repr(e))

        return render_template(
            "index.html",
            product=None,
            result=None,
            error=(
                "The product could not be processed. "
                "Please try the barcode again."
            ),
            comparison=None,
        )


# ============================================================
# MANUAL PRODUCT INPUT
# ============================================================

@app.route("/manual", methods=["POST"])
def manual():

    try:

        product_name = (
            request.form.get("product_name")
            or request.form.get("name")
            or "Manual Product"
        )

        ingredients_text = (
            request.form.get("ingredients")
            or request.form.get("ingredient_text")
            or ""
        )

        calories = request.form.get("calories", "")
        fat = request.form.get("fat", "")
        saturated_fat = request.form.get("saturated_fat", "")
        carbohydrates = request.form.get("carbohydrates", "")
        sugars = request.form.get("sugars", "")
        protein = request.form.get("protein", "")
        fiber = request.form.get("fiber", "")
        salt = request.form.get("salt", "")

        ingredient_parts = re.split(
            r",|;|\n",
            ingredients_text
        )

        ingredient_parts = [
            x.strip()
            for x in ingredient_parts
            if x.strip()
        ]

        product = {
            "product_name": product_name,
            "brands": request.form.get("brand", "Manual Entry"),
            "ingredients_text": ingredients_text,
            "ingredients": [
                {"text": x}
                for x in ingredient_parts
            ],
            "nutriments": {
                "energy-kcal_100g": safe_float(calories),
                "fat_100g": safe_float(fat),
                "saturated-fat_100g": safe_float(saturated_fat),
                "carbohydrates_100g": safe_float(carbohydrates),
                "sugars_100g": safe_float(sugars),
                "proteins_100g": safe_float(protein),
                "fiber_100g": safe_float(fiber),
                "salt_100g": safe_float(salt),
            },
        }

        result = analyze_product(product)

        return render_template(
            "index.html",
            product=product,
            result=result,
            error=None,
            comparison=None,
        )

    except Exception as e:

        print("MANUAL ERROR:", repr(e))

        return render_template(
            "index.html",
            product=None,
            result=None,
            error="Unable to process the manual product information.",
            comparison=None,
        )


# ============================================================
# COMPARISON HELPER
# ============================================================

def get_comparison_data(product_a, product_b):

    a = analyze_product(product_a)
    b = analyze_product(product_b)

    return {
        "product_a": a,
        "product_b": b,
    }


# ============================================================
# PRODUCT COMPARISON
# ============================================================

@app.route("/compare", methods=["POST"])
def compare():

    try:

        barcode_a = clean_barcode(
            request.form.get("barcode1")
            or request.form.get("barcode_a")
            or ""
        )

        barcode_b = clean_barcode(
            request.form.get("barcode2")
            or request.form.get("barcode_b")
            or ""
        )

        if not barcode_a or not barcode_b:

            return render_template(
                "index.html",
                product=None,
                result=None,
                error="Please enter both product barcodes.",
                comparison=None,
            )

        product_a = lookup_openfoodfacts(barcode_a)
        product_b = lookup_openfoodfacts(barcode_b)

        if product_a is None:

            return render_template(
                "index.html",
                product=None,
                result=None,
                error=f"Product 1 was not found for barcode {barcode_a}.",
                comparison=None,
            )

        if product_b is None:

            return render_template(
                "index.html",
                product=None,
                result=None,
                error=f"Product 2 was not found for barcode {barcode_b}.",
                comparison=None,
            )

        comparison = get_comparison_data(
            product_a,
            product_b
        )

        return render_template(
            "index.html",
            product=None,
            result=None,
            error=None,
            comparison=comparison,
        )

    except Exception as e:

        print("COMPARE ERROR:", repr(e))

        return render_template(
            "index.html",
            product=None,
            result=None,
            error="Unable to compare these products right now.",
            comparison=None,
        )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "service": "ProductLens",
    }


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("ProductLens — Food Intelligence")
    print("=" * 60)
    print("Server: http://127.0.0.1:5000")
    print("Health: http://127.0.0.1:5000/health")
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
    )
