from flask import Flask, render_template, request, jsonify
import requests
import re

app = Flask(__name__)

# =========================================================
# PRODUCTLENS - API SETTINGS
# =========================================================

OFF_API = "https://world.openfoodfacts.org/api/v2/product/{}.json"
USDA_API = "https://api.nal.usda.gov/fdc/v1/foods/search"
USDA_API_KEY = "DEMO_KEY"


# =========================================================
# ALLERGEN DATABASE
# =========================================================

ALLERGEN_GUIDE = {
    "Wheat / Gluten": [
        "wheat", "wheat flour", "whole wheat", "whole wheat flour",
        "maida", "atta", "gluten", "wheat starch", "wheat protein",
        "wheat gluten", "semolina", "suji", "sooji", "rava"
    ],

    "Milk / Dairy": [
        "milk", "milk powder", "milk solids", "skimmed milk",
        "skim milk", "milk protein", "milk fat", "whey",
        "whey powder", "whey protein", "casein", "caseinate",
        "sodium caseinate", "calcium caseinate", "lactose",
        "butter", "cream", "dairy", "cheese", "curd", "ghee"
    ],

    "Tree Nuts": [
        "almond", "almonds", "cashew", "cashews", "walnut",
        "walnuts", "pistachio", "pistachios", "hazelnut",
        "hazelnuts", "pecan", "pecans", "macadamia"
    ],

    "Peanuts": [
        "peanut", "peanuts", "groundnut", "groundnuts",
        "ground nut", "peanut oil", "peanut flour"
    ],

    "Soy": [
        "soy", "soya", "soybean", "soybeans", "soy protein",
        "soy lecithin", "soya lecithin", "soy flour"
    ],

    "Sesame": ["sesame", "sesame seeds", "sesame seed", "til"],

    "Mustard": ["mustard", "mustard seeds", "mustard seed"],

    "Egg": [
        "egg", "eggs", "egg powder", "egg white", "egg yolk", "albumin"
    ]
}

ALLERGEN_ICONS = {
    "Wheat / Gluten": "🌾",
    "Milk / Dairy": "🥛",
    "Tree Nuts": "🥜",
    "Peanuts": "🥜",
    "Soy": "🫘",
    "Sesame": "🌱",
    "Mustard": "🌿",
    "Egg": "🥚"
}


# =========================================================
# SAFE NUMBER
# =========================================================

def safe_number(value, default=0):
    try:
        if value is None:
            return default

        if isinstance(value, str):
            value = value.replace(",", "").strip()

            if value == "":
                return default

        return float(value)

    except (ValueError, TypeError):
        return default


# =========================================================
# TEXT MATCHING
# =========================================================

def keyword_found(keyword, text):
    keyword = str(keyword).lower().strip()
    text = str(text).lower()

    keyword = keyword.replace("en:", "")
    keyword = keyword.replace("-", " ")
    keyword = keyword.replace("_", " ")

    parts = keyword.split()

    if not parts:
        return False

    pattern = r"(?<![a-z])" + r"\s+".join(
        re.escape(part) for part in parts
    ) + r"(?![a-z])"

    return re.search(pattern, text) is not None


# =========================================================
# ALLERGEN DETECTION
# =========================================================

def detect_allergens(*texts):
    combined_text = " ".join(
        str(text) for text in texts if text
    ).lower()

    if not combined_text:
        return []

    combined_text = combined_text.replace("en:", " ")
    combined_text = combined_text.replace("-", " ")
    combined_text = combined_text.replace("_", " ")
    combined_text = combined_text.replace(";", " ")
    combined_text = combined_text.replace(",", " ")

    detected = []

    for allergen, keywords in ALLERGEN_GUIDE.items():

        found_keyword = None

        for keyword in sorted(keywords, key=len, reverse=True):
            if keyword_found(keyword, combined_text):
                found_keyword = keyword
                break

        if found_keyword:
            detected.append({
                "name": allergen,
                "icon": ALLERGEN_ICONS.get(allergen, "⚠️"),
                "keyword": found_keyword
            })

    return detected


# =========================================================
# NUTRITION LEVELS
# =========================================================

def nutrition_level(value, nutrient):

    value = safe_number(value)

    if nutrient == "sugar":
        if value <= 5:
            return {"level": "Low", "class": "low"}
        elif value <= 15:
            return {"level": "Moderate", "class": "moderate"}
        return {"level": "High", "class": "high"}

    if nutrient == "fat":
        if value <= 3:
            return {"level": "Low", "class": "low"}
        elif value <= 17.5:
            return {"level": "Moderate", "class": "moderate"}
        return {"level": "High", "class": "high"}

    if nutrient == "salt":
        if value <= 0.3:
            return {"level": "Low", "class": "low"}
        elif value <= 1.5:
            return {"level": "Moderate", "class": "moderate"}
        return {"level": "High", "class": "high"}

    if nutrient == "protein":
        if value >= 10:
            return {"level": "High", "class": "high"}
        elif value >= 5:
            return {"level": "Moderate", "class": "moderate"}
        return {"level": "Low", "class": "low"}

    return {"level": "Not available", "class": "neutral"}


# =========================================================
# PROGRESS BAR
# =========================================================

def progress_bar(value, nutrient):

    value = safe_number(value)

    maximums = {
        "energy": 700,
        "sugar": 25,
        "fat": 30,
        "protein": 20,
        "salt": 3
    }

    maximum = maximums.get(nutrient, 100)

    percent = (value / maximum) * 100
    percent = max(0, min(percent, 100))

    if nutrient == "energy":

        if value <= 200:
            level_class = "low"
        elif value <= 500:
            level_class = "moderate"
        else:
            level_class = "high"

    else:
        level_class = nutrition_level(value, nutrient)["class"]

    return {
        "percent": round(percent, 1),
        "class": level_class
    }


# =========================================================
# INGREDIENT PARSER
# =========================================================

def get_ingredient_order(ingredients):

    if not ingredients:
        return []

    text = str(ingredients)

    # Normalize common separators
    text = text.replace(";", ",")

    parts = text.split(",")

    cleaned = []

    for part in parts:

        part = part.strip()

        # Remove leading numbering
        part = re.sub(r"^\s*\d+[\.\)]\s*", "", part)

        if part:
            cleaned.append(part)

    return cleaned


# =========================================================
# INGREDIENT CATEGORY DETECTION
# =========================================================

def get_ingredient_categories(ingredients):

    if not ingredients:
        return []

    text = str(ingredients).lower()

    categories_data = {

        "🌾 Cereals / Grains": [
            "wheat", "flour", "rice", "maida", "atta",
            "corn", "barley", "semolina", "suji",
            "sooji", "rava", "oat", "potato"
        ],

        "🍬 Sugars / Sweeteners": [
            "sugar", "glucose", "fructose", "syrup",
            "maltose", "dextrose", "honey", "sweetener"
        ],

        "🛢️ Oils / Fats": [
            "oil", "fat", "butter", "palm",
            "sunflower", "vegetable oil", "coconut oil"
        ],

        "🧂 Salt / Minerals": [
            "salt", "sodium", "potassium", "calcium"
        ],

        "🌿 Spices / Herbs": [
            "spice", "spices", "pepper", "chilli",
            "chili", "turmeric", "cumin", "coriander"
        ],

        "🧪 Additives": [
            "preservative", "emulsifier", "stabilizer",
            "stabiliser", "colour", "color", "flavour",
            "flavor", "acidity regulator", "thickener",
            "raising agent", "antioxidant", "humectant"
        ]
    }

    categories = []

    for category, keywords in categories_data.items():

        found = []

        for keyword in keywords:

            if keyword_found(keyword, text):
                found.append(keyword)

        if found:

            categories.append({
                "icon": category.split()[0],
                "title": category[2:],
                "ingredients": list(dict.fromkeys(found))
            })

    return categories


# =========================================================
# INGREDIENT INTELLIGENCE DATABASE
# =========================================================

INGREDIENT_GUIDE = {

    "potato": {
        "name": "🥔 Potato",
        "role": "Base ingredient / carbohydrate source",
        "description": "A starchy vegetable that can provide carbohydrates, bulk and structure to the food.",
        "purpose": "Provides starch, bulk, texture and carbohydrate content.",
        "confidence": "High",
        "source": "Ingredient label + ProductLens ingredient knowledge base"
    },

    "potato starch": {
        "name": "🥔 Potato Starch",
        "role": "Thickener / texture agent",
        "description": "Starch extracted from potatoes and commonly used to provide thickness and improve texture.",
        "purpose": "Provides thickening, structure and texture.",
        "confidence": "High",
        "source": "Ingredient label + ProductLens ingredient knowledge base"
    },

    "sugar": {
        "name": "🍬 Sugar",
        "role": "Sweetener",
        "description": "A carbohydrate ingredient primarily used to provide sweetness.",
        "purpose": "Provides sweetness and contributes carbohydrate content.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "glucose": {
        "name": "🍬 Glucose",
        "role": "Sweetener / carbohydrate",
        "description": "A simple sugar used as a carbohydrate source and sweetening ingredient.",
        "purpose": "Provides sweetness and carbohydrate content.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "dextrose": {
        "name": "🍬 Dextrose",
        "role": "Sweetener",
        "description": "A form of glucose commonly used in food products.",
        "purpose": "Provides sweetness and carbohydrate content.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "fructose": {
        "name": "🍯 Fructose",
        "role": "Sweetener",
        "description": "A naturally occurring simple sugar.",
        "purpose": "Provides sweetness.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "syrup": {
        "name": "🍯 Syrup",
        "role": "Sweetener / texture ingredient",
        "description": "A concentrated sweetening ingredient that can also affect texture.",
        "purpose": "Provides sweetness and contributes to texture.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "honey": {
        "name": "🍯 Honey",
        "role": "Sweetener",
        "description": "A natural sweetening ingredient.",
        "purpose": "Provides sweetness and flavour.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "salt": {
        "name": "🧂 Salt",
        "role": "Flavouring / preservation",
        "description": "A mineral salt commonly used for flavour and, in some products, preservation.",
        "purpose": "Provides salty flavour and sodium.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "sodium": {
        "name": "🧂 Sodium",
        "role": "Mineral",
        "description": "A mineral element commonly present in sodium-containing food ingredients.",
        "purpose": "Contributes sodium content.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "wheat flour": {
        "name": "🌾 Wheat Flour",
        "role": "Structure / base ingredient",
        "description": "Flour produced from wheat and widely used as a structural ingredient.",
        "purpose": "Provides bulk, structure and carbohydrates.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "wheat": {
        "name": "🌾 Wheat",
        "role": "Cereal grain",
        "description": "A cereal grain commonly used as a carbohydrate and structural ingredient.",
        "purpose": "Provides carbohydrates, bulk and structure.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "rice": {
        "name": "🍚 Rice",
        "role": "Cereal / carbohydrate",
        "description": "A cereal grain that primarily contributes carbohydrates.",
        "purpose": "Provides carbohydrate content and bulk.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "corn": {
        "name": "🌽 Corn",
        "role": "Cereal / carbohydrate",
        "description": "A cereal grain used as a food base or carbohydrate source.",
        "purpose": "Provides bulk and carbohydrate content.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "semolina": {
        "name": "🌾 Semolina",
        "role": "Cereal / structural ingredient",
        "description": "A coarse flour generally produced from durum wheat.",
        "purpose": "Provides structure, bulk and carbohydrates.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "vegetable oil": {
        "name": "🛢️ Vegetable Oil",
        "role": "Fat / texture ingredient",
        "description": "Plant-derived oil used in food preparation and formulation.",
        "purpose": "Provides fat, texture and cooking properties.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "palm oil": {
        "name": "🌴 Palm Oil",
        "role": "Fat / texture ingredient",
        "description": "A vegetable oil commonly used for texture and stability.",
        "purpose": "Provides fat and contributes to texture.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "sunflower oil": {
        "name": "🌻 Sunflower Oil",
        "role": "Fat / cooking ingredient",
        "description": "A plant-based oil used as a source of dietary fat.",
        "purpose": "Provides fat and contributes to texture.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "coconut oil": {
        "name": "🥥 Coconut Oil",
        "role": "Fat / flavour ingredient",
        "description": "A plant-based fat used in food formulation.",
        "purpose": "Provides fat and contributes to texture and flavour.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "butter": {
        "name": "🧈 Butter",
        "role": "Dairy fat",
        "description": "A dairy-derived fat used for flavour and texture.",
        "purpose": "Provides dairy fat, flavour and texture.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "milk": {
        "name": "🥛 Milk",
        "role": "Dairy ingredient",
        "description": "A dairy ingredient containing components such as protein, lactose and fat.",
        "purpose": "Provides dairy flavour, nutrients and texture.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "milk powder": {
        "name": "🥛 Milk Powder",
        "role": "Dairy ingredient",
        "description": "Dried milk solids used in food formulation.",
        "purpose": "Provides dairy flavour, protein and texture.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "whey protein": {
        "name": "🥛 Whey Protein",
        "role": "Protein ingredient",
        "description": "A milk-derived protein ingredient.",
        "purpose": "Increases protein content and may contribute functional properties.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "whey": {
        "name": "🥛 Whey",
        "role": "Dairy ingredient",
        "description": "A milk-derived ingredient containing proteins and other milk components.",
        "purpose": "Provides dairy components and contributes to nutritional composition.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "casein": {
        "name": "🥛 Casein",
        "role": "Milk protein",
        "description": "A major milk protein used for nutritional and functional properties.",
        "purpose": "Provides protein and functional properties.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "soy": {
        "name": "🫘 Soy",
        "role": "Plant protein / food ingredient",
        "description": "A soybean-derived ingredient used as a protein or functional food ingredient.",
        "purpose": "Provides plant protein and may contribute texture.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "soy lecithin": {
        "name": "🫘 Soy Lecithin",
        "role": "Emulsifier",
        "description": "A soy-derived lecithin used to help oil- and water-based components remain mixed.",
        "purpose": "Improves mixing and product consistency.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "lecithin": {
        "name": "🔄 Lecithin",
        "role": "Emulsifier",
        "description": "A food emulsifier that helps normally difficult-to-mix ingredients remain combined.",
        "purpose": "Helps maintain a uniform mixture.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "emulsifier": {
        "name": "🔄 Emulsifier",
        "role": "Emulsifier",
        "description": "A food ingredient used to help different components remain evenly mixed.",
        "purpose": "Improves mixture stability and consistency.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "citric acid": {
        "name": "🍋 Citric Acid",
        "role": "Acidity regulator",
        "description": "An organic acid commonly used to control acidity and provide sourness.",
        "purpose": "Controls acidity and contributes sour taste.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "acidity regulator": {
        "name": "⚖️ Acidity Regulator",
        "role": "Acidity regulator",
        "description": "A food ingredient used to control or maintain acidity.",
        "purpose": "Controls product acidity and pH.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "sodium benzoate": {
        "name": "🧪 Sodium Benzoate",
        "role": "Preservative",
        "description": "A preservative commonly used to help control microbial spoilage.",
        "purpose": "Helps extend shelf life by limiting microbial growth.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "potassium sorbate": {
        "name": "🧪 Potassium Sorbate",
        "role": "Preservative",
        "description": "A preservative commonly used to control mould and yeast growth.",
        "purpose": "Helps extend shelf life.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "preservative": {
        "name": "🧪 Preservative",
        "role": "Preservative",
        "description": "A food additive used to slow spoilage.",
        "purpose": "Helps extend shelf life.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "xanthan gum": {
        "name": "⚗️ Xanthan Gum",
        "role": "Thickener / stabilizer",
        "description": "A hydrocolloid commonly used to increase viscosity and stabilize texture.",
        "purpose": "Improves thickness, consistency and stability.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "guar gum": {
        "name": "⚗️ Guar Gum",
        "role": "Thickener / stabilizer",
        "description": "A plant-derived hydrocolloid used to thicken food products.",
        "purpose": "Improves viscosity and texture.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "modified starch": {
        "name": "🌽 Modified Starch",
        "role": "Thickener / texture agent",
        "description": "Starch modified to provide specific functional properties in food.",
        "purpose": "Improves thickness, structure, texture or stability.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "starch": {
        "name": "🌽 Starch",
        "role": "Thickener / carbohydrate",
        "description": "A carbohydrate polymer commonly used for structure and texture.",
        "purpose": "Provides carbohydrate content and can improve thickness or structure.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "stabilizer": {
        "name": "⚗️ Stabilizer",
        "role": "Stabilizer",
        "description": "A food ingredient used to maintain physical consistency and stability.",
        "purpose": "Helps maintain texture and product stability.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "thickener": {
        "name": "🥣 Thickener",
        "role": "Thickener",
        "description": "An ingredient used to increase viscosity.",
        "purpose": "Improves thickness and texture.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "msg": {
        "name": "✨ MSG",
        "role": "Flavour enhancer",
        "description": "Monosodium glutamate is used to enhance savoury flavour.",
        "purpose": "Enhances umami/savoury taste.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "monosodium glutamate": {
        "name": "✨ Monosodium Glutamate",
        "role": "Flavour enhancer",
        "description": "A flavour-enhancing food additive.",
        "purpose": "Enhances savoury/umami flavour.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "natural flavour": {
        "name": "🌿 Natural Flavour",
        "role": "Flavouring",
        "description": "A flavouring ingredient used to provide or enhance flavour.",
        "purpose": "Provides or enhances flavour.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "flavour": {
        "name": "👃 Flavouring",
        "role": "Flavouring",
        "description": "A flavouring ingredient used to provide or enhance product flavour.",
        "purpose": "Provides or enhances flavour.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "flavor": {
        "name": "👃 Flavouring",
        "role": "Flavouring",
        "description": "A flavouring ingredient used to provide or enhance product flavour.",
        "purpose": "Provides or enhances flavour.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "colour": {
        "name": "🎨 Food Colour",
        "role": "Colouring agent",
        "description": "A food colouring ingredient used to provide or restore product colour.",
        "purpose": "Provides or improves product colour.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "color": {
        "name": "🎨 Food Colour",
        "role": "Colouring agent",
        "description": "A food colouring ingredient used to provide or restore product colour.",
        "purpose": "Provides or improves product colour.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "egg": {
        "name": "🥚 Egg",
        "role": "Protein / structural ingredient",
        "description": "An animal-derived food ingredient that can contribute protein, structure, binding and texture.",
        "purpose": "Provides protein and may contribute structure, binding or emulsification.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "egg powder": {
        "name": "🥚 Egg Powder",
        "role": "Protein / binding ingredient",
        "description": "Dried egg used in food formulations.",
        "purpose": "Provides protein and can contribute binding and structure.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "peanut": {
        "name": "🥜 Peanut",
        "role": "Legume / protein and fat",
        "description": "A legume commonly used for protein, fat, flavour and texture.",
        "purpose": "Provides protein, fat and characteristic flavour.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "almond": {
        "name": "🥜 Almond",
        "role": "Tree nut / protein and fat",
        "description": "A tree nut commonly used for flavour, texture, protein and fat.",
        "purpose": "Provides flavour, texture, protein and fat.",
        "confidence": "High",
        "source": "Ingredient label"
    },

    "cashew": {
        "name": "🥜 Cashew",
        "role": "Tree nut / fat and texture",
        "description": "A tree nut commonly used for flavour and texture.",
        "purpose": "Provides flavour, fat and texture.",
        "confidence": "High",
        "source": "Ingredient label"
    }
}


# =========================================================
# INGREDIENT DETECTIVE
# =========================================================

def get_ingredient_details(ingredients):

    ingredient_list = get_ingredient_order(ingredients)

    if not ingredient_list:
        return []

    details = []

    for ingredient in ingredient_list:

        clean = ingredient.strip()

        # Remove percentage declarations
        lookup = re.sub(
            r"\(\s*\d+(?:\.\d+)?\s*%\s*\)",
            "",
            clean
        )

        lookup = lookup.lower().strip()

        matched_key = None

        # Longest/most specific terms first
        for key in sorted(INGREDIENT_GUIDE.keys(), key=len, reverse=True):

            if keyword_found(key, lookup):

                matched_key = key
                break

        if matched_key:

            info = INGREDIENT_GUIDE[matched_key]

            details.append({
                "ingredient": clean,
                "role": info["role"],
                "code": "",
                "description": info["description"],
                "purpose": info["purpose"],
                "confidence": info["confidence"],
                "source": info["source"]
            })

        else:

            # IMPORTANT:
            # Unknown ingredients are still shown individually,
            # but are clearly labelled as unclassified instead of
            # pretending that ProductLens knows their function.

            details.append({
                "ingredient": clean,
                "role": "Food ingredient — function not classified",
                "code": "",
                "description": (
                    "This exact ingredient was found in the product "
                    "label/database, but ProductLens does not currently "
                    "have enough evidence in its supported ingredient "
                    "knowledge base to assign a specific technological function."
                ),
                "purpose": (
                    "The package declaration remains the primary evidence. "
                    "No function is guessed."
                ),
                "confidence": "Label confirmed; function not classified",
                "source": "Product label/database"
            })

    return details


# =========================================================
# SMART HIGHLIGHTS
# =========================================================

def make_smart_highlights(product):

    highlights = []

    sugar = safe_number(product.get("sugar"))
    fat = safe_number(product.get("fat"))
    protein = safe_number(product.get("protein"))
    salt = safe_number(product.get("salt"))

    allergens = product.get("detected_allergens", [])

    if sugar > 15:

        highlights.append({
            "icon": "🍬",
            "title": "High Sugar",
            "text": "Sugar is relatively high per 100 g."
        })

    elif 0 < sugar <= 5:

        highlights.append({
            "icon": "✅",
            "title": "Lower Sugar",
            "text": "Sugar is relatively low per 100 g."
        })

    if fat > 17.5:

        highlights.append({
            "icon": "🛢️",
            "title": "Higher Fat",
            "text": "Total fat is relatively high per 100 g."
        })

    if protein >= 10:

        highlights.append({
            "icon": "💪",
            "title": "Higher Protein",
            "text": "Protein is relatively high per 100 g."
        })

    if salt > 1.5:

        highlights.append({
            "icon": "🧂",
            "title": "High Salt",
            "text": "Salt is relatively high per 100 g."
        })

    if allergens:

        names = ", ".join(
            item["name"] for item in allergens
        )

        highlights.append({
            "icon": "🚨",
            "title": "Allergens Detected",
            "text": names
        })

    if not highlights:

        highlights.append({
            "icon": "🔬",
            "title": "Product Analysis",
            "text": "Review the nutrition and ingredient information below."
        })

    return highlights


# =========================================================
# HEALTH CAUTIONS
# =========================================================

def disease_cautions(product):

    cautions = []

    sugar = safe_number(product.get("sugar"))
    salt = safe_number(product.get("salt"))
    fat = safe_number(product.get("fat"))

    allergens = product.get("detected_allergens", [])

    if sugar > 15:

        cautions.append({
            "icon": "🩸",
            "title": "High Sugar Caution",
            "text": (
                "This product contains a high amount of sugar per 100 g. "
                "People managing blood glucose may need to consider "
                "portion size and their overall diet."
            ),
            "class": "danger"
        })

    if salt > 1.5:

        cautions.append({
            "icon": "❤️",
            "title": "High Salt Caution",
            "text": (
                "This product contains a relatively high amount of salt "
                "per 100 g. People managing blood pressure may need to "
                "monitor salt intake."
            ),
            "class": "danger"
        })

    if fat > 17.5:

        cautions.append({
            "icon": "❤️",
            "title": "Higher Fat Caution",
            "text": (
                "This product is relatively high in total fat per 100 g. "
                "The type of fat and overall dietary pattern also matter."
            ),
            "class": "caution"
        })

    if allergens:

        names = ", ".join(
            item["name"] for item in allergens
        )

        cautions.insert(0, {
            "icon": "🚨",
            "title": "ALLERGEN ALERT",
            "text": (
                "Potential allergens detected: "
                + names +
                ". Always check the package label and allergen declaration."
            ),
            "class": "danger"
        })

    return cautions


# =========================================================
# ADDITIVE INTELLIGENCE
# =========================================================

ADDITIVE_GUIDE = {

    "e100": ("Curcumin", "Colour", "Food colouring agent"),

    "e101": ("Riboflavin", "Colour", "Colouring agent and vitamin"),

    "e102": ("Tartrazine", "Colour", "Food colouring agent"),

    "e110": ("Sunset Yellow FCF", "Colour", "Food colouring agent"),

    "e120": ("Carmine", "Colour", "Food colouring agent"),

    "e129": ("Allura Red AC", "Colour", "Food colouring agent"),

    "e150": ("Caramel Colour", "Colour", "Food colouring agent"),

    "e160": ("Carotenoids", "Colour", "Food colouring agents"),

    "e200": ("Sorbic Acid", "Preservative", "Helps inhibit microbial growth"),

    "e202": ("Potassium Sorbate", "Preservative", "Helps control mould and yeast"),

    "e211": ("Sodium Benzoate", "Preservative", "Helps control microbial spoilage"),

    "e220": ("Sulphur Dioxide", "Preservative", "Preservative and antioxidant"),

    "e300": ("Ascorbic Acid", "Antioxidant", "Helps limit oxidation"),

    "e301": ("Sodium Ascorbate", "Antioxidant", "Antioxidant ingredient"),

    "e322": ("Lecithins", "Emulsifier", "Helps maintain uniform mixtures"),

    "e330": ("Citric Acid", "Acidity Regulator", "Controls acidity and contributes sour taste"),

    "e407": ("Carrageenan", "Thickener / Stabilizer", "Improves texture and stability"),

    "e410": ("Locust Bean Gum", "Thickener / Stabilizer", "Improves viscosity and texture"),

    "e412": ("Guar Gum", "Thickener / Stabilizer", "Improves viscosity and texture"),

    "e415": ("Xanthan Gum", "Thickener / Stabilizer", "Improves viscosity and stability"),

    "e420": ("Sorbitol", "Humectant / Sweetener", "Provides sweetness and helps retain moisture"),

    "e440": ("Pectins", "Gelling / Thickening Agent", "Helps form gels and improve texture"),

    "e450": ("Diphosphates", "Raising / Stabilizing Agent", "Used for functional and leavening properties"),

    "e621": ("Monosodium Glutamate", "Flavour Enhancer", "Enhances savoury flavour")
}


def get_regulatory_insights(ingredients):

    if not ingredients:
        return []

    text = str(ingredients).lower()

    results = []

    for code, data in ADDITIVE_GUIDE.items():

        if keyword_found(code, text):

            name, role, purpose = data

            results.append({
                "code": code.upper(),
                "name": name,
                "role": role,
                "purpose": purpose,
                "source": "ProductLens additive reference database"
            })

    return results


# =========================================================
# FINALIZE PRODUCT
# =========================================================

def finalize_product(product):

    for nutrient in [
        "energy",
        "sugar",
        "fat",
        "protein",
        "salt"
    ]:

        product[nutrient] = safe_number(
            product.get(nutrient)
        )

    product["sugar_level"] = nutrition_level(
        product["sugar"],
        "sugar"
    )

    product["fat_level"] = nutrition_level(
        product["fat"],
        "fat"
    )

    product["protein_level"] = nutrition_level(
        product["protein"],
        "protein"
    )

    product["salt_level"] = nutrition_level(
        product["salt"],
        "salt"
    )

    ingredients = product.get("ingredients", "") or ""

    declared_allergens = product.get(
        "allergens",
        ""
    ) or ""

    allergen_tags = product.get(
        "allergen_tags",
        ""
    ) or ""

    product["detected_allergens"] = detect_allergens(
        ingredients,
        declared_allergens,
        allergen_tags
    )

    # Ingredient order
    product["ingredient_order"] = get_ingredient_order(
        ingredients
    )

    # Categories
    product["ingredient_categories"] = get_ingredient_categories(
        ingredients
    )

    # MAIN FIX:
    # The HTML uses product.ingredient_details
    product["ingredient_details"] = get_ingredient_details(
        ingredients
    )

    # Keep old key too, so older parts of the template continue working
    product["decoded_ingredients"] = product["ingredient_details"]

    # Additive intelligence
    product["regulatory_insights"] = get_regulatory_insights(
        ingredients
    )

    # Smart highlights
    product["smart_highlights"] = make_smart_highlights(
        product
    )

    # Health cautions
    product["disease_cautions"] = disease_cautions(
        product
    )

    # Nutrition bars
    product["energy_bar"] = progress_bar(
        product["energy"],
        "energy"
    )

    product["sugar_bar"] = progress_bar(
        product["sugar"],
        "sugar"
    )

    product["fat_bar"] = progress_bar(
        product["fat"],
        "fat"
    )

    product["protein_bar"] = progress_bar(
        product["protein"],
        "protein"
    )

    product["salt_bar"] = progress_bar(
        product["salt"],
        "salt"
    )

    return product


# =========================================================
# OPEN FOOD FACTS
# =========================================================

def get_from_open_food_facts(barcode):

    print("\n" + "=" * 60)
    print("DATABASE 1: OPEN FOOD FACTS")
    print("Searching barcode:", barcode)

    try:

        url = OFF_API.format(barcode)

        response = requests.get(
            url,
            headers={
                "User-Agent":
                "ProductLens/2.0 (food analysis application)"
            },
            timeout=15
        )

        print(
            "OFF STATUS CODE:",
            response.status_code
        )

        response.raise_for_status()

        data = response.json()

    except requests.exceptions.RequestException as e:

        print(
            "Open Food Facts error:",
            e
        )

        return None

    except ValueError:

        print(
            "Invalid Open Food Facts JSON."
        )

        return None

    if data.get("status") != 1:

        print(
            "Product not found in Open Food Facts."
        )

        return None

    raw = data.get(
        "product",
        {}
    ) or {}

    ingredients = raw.get(
        "ingredients_text",
        ""
    ) or ""

    declared_allergens = raw.get(
        "allergens",
        ""
    ) or ""

    allergen_tags = raw.get(
        "allergens_tags",
        []
    ) or []

    allergen_tags_text = " ".join(
        str(item)
        for item in allergen_tags
    )

    nutrition = raw.get(
        "nutriments",
        {}
    ) or {}

    energy = nutrition.get(
        "energy-kcal_100g",
        nutrition.get(
            "energy-kcal",
            0
        )
    )

    product = {

        "name": raw.get(
            "product_name",
            "Unknown Product"
        ),

        "brands": raw.get(
            "brands",
            ""
        ),

        "barcode": barcode,

        "image": raw.get(
            "image_front_url",
            ""
        ),

        "ingredients": ingredients,

        "allergens": declared_allergens,

        "allergen_tags": allergen_tags_text,

        "energy": energy,

        "sugar": nutrition.get(
            "sugars_100g",
            0
        ),

        "fat": nutrition.get(
            "fat_100g",
            0
        ),

        "protein": nutrition.get(
            "proteins_100g",
            0
        ),

        "salt": nutrition.get(
            "salt_100g",
            0
        ),

        "source": "Open Food Facts",

        "verified": True
    }

    product = finalize_product(
        product
    )

    print(
        "Product found:",
        product["name"]
    )

    print(
        "Ingredient count:",
        len(product["ingredient_details"])
    )

    return product


# =========================================================
# USDA FOODDATA CENTRAL
# =========================================================

def get_from_usda(barcode):

    print("\n" + "=" * 60)
    print("DATABASE 2: USDA FOODDATA CENTRAL")
    print("Searching barcode:", barcode)

    try:

        params = {
            "api_key": USDA_API_KEY,
            "query": barcode,
            "pageSize": 10
        }

        response = requests.get(
            USDA_API,
            params=params,
            timeout=15
        )

        print(
            "USDA STATUS CODE:",
            response.status_code
        )

        response.raise_for_status()

        data = response.json()

    except requests.exceptions.RequestException as e:

        print(
            "USDA connection error:",
            e
        )

        return None

    except ValueError:

        print(
            "Invalid USDA response."
        )

        return None

    foods = data.get(
        "foods",
        []
    ) or []

    if not foods:
        return None

    food = foods[0]

    nutrients = food.get(
        "foodNutrients",
        []
    ) or []

    energy = 0
    sugar = 0
    fat = 0
    protein = 0
    sodium = 0

    for nutrient in nutrients:

        name = str(
            nutrient.get(
                "nutrientName",
                ""
            )
        ).lower()

        value = safe_number(
            nutrient.get(
                "value",
                0
            )
        )

        if "energy" in name and "kcal" in name:
            energy = value

        elif "sugars, total" in name:
            sugar = value

        elif name == "total lipid (fat)":
            fat = value

        elif name == "protein":
            protein = value

        elif name == "sodium":
            sodium = value

    # Sodium mg -> approximate salt g
    salt = sodium * 2.5 / 1000

    product = {

        "name": food.get(
            "description",
            "Unknown Product"
        ),

        "brands": food.get(
            "brandOwner",
            ""
        ),

        "barcode": barcode,

        "image": "",

        "ingredients": food.get(
            "ingredients",
            ""
        ) or "",

        "allergens": "",

        "allergen_tags": "",

        "energy": energy,

        "sugar": sugar,

        "fat": fat,

        "protein": protein,

        "salt": salt,

        "source": "USDA FoodData Central",

        "verified": True
    }

    return finalize_product(
        product
    )


# =========================================================
# SEARCH PRODUCT
# =========================================================

def search_product(barcode):

    barcode = str(
        barcode
    ).strip()

    if not barcode.isdigit():
        return None

    product = get_from_open_food_facts(
        barcode
    )

    if product:
        return product

    print(
        "Open Food Facts failed."
    )

    print(
        "Trying USDA FoodData Central..."
    )

    return get_from_usda(
        barcode
    )


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# BARCODE SEARCH
# =========================================================

@app.route(
    "/search",
    methods=["POST"]
)
def search():

    barcode = request.form.get(
        "barcode",
        ""
    ).strip()

    if not barcode:

        return render_template(
            "index.html",
            error="Please enter or scan a barcode."
        )

    if not barcode.isdigit():

        return render_template(
            "index.html",
            error="Barcode should contain numbers only."
        )

    product = search_product(
        barcode
    )

    if product:

        return render_template(
            "index.html",
            product=product,
            auto_scroll=True
        )

    return render_template(
        "index.html",
        show_manual_form=True,
        missing_barcode=barcode,
        error=(
            "Product was not found in Open Food Facts or USDA. "
            "You can enter the product information manually below."
        ),
        auto_scroll=True
    )


# =========================================================
# JSON SEARCH API
# =========================================================

@app.route(
    "/api/search/<barcode>",
    methods=["GET"]
)
def api_search(barcode):

    barcode = str(
        barcode
    ).strip()

    if not barcode.isdigit():

        return jsonify({
            "success": False,
            "error": "Barcode should contain numbers only."
        }), 400

    product = search_product(
        barcode
    )

    if not product:

        return jsonify({
            "success": False,
            "error": "Product not found."
        }), 404

    return jsonify({
        "success": True,
        "product": product
    })


# =========================================================
# MANUAL ENTRY
# =========================================================

@app.route(
    "/manual",
    methods=["POST"]
)
def manual():

    barcode = request.form.get(
        "barcode",
        ""
    ).strip()

    name = request.form.get(
        "name",
        ""
    ).strip()

    brand = request.form.get(
        "brand",
        ""
    ).strip()

    ingredients = request.form.get(
        "ingredients",
        ""
    ).strip()

    allergens = request.form.get(
        "allergens",
        ""
    ).strip()

    energy = request.form.get(
        "energy",
        0
    )

    sugar = request.form.get(
        "sugar",
        0
    )

    fat = request.form.get(
        "fat",
        0
    )

    protein = request.form.get(
        "protein",
        0
    )

    salt = request.form.get(
        "salt",
        0
    )

    if not name:

        return render_template(
            "index.html",
            error="Product name is required.",
            show_manual_form=True,
            missing_barcode=barcode
        )

    product = {

        "name": name,

        "brands": brand,

        "barcode": barcode,

        "image": "",

        "ingredients": ingredients,

        "allergens": allergens,

        "allergen_tags": "",

        "energy": energy,

        "sugar": sugar,

        "fat": fat,

        "protein": protein,

        "salt": salt,

        "source": "Manual Entry",

        "verified": False
    }

    product = finalize_product(
        product
    )

    return render_template(
        "index.html",
        product=product,
        manual_success=True,
        manual_saved=bool(
            barcode and barcode.isdigit()
        ),
        auto_scroll=True
    )


# =========================================================
# COMPARE
# =========================================================

@app.route(
    "/compare",
    methods=["POST"]
)
def compare():

    barcode1 = request.form.get(
        "barcode1",
        ""
    ).strip()

    barcode2 = request.form.get(
        "barcode2",
        ""
    ).strip()

    if not barcode1 or not barcode2:

        return render_template(
            "index.html",
            compare_error="Please enter both barcodes."
        )

    if not barcode1.isdigit() or not barcode2.isdigit():

        return render_template(
            "index.html",
            compare_error="Both barcodes should contain numbers only."
        )

    product1 = search_product(
        barcode1
    )

    product2 = search_product(
        barcode2
    )

    if not product1 or not product2:

        return render_template(
            "index.html",
            compare_error="One or both products could not be found."
        )

    rows = []

    nutrients = [
        ("Energy", "energy", "kcal"),
        ("Sugar", "sugar", "g"),
        ("Fat", "fat", "g"),
        ("Protein", "protein", "g"),
        ("Salt", "salt", "g")
    ]

    for label, key, unit in nutrients:

        value1 = safe_number(
            product1.get(key)
        )

        value2 = safe_number(
            product2.get(key)
        )

        if key == "protein":

            if value1 > value2:
                result = "Product 1 has more protein"

            elif value2 > value1:
                result = "Product 2 has more protein"

            else:
                result = "Same"

        else:

            if value1 < value2:
                result = "Product 1 is lower"

            elif value2 < value1:
                result = "Product 2 is lower"

            else:
                result = "Same"

        rows.append({

            "label": label,

            "value1": value1,

            "value2": value2,

            "unit": unit,

            "result": result
        })

    insights = []

    if product1["sugar"] < product2["sugar"]:

        insights.append(
            product1["name"] +
            " has less sugar."
        )

    elif product2["sugar"] < product1["sugar"]:

        insights.append(
            product2["name"] +
            " has less sugar."
        )

    if product1["protein"] > product2["protein"]:

        insights.append(
            product1["name"] +
            " has more protein."
        )

    elif product2["protein"] > product1["protein"]:

        insights.append(
            product2["name"] +
            " has more protein."
        )

    comparison = {

        "product1": product1,

        "product2": product2,

        "rows": rows,

        "insights": insights
    }

    return render_template(
        "index.html",
        comparison=comparison,
        auto_scroll=True
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("PRODUCTLENS")
    print("Food Ingredient & Nutrition Intelligence")
    print("=" * 60)
    print()

    print(
        "Starting Flask server..."
    )

    print(
        "Open on this PC: http://127.0.0.1:5000"
    )

    print(
        "For phone on same Wi-Fi, use your PC's local IP + :5000"
    )

    print()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
