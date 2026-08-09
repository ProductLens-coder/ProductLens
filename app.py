from flask import Flask, render_template, request, jsonify
import requests
import re
import time
from functools import lru_cache

app = Flask(__name__)

# ============================================================
# PRODUCTLENS
# SMART FOOD INTELLIGENCE ENGINE
# ============================================================

APP_NAME = "ProductLens"
APP_VERSION = "3.0"

USER_AGENT = (
    f"{APP_NAME}/{APP_VERSION} "
    "(food intelligence application; "
    "contact: productlens@example.com)"
)

REQUEST_TIMEOUT = 15


# ============================================================
# DATA SOURCES
# ============================================================

# Open Food Facts
# v3 is the current recommended API.
OFF_API = (
    "https://world.openfoodfacts.org/api/v3/product/{}.json"
)

# USDA FoodData Central
USDA_API = "https://api.nal.usda.gov/fdc/v1/foods/search"

# IMPORTANT:
# Do NOT use DEMO_KEY in production.
# USDA fallback is used only when a real key is configured.
USDA_API_KEY = ""


# ============================================================
# FSSAI
# ============================================================

# FSSAI is treated as the primary Indian regulatory authority.
#
# FSSAI does NOT provide a public barcode -> full ingredient
# database API that ProductLens can truthfully use for every
# product.
#
# Therefore:
#
# FSSAI = regulatory authority
# OFF    = product/label database
# USDA   = nutrition fallback
#
# FSSAI license verification page:
FSSAI_VERIFY_URL = "https://foscos.fssai.gov.in/"

FSSAI_REGULATORY_SOURCE = (
    "FSSAI Food Products Standards and Food Additives Regulations"
)


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "application/json"
})


# ============================================================
# SIMPLE CACHE
# ============================================================

CACHE = {}

CACHE_SECONDS = 900


def cache_get(key):

    item = CACHE.get(key)

    if not item:
        return None

    timestamp, value = item

    if time.time() - timestamp > CACHE_SECONDS:

        CACHE.pop(key, None)

        return None

    return value


def cache_set(key, value):

    CACHE[key] = (
        time.time(),
        value
    )


# ============================================================
# SAFE NUMBER
# ============================================================

def safe_number(value, default=0):

    try:

        if value is None:
            return default

        if isinstance(value, str):

            value = value.replace(",", "")
            value = value.strip()

            if value == "":
                return default

        return float(value)

    except (ValueError, TypeError):

        return default


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):

    if text is None:
        return ""

    text = str(text).lower()

    text = text.replace("en:", " ")
    text = text.replace("fr:", " ")
    text = text.replace("hi:", " ")

    text = text.replace("_", " ")
    text = text.replace("-", " ")

    text = text.replace("&", " and ")

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# KEYWORD MATCHING
# ============================================================

def keyword_found(keyword, text):

    keyword = normalize_text(keyword)
    text = normalize_text(text)

    if not keyword or not text:
        return False

    pattern = (
        r"(?<![a-z])"
        +
        r"\s+".join(
            re.escape(x)
            for x in keyword.split()
        )
        +
        r"(?![a-z])"
    )

    return re.search(
        pattern,
        text
    ) is not None


# ============================================================
# ALLERGEN DATABASE
# ============================================================

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
        "sooji",
        "rava",
        "durum"
    ],

    "Milk / Dairy": [
        "milk",
        "milk powder",
        "milk solids",
        "skimmed milk",
        "skim milk",
        "milk protein",
        "milk fat",
        "whey",
        "whey powder",
        "whey protein",
        "casein",
        "caseinate",
        "sodium caseinate",
        "calcium caseinate",
        "lactose",
        "butter",
        "cream",
        "dairy",
        "cheese",
        "curd",
        "ghee"
    ],

    "Tree Nuts": [
        "almond",
        "almonds",
        "cashew",
        "cashews",
        "walnut",
        "walnuts",
        "pistachio",
        "pistachios",
        "hazelnut",
        "hazelnuts",
        "pecan",
        "pecans",
        "macadamia"
    ],

    "Peanuts": [
        "peanut",
        "peanuts",
        "groundnut",
        "groundnuts",
        "ground nut",
        "peanut oil",
        "peanut flour"
    ],

    "Soy": [
        "soy",
        "soya",
        "soybean",
        "soybeans",
        "soy protein",
        "soy lecithin",
        "soya lecithin",
        "soy flour"
    ],

    "Sesame": [
        "sesame",
        "sesame seeds",
        "sesame seed",
        "til"
    ],

    "Mustard": [
        "mustard",
        "mustard seeds",
        "mustard seed"
    ],

    "Egg": [
        "egg",
        "eggs",
        "egg powder",
        "egg white",
        "egg yolk",
        "albumin"
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


# ============================================================
# ALLERGEN DETECTION
# ============================================================

def detect_allergens(*texts):

    combined = " ".join(
        str(x)
        for x in texts
        if x
    )

    combined = normalize_text(
        combined
    )

    detected = []

    for allergen, keywords in ALLERGEN_GUIDE.items():

        matched = None

        for keyword in sorted(
            keywords,
            key=len,
            reverse=True
        ):

            if keyword_found(
                keyword,
                combined
            ):

                matched = keyword

                break

        if matched:

            detected.append({

                "name": allergen,

                "icon": ALLERGEN_ICONS.get(
                    allergen,
                    "⚠️"
                ),

                "keyword": matched

            })

    return detected


# ============================================================
# NUTRITION CLASSIFICATION
# ============================================================

def nutrition_level(
    value,
    nutrient
):

    value = safe_number(value)

    if nutrient == "sugar":

        if value <= 5:
            return {
                "level": "Low",
                "class": "low"
            }

        if value <= 15:
            return {
                "level": "Moderate",
                "class": "moderate"
            }

        return {
            "level": "High",
            "class": "high"
        }

    if nutrient == "fat":

        if value <= 3:
            return {
                "level": "Low",
                "class": "low"
            }

        if value <= 17.5:
            return {
                "level": "Moderate",
                "class": "moderate"
            }

        return {
            "level": "High",
            "class": "high"
        }

    if nutrient == "salt":

        if value <= 0.3:
            return {
                "level": "Low",
                "class": "low"
            }

        if value <= 1.5:
            return {
                "level": "Moderate",
                "class": "moderate"
            }

        return {
            "level": "High",
            "class": "high"
        }

    if nutrient == "protein":

        if value >= 10:
            return {
                "level": "High",
                "class": "high"
            }

        if value >= 5:
            return {
                "level": "Moderate",
                "class": "moderate"
            }

        return {
            "level": "Low",
            "class": "low"
        }

    return {
        "level": "Not available",
        "class": "neutral"
    }


# ============================================================
# PROGRESS BAR
# ============================================================

def progress_bar(
    value,
    nutrient
):

    value = safe_number(value)

    maximums = {

        "energy": 700,

        "sugar": 25,

        "fat": 30,

        "protein": 20,

        "salt": 3
    }

    maximum = maximums.get(
        nutrient,
        100
    )

    percent = (
        value / maximum
    ) * 100

    percent = max(
        0,
        min(percent, 100)
    )

    if nutrient == "energy":

        if value <= 200:
            level_class = "low"

        elif value <= 500:
            level_class = "moderate"

        else:
            level_class = "high"

    else:

        level_class = nutrition_level(
            value,
            nutrient
        )["class"]

    return {

        "percent": round(
            percent,
            1
        ),

        "class": level_class
    }


# ============================================================
# INGREDIENT ALIASES
# ============================================================

INGREDIENT_ALIASES = {

    "aloo": "potato",

    "batata": "potato",

    "maida": "wheat flour",

    "atta": "wheat flour",

    "suji": "semolina",

    "sooji": "semolina",

    "rava": "semolina",

    "sodium chloride": "salt",

    "common salt": "salt",

    "table salt": "salt",

    "monosodium glutamate": "msg",

    "msg": "msg",

    "ascorbic acid": "vitamin c",

    "citric acid": "citric acid",

    "sunflower": "sunflower oil",

    "palm": "palm oil",

    "vegetable fat": "vegetable oil",

    "vegetable oil": "vegetable oil",

    "milk solids": "milk",

    "skimmed milk powder": "milk powder",

    "skim milk powder": "milk powder",

    "soya lecithin": "soy lecithin",

    "soy lecithin": "soy lecithin"
}


# ============================================================
# INGREDIENT INTELLIGENCE DATABASE
#
# This is deliberately broader than the original dictionary.
# The engine also has rule-based classification below.
# ============================================================

INGREDIENT_GUIDE = {

    "potato": {
        "name": "🥔 Potato",
        "role": "Base ingredient / carbohydrate source",
        "description": (
            "A starchy vegetable commonly used as a food "
            "base and carbohydrate source."
        ),
        "purpose": (
            "Provides starch, bulk, texture and carbohydrates."
        ),
        "confidence": "High"
    },

    "potato starch": {
        "name": "🥔 Potato Starch",
        "role": "Thickener / texture agent",
        "description": (
            "Starch extracted from potatoes and used "
            "for texture and structure."
        ),
        "purpose": (
            "Provides starch-based thickening, structure "
            "and texture."
        ),
        "confidence": "High"
    },

    "sugar": {
        "name": "🍬 Sugar",
        "role": "Sweetener",
        "description": (
            "A carbohydrate ingredient primarily used "
            "to provide sweetness."
        ),
        "purpose": (
            "Provides sweetness and carbohydrate content."
        ),
        "confidence": "High"
    },

    "glucose": {
        "name": "🍬 Glucose",
        "role": "Sweetener / carbohydrate",
        "description": (
            "A simple carbohydrate used in food formulations."
        ),
        "purpose": (
            "Provides sweetness and carbohydrate content."
        ),
        "confidence": "High"
    },

    "dextrose": {
        "name": "🍬 Dextrose",
        "role": "Sweetener",
        "description": (
            "A form of glucose used as a food carbohydrate "
            "and sweetening ingredient."
        ),
        "purpose": (
            "Provides sweetness and carbohydrate."
        ),
        "confidence": "High"
    },

    "fructose": {
        "name": "🍯 Fructose",
        "role": "Sweetener",
        "description": (
            "A naturally occurring simple sugar."
        ),
        "purpose": "Provides sweetness.",
        "confidence": "High"
    },

    "syrup": {
        "name": "🍯 Syrup",
        "role": "Sweetener / texture ingredient",
        "description": (
            "A concentrated sweetening ingredient."
        ),
        "purpose": (
            "Provides sweetness and can influence texture."
        ),
        "confidence": "High"
    },

    "honey": {
        "name": "🍯 Honey",
        "role": "Sweetener",
        "description": (
            "A natural sweetening ingredient."
        ),
        "purpose": (
            "Provides sweetness and characteristic flavour."
        ),
        "confidence": "High"
    },

    "salt": {
        "name": "🧂 Salt",
        "role": "Flavouring / sodium source",
        "description": (
            "Sodium chloride used primarily for flavour "
            "and formulation."
        ),
        "purpose": (
            "Provides salty flavour and sodium."
        ),
        "confidence": "High"
    },

    "wheat flour": {
        "name": "🌾 Wheat Flour",
        "role": "Base / structural ingredient",
        "description": (
            "Flour produced from wheat and widely used "
            "as a structural food ingredient."
        ),
        "purpose": (
            "Provides bulk, structure and carbohydrates."
        ),
        "confidence": "High"
    },

    "wheat": {
        "name": "🌾 Wheat",
        "role": "Cereal grain",
        "description": (
            "A cereal grain used as a carbohydrate "
            "and structural ingredient."
        ),
        "purpose": (
            "Provides carbohydrates, bulk and structure."
        ),
        "confidence": "High"
    },

    "rice": {
        "name": "🍚 Rice",
        "role": "Cereal / carbohydrate",
        "description": (
            "A cereal grain primarily contributing carbohydrates."
        ),
        "purpose": (
            "Provides carbohydrate content and bulk."
        ),
        "confidence": "High"
    },

    "corn": {
        "name": "🌽 Corn",
        "role": "Cereal / carbohydrate",
        "description": (
            "A cereal ingredient used as a food base "
            "or carbohydrate source."
        ),
        "purpose": (
            "Provides bulk and carbohydrates."
        ),
        "confidence": "High"
    },

    "semolina": {
        "name": "🌾 Semolina",
        "role": "Cereal / structural ingredient",
        "description": (
            "A coarse flour generally produced from durum wheat."
        ),
        "purpose": (
            "Provides structure, bulk and carbohydrates."
        ),
        "confidence": "High"
    },

    "vegetable oil": {
        "name": "🛢️ Vegetable Oil",
        "role": "Fat / texture ingredient",
        "description": (
            "Plant-derived oil used in food formulation."
        ),
        "purpose": (
            "Provides fat and contributes to texture."
        ),
        "confidence": "High"
    },

    "palm oil": {
        "name": "🌴 Palm Oil",
        "role": "Fat / texture ingredient",
        "description": (
            "A vegetable oil used for fat, texture "
            "and formulation properties."
        ),
        "purpose": (
            "Provides fat and contributes to texture."
        ),
        "confidence": "High"
    },

    "sunflower oil": {
        "name": "🌻 Sunflower Oil",
        "role": "Plant oil / fat",
        "description": (
            "A plant-derived oil used as a source of dietary fat."
        ),
        "purpose": (
            "Provides fat and cooking/formulation properties."
        ),
        "confidence": "High"
    },

    "coconut oil": {
        "name": "🥥 Coconut Oil",
        "role": "Plant fat",
        "description": (
            "A plant-derived fat used in food formulation."
        ),
        "purpose": (
            "Provides fat and contributes to texture/flavour."
        ),
        "confidence": "High"
    },

    "butter": {
        "name": "🧈 Butter",
        "role": "Dairy fat",
        "description": (
            "A dairy-derived fat used for flavour and texture."
        ),
        "purpose": (
            "Provides dairy fat, flavour and texture."
        ),
        "confidence": "High"
    },

    "milk": {
        "name": "🥛 Milk",
        "role": "Dairy ingredient",
        "description": (
            "A dairy ingredient containing protein, "
            "lactose and fat."
        ),
        "purpose": (
            "Provides dairy components, nutrients and texture."
        ),
        "confidence": "High"
    },

    "milk powder": {
        "name": "🥛 Milk Powder",
        "role": "Dairy ingredient",
        "description": (
            "Dried milk solids used in food formulations."
        ),
        "purpose": (
            "Provides dairy solids, protein and texture."
        ),
        "confidence": "High"
    },

    "whey": {
        "name": "🥛 Whey",
        "role": "Dairy ingredient",
        "description": (
            "A milk-derived ingredient containing proteins "
            "and other milk components."
        ),
        "purpose": (
            "Provides dairy components and contributes to nutrition."
        ),
        "confidence": "High"
    },

    "whey protein": {
        "name": "🥛 Whey Protein",
        "role": "Protein ingredient",
        "description": (
            "A milk-derived protein ingredient."
        ),
        "purpose": (
            "Increases protein content and can contribute "
            "functional properties."
        ),
        "confidence": "High"
    },

    "casein": {
        "name": "🥛 Casein",
        "role": "Milk protein",
        "description": (
            "A major milk protein used for nutritional "
            "and functional properties."
        ),
        "purpose": (
            "Provides protein and functional properties."
        ),
        "confidence": "High"
    },

    "soy": {
        "name": "🫘 Soy",
        "role": "Plant protein / ingredient",
        "description": (
            "A soybean-derived food ingredient."
        ),
        "purpose": (
            "Provides plant protein and can contribute texture."
        ),
        "confidence": "High"
    },

    "soy lecithin": {
        "name": "🫘 Soy Lecithin",
        "role": "Emulsifier",
        "description": (
            "A soy-derived lecithin used to help "
            "oil- and water-based components mix."
        ),
        "purpose": (
            "Improves mixing and product consistency."
        ),
        "confidence": "High"
    },

    "lecithin": {
        "name": "🔄 Lecithin",
        "role": "Emulsifier",
        "description": (
            "A food emulsifier that helps components "
            "remain uniformly mixed."
        ),
        "purpose": (
            "Helps maintain a uniform mixture."
        ),
        "confidence": "High"
    },

    "citric acid": {
        "name": "🍋 Citric Acid",
        "role": "Acidity regulator",
        "description": (
            "An organic acid commonly used to control acidity."
        ),
        "purpose": (
            "Controls acidity and contributes sour taste."
        ),
        "confidence": "High"
    },

    "sodium benzoate": {
        "name": "🧪 Sodium Benzoate",
        "role": "Preservative",
        "description": (
            "A preservative used to control microbial spoilage."
        ),
        "purpose": (
            "Helps extend shelf life by limiting microbial growth."
        ),
        "confidence": "High"
    },

    "potassium sorbate": {
        "name": "🧪 Potassium Sorbate",
        "role": "Preservative",
        "description": (
            "A preservative commonly used to control "
            "mould and yeast."
        ),
        "purpose": (
            "Helps extend shelf life."
        ),
        "confidence": "High"
    },

    "xanthan gum": {
        "name": "⚗️ Xanthan Gum",
        "role": "Thickener / stabilizer",
        "description": (
            "A hydrocolloid used to increase viscosity "
            "and stabilize texture."
        ),
        "purpose": (
            "Improves thickness, consistency and stability."
        ),
        "confidence": "High"
    },

    "guar gum": {
        "name": "⚗️ Guar Gum",
        "role": "Thickener / stabilizer",
        "description": (
            "A plant-derived hydrocolloid used for thickening."
        ),
        "purpose": (
            "Improves viscosity and texture."
        ),
        "confidence": "High"
    },

    "modified starch": {
        "name": "🌽 Modified Starch",
        "role": "Thickener / texture agent",
        "description": (
            "Starch modified to provide specific "
            "functional properties."
        ),
        "purpose": (
            "Improves thickness, structure, texture or stability."
        ),
        "confidence": "High"
    },

    "starch": {
        "name": "🌽 Starch",
        "role": "Carbohydrate / texture agent",
        "description": (
            "A carbohydrate polymer commonly used "
            "for structure and texture."
        ),
        "purpose": (
            "Provides carbohydrates and can improve "
            "structure or texture."
        ),
        "confidence": "High"
    },

    "msg": {
        "name": "✨ MSG",
        "role": "Flavour enhancer",
        "description": (
            "Monosodium glutamate is used to enhance savoury flavour."
        ),
        "purpose": (
            "Enhances umami/savoury taste."
        ),
        "confidence": "High"
    },

    "monosodium glutamate": {
        "name": "✨ Monosodium Glutamate",
        "role": "Flavour enhancer",
        "description": (
            "A flavour-enhancing food additive."
        ),
        "purpose": (
            "Enhances savoury/umami flavour."
        ),
        "confidence": "High"
    },

    "natural flavour": {
        "name": "🌿 Natural Flavour",
        "role": "Flavouring",
        "description": (
            "A flavouring ingredient used to provide "
            "or enhance flavour."
        ),
        "purpose": (
            "Provides or enhances flavour."
        ),
        "confidence": "High"
    },

    "flavour": {
        "name": "👃 Flavouring",
        "role": "Flavouring",
        "description": (
            "A flavouring ingredient used to provide "
            "or enhance product flavour."
        ),
        "purpose": (
            "Provides or enhances flavour."
        ),
        "confidence": "High"
    },

    "color": {
        "name": "🎨 Food Colour",
        "role": "Colouring agent",
        "description": (
            "A food colouring ingredient used to provide "
            "or restore product colour."
        ),
        "purpose": (
            "Provides or improves product colour."
        ),
        "confidence": "High"
    },

    "colour": {
        "name": "🎨 Food Colour",
        "role": "Colouring agent",
        "description": (
            "A food colouring ingredient used to provide "
            "or restore product colour."
        ),
        "purpose": (
            "Provides or improves product colour."
        ),
        "confidence": "High"
    },

    "egg": {
        "name": "🥚 Egg",
        "role": "Protein / structural ingredient",
        "description": (
            "An animal-derived ingredient that can contribute "
            "protein, structure and binding."
        ),
        "purpose": (
            "Provides protein and can contribute structure "
            "and emulsification."
        ),
        "confidence": "High"
    },

    "egg powder": {
        "name": "🥚 Egg Powder",
        "role": "Protein / binding ingredient",
        "description": (
            "Dried egg used in food formulations."
        ),
        "purpose": (
            "Provides protein and can contribute binding and structure."
        ),
        "confidence": "High"
    },

    "peanut": {
        "name": "🥜 Peanut",
        "role": "Legume / protein and fat",
        "description": (
            "A legume commonly used for protein, fat, "
            "flavour and texture."
        ),
        "purpose": (
            "Provides protein, fat and characteristic flavour."
        ),
        "confidence": "High"
    },

    "almond": {
        "name": "🥜 Almond",
        "role": "Tree nut / protein and fat",
        "description": (
            "A tree nut commonly used for flavour, "
            "texture, protein and fat."
        ),
        "purpose": (
            "Provides flavour, texture, protein and fat."
        ),
        "confidence": "High"
    },

    "cashew": {
        "name": "🥜 Cashew",
        "role": "Tree nut / fat and texture",
        "description": (
            "A tree nut commonly used for flavour and texture."
        ),
        "purpose": (
            "Provides flavour, fat and texture."
        ),
        "confidence": "High"
    }
}


# ============================================================
# ADDITIVE / INS / E-NUMBER INTELLIGENCE
#
# FSSAI is the regulatory reference.
# The mapping is used only to interpret a declared additive.
# ============================================================

ADDITIVE_GUIDE = {

    "e100": (
        "Curcumin",
        "Colour",
        "Food colouring agent"
    ),

    "e101": (
        "Riboflavin",
        "Colour / vitamin",
        "Colouring agent"
    ),

    "e102": (
        "Tartrazine",
        "Colour",
        "Food colouring agent"
    ),

    "e110": (
        "Sunset Yellow FCF",
        "Colour",
        "Food colouring agent"
    ),

    "e120": (
        "Carmine",
        "Colour",
        "Food colouring agent"
    ),

    "e129": (
        "Allura Red AC",
        "Colour",
        "Food colouring agent"
    ),

    "e150": (
        "Caramel Colour",
        "Colour",
        "Food colouring agent"
    ),

    "e160": (
        "Carotenoids",
        "Colour",
        "Food colouring agent"
    ),

    "e200": (
        "Sorbic Acid",
        "Preservative",
        "Helps inhibit microbial growth"
    ),

    "e202": (
        "Potassium Sorbate",
        "Preservative",
        "Helps control mould and yeast"
    ),

    "e211": (
        "Sodium Benzoate",
        "Preservative",
        "Helps control microbial spoilage"
    ),

    "e220": (
        "Sulphur Dioxide",
        "Preservative / antioxidant",
        "Helps control oxidation and microbial growth"
    ),

    "e300": (
        "Ascorbic Acid",
        "Antioxidant",
        "Helps limit oxidation"
    ),

    "e301": (
        "Sodium Ascorbate",
        "Antioxidant",
        "Antioxidant ingredient"
    ),

    "e322": (
        "Lecithins",
        "Emulsifier",
        "Helps maintain uniform mixtures"
    ),

    "e330": (
        "Citric Acid",
        "Acidity Regulator",
        "Controls acidity and contributes sour taste"
    ),

    "e407": (
        "Carrageenan",
        "Thickener / Stabilizer",
        "Improves texture and stability"
    ),

    "e410": (
        "Locust Bean Gum",
        "Thickener / Stabilizer",
        "Improves viscosity and texture"
    ),

    "e412": (
        "Guar Gum",
        "Thickener / Stabilizer",
        "Improves viscosity and texture"
    ),

    "e415": (
        "Xanthan Gum",
        "Thickener / Stabilizer",
        "Improves viscosity and stability"
    ),

    "e420": (
        "Sorbitol",
        "Humectant / Sweetener",
        "Provides sweetness and helps retain moisture"
    ),

    "e440": (
        "Pectins",
        "Gelling / Thickening Agent",
        "Helps form gels and improve texture"
    ),

    "e450": (
        "Diphosphates",
        "Raising / Stabilizing Agent",
        "Used for functional and leavening properties"
    ),

    "e621": (
        "Monosodium Glutamate",
        "Flavour Enhancer",
        "Enhances savoury flavour"
    )
}


# ============================================================
# NORMALIZE ADDITIVE CODE
# ============================================================

def normalize_additive_code(text):

    text = normalize_text(text)

    match = re.search(
        r"\b(?:e|ins)\s*[- ]?\s*(\d{3,4})\b",
        text
    )

    if match:

        return "e" + match.group(1)

    return None


# ============================================================
# RULE-BASED INGREDIENT INTELLIGENCE
#
# This is the important part that fixes the
# "9 out of 10 are just ingredients" problem.
# ============================================================

def rule_based_ingredient_intelligence(
    ingredient,
    raw_ingredient=""
):

    text = normalize_text(
        ingredient
    )

    raw = normalize_text(
        raw_ingredient
    )

    combined = (
        text + " " + raw
    ).strip()


    # --------------------------------------------------------
    # E / INS NUMBER
    # --------------------------------------------------------

    additive_code = normalize_additive_code(
        combined
    )

    if additive_code in ADDITIVE_GUIDE:

        name, role, purpose = ADDITIVE_GUIDE[
            additive_code
        ]

        return {

            "role": role,

            "description": (
                f"{name} is a food additive identified "
                f"by the declared code {additive_code.upper()}."
            ),

            "purpose": purpose,

            "confidence": "High",

            "source": (
                "Declared additive code + "
                "ProductLens regulatory reference; "
                "FSSAI regulations should be used for "
                "India-specific regulatory confirmation."
            ),

            "code": additive_code.upper()
        }


    # --------------------------------------------------------
    # PRESERVATIVE
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "preservative",
            "sodium benzoate",
            "potassium sorbate",
            "sorbic acid",
            "benzoate"
        ]
    ):

        return {

            "role": "Preservative",

            "description": (
                "An ingredient or additive used to "
                "slow food spoilage."
            ),

            "purpose": (
                "Helps control microbial deterioration "
                "and extend shelf life."
            ),

            "confidence": "High",

            "source": (
                "Ingredient declaration + "
                "ProductLens functional classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # EMULSIFIER
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "emulsifier",
            "lecithin",
            "mono and diglycerides",
            "mono diglycerides",
            "diglycerides",
            "polysorbate"
        ]
    ):

        return {

            "role": "Emulsifier",

            "description": (
                "An ingredient used to help components "
                "that normally separate remain uniformly mixed."
            ),

            "purpose": (
                "Improves mixture stability, texture "
                "and consistency."
            ),

            "confidence": "High",

            "source": (
                "Ingredient declaration + "
                "functional food-ingredient classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # THICKENER / STABILIZER
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "thickener",
            "stabilizer",
            "stabiliser",
            "xanthan",
            "guar gum",
            "carrageenan",
            "pectin",
            "locust bean gum",
            "cellulose gum",
            "carboxymethyl cellulose",
            "modified starch"
        ]
    ):

        return {

            "role": "Thickener / Stabilizer",

            "description": (
                "A food ingredient used to control "
                "viscosity, texture or physical stability."
            ),

            "purpose": (
                "Improves thickness, texture and/or "
                "physical stability."
            ),

            "confidence": "High",

            "source": (
                "Ingredient declaration + "
                "functional food-ingredient classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # ACIDITY REGULATOR
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "acidity regulator",
            "citric acid",
            "lactic acid",
            "malic acid",
            "tartaric acid",
            "phosphoric acid"
        ]
    ):

        return {

            "role": "Acidity regulator / acidulant",

            "description": (
                "An acidic food ingredient used to "
                "control product acidity and flavour."
            ),

            "purpose": (
                "Controls acidity and can contribute "
                "sour taste."
            ),

            "confidence": "High",

            "source": (
                "Ingredient declaration + "
                "functional food-ingredient classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # ANTIOXIDANT
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "antioxidant",
            "ascorbic acid",
            "tocopherol",
            "vitamin e"
        ]
    ):

        return {

            "role": "Antioxidant",

            "description": (
                "An ingredient that can help reduce "
                "oxidative deterioration of food components."
            ),

            "purpose": (
                "Helps protect susceptible food components "
                "from oxidation."
            ),

            "confidence": "High",

            "source": (
                "Ingredient declaration + "
                "functional food-ingredient classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # RAISING AGENT
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "raising agent",
            "leavening agent",
            "baking powder",
            "baking soda",
            "sodium bicarbonate",
            "ammonium bicarbonate"
        ]
    ):

        return {

            "role": "Raising / leavening agent",

            "description": (
                "An ingredient used to produce gas "
                "and increase the volume or porosity "
                "of a food product."
            ),

            "purpose": (
                "Helps create a lighter or more porous texture."
            ),

            "confidence": "High",

            "source": (
                "Ingredient declaration + "
                "functional food-ingredient classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # HUMECTANT
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "humectant",
            "glycerol",
            "glycerin",
            "sorbitol"
        ]
    ):

        return {

            "role": "Humectant",

            "description": (
                "An ingredient used to influence moisture "
                "retention in a food product."
            ),

            "purpose": (
                "Helps retain moisture and influence texture."
            ),

            "confidence": "High",

            "source": (
                "Ingredient declaration + "
                "functional food-ingredient classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # SWEETENER
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "sweetener",
            "sugar",
            "glucose",
            "fructose",
            "dextrose",
            "sucrose",
            "maltose",
            "honey",
            "syrup",
            "jaggery"
        ]
    ):

        return {

            "role": "Sweetener / carbohydrate ingredient",

            "description": (
                "A carbohydrate or sweetening ingredient "
                "used to provide sweetness."
            ),

            "purpose": (
                "Provides sweetness and may contribute "
                "to carbohydrate content."
            ),

            "confidence": "High",

            "source": (
                "Ingredient declaration + "
                "functional food-ingredient classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # OIL / FAT
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "oil",
            "fat",
            "shortening",
            "butter",
            "ghee"
        ]
    ):

        return {

            "role": "Fat / texture ingredient",

            "description": (
                "A lipid ingredient used as a source "
                "of fat and for formulation properties."
            ),

            "purpose": (
                "Provides fat and can contribute "
                "texture, mouthfeel or cooking properties."
            ),

            "confidence": "High",

            "source": (
                "Ingredient declaration + "
                "functional food-ingredient classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # CEREAL / GRAIN
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "wheat",
            "rice",
            "corn",
            "maize",
            "barley",
            "oat",
            "rye",
            "millet",
            "sorghum",
            "flour",
            "semolina",
            "atta",
            "maida"
        ]
    ):

        return {

            "role": "Cereal / grain-based ingredient",

            "description": (
                "A cereal-derived ingredient primarily "
                "used as a food base or carbohydrate source."
            ),

            "purpose": (
                "Provides carbohydrates, bulk and/or "
                "structural properties."
            ),

            "confidence": "High",

            "source": (
                "Ingredient declaration + "
                "food composition classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # PROTEIN
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "protein",
            "whey",
            "casein",
            "albumin",
            "pea protein",
            "soy protein",
            "milk protein"
        ]
    ):

        return {

            "role": "Protein ingredient",

            "description": (
                "A protein-containing ingredient used "
                "primarily for nutritional and/or functional properties."
            ),

            "purpose": (
                "Contributes protein and may contribute "
                "structure or texture."
            ),

            "confidence": "High",

            "source": (
                "Ingredient declaration + "
                "food composition classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # FLAVOUR
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "flavour",
            "flavor",
            "natural flavour",
            "natural flavor",
            "artificial flavour",
            "artificial flavor"
        ]
    ):

        return {

            "role": "Flavouring",

            "description": (
                "A flavouring ingredient used to "
                "provide or enhance product flavour."
            ),

            "purpose": (
                "Provides or enhances flavour."
            ),

            "confidence": "High",

            "source": (
                "Ingredient declaration + "
                "functional classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # COLOUR
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "colour",
            "color",
            "colouring",
            "coloring",
            "caramel colour",
            "caramel color"
        ]
    ):

        return {

            "role": "Colouring agent",

            "description": (
                "An ingredient used to provide or "
                "restore product colour."
            ),

            "purpose": (
                "Provides or improves product colour."
            ),

            "confidence": "High",

            "source": (
                "Ingredient declaration + "
                "functional classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # SALT / MINERAL
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "salt",
            "sodium chloride",
            "mineral",
            "calcium",
            "potassium",
            "magnesium"
        ]
    ):

        return {

            "role": "Mineral / formulation ingredient",

            "description": (
                "A mineral-containing ingredient "
                "declared on the product label."
            ),

            "purpose": (
                "Contributes minerals and may have "
                "flavour or formulation functions depending "
                "on the specific compound."
            ),

            "confidence": "Medium",

            "source": (
                "Ingredient declaration + "
                "ingredient classification"
            ),

            "code": ""
        }


    # --------------------------------------------------------
    # PLANT / VEGETABLE BASE
    # --------------------------------------------------------

    if any(
        keyword_found(
            x,
            combined
        )
        for x in [
            "potato",
            "tomato",
            "onion",
            "garlic",
            "carrot",
            "pea",
            "chickpea",
            "lentil",
            "bean",
            "vegetable",
            "fruit"
        ]
    ):

        return {

            "role": "Plant-derived food ingredient",

            "description": (
                "A plant-derived food ingredient that "
                "contributes to the product's composition."
            ),

            "purpose": (
                "Provides food solids, nutrients, flavour "
                "and/or texture depending on the ingredient."
            ),

            "confidence": "Medium",

            "source": (
                "Ingredient declaration + "
                "food composition classification"
            ),

            "code": ""
        }


    return None


# ============================================================
# INGREDIENT PARSER
#
# Better than simply splitting on commas.
# Keeps parenthetical percentages and subingredients.
# ============================================================

def get_ingredient_order(ingredients):

    if not ingredients:
        return []

    text = str(
        ingredients
    )

    text = text.replace(
        ";",
        ","
    )

    # Remove "Ingredients:" heading
    text = re.sub(
        r"^\s*ingredients?\s*:\s*",
        "",
        text,
        flags=re.I
    )

    parts = []

    current = ""
    depth = 0

    for char in text:

        if char == "(":
            depth += 1

        elif char == ")":
            depth = max(
                0,
                depth - 1
            )

        if char == "," and depth == 0:

            if current.strip():

                parts.append(
                    current.strip()
                )

            current = ""

        else:

            current += char

    if current.strip():

        parts.append(
            current.strip()
        )

    cleaned = []

    for part in parts:

        part = re.sub(
            r"^\s*\d+[\.\)]\s*",
            "",
            part
        )

        part = part.strip(
            " ."
        )

        if part:

            cleaned.append(
                part
            )

    return cleaned


# ============================================================
# EXTRACT PERCENTAGE
# ============================================================

def extract_percentage(text):

    if not text:
        return None

    match = re.search(
        r"(\d+(?:\.\d+)?)\s*%",
        str(text)
    )

    if not match:
        return None

    return safe_number(
        match.group(1),
        None
    )


# ============================================================
# INGREDIENT DETAILS
# ============================================================

def get_ingredient_details(
    ingredients,
    structured_ingredients=None,
    additive_tags=None
):

    ingredient_list = get_ingredient_order(
        ingredients
    )

    if not ingredient_list:
        return []

    structured_ingredients = (
        structured_ingredients
        or []
    )

    additive_tags = (
        additive_tags
        or []
    )

    details = []

    for index, ingredient in enumerate(
        ingredient_list
    ):

        clean = ingredient.strip()

        lookup = re.sub(
            r"\(\s*\d+(?:\.\d+)?\s*%\s*\)",
            "",
            clean
        )

        lookup = normalize_text(
            lookup
        )

        percentage = extract_percentage(
            clean
        )

        matched_key = None

        # ----------------------------------------------------
        # 1. EXACT DATABASE MATCH
        # ----------------------------------------------------

        normalized_alias = (
            INGREDIENT_ALIASES.get(
                lookup
            )
        )

        if normalized_alias:

            lookup_for_match = normalized_alias

        else:

            lookup_for_match = lookup


        for key in sorted(
            INGREDIENT_GUIDE.keys(),
            key=len,
            reverse=True
        ):

            if (
                lookup_for_match == key
                or keyword_found(
                    key,
                    lookup_for_match
                )
            ):

                matched_key = key

                break


        # ----------------------------------------------------
        # 2. STRUCTURED OFF DATA
        # ----------------------------------------------------

        structured = {}

        if index < len(
            structured_ingredients
        ):

            candidate = (
                structured_ingredients[index]
            )

            if isinstance(
                candidate,
                dict
            ):

                structured = candidate


        structured_id = structured.get(
            "id",
            ""
        )

        structured_text = structured.get(
            "text",
            ""
        )

        structured_percent = structured.get(
            "percent_estimate"
        )

        if structured_percent is not None:

            percentage = safe_number(
                structured_percent,
                percentage
            )


        # ----------------------------------------------------
        # 3. ADDITIVE TAG MATCH
        # ----------------------------------------------------

        additive_code = normalize_additive_code(
            clean
        )

        if not additive_code:

            for tag in additive_tags:

                tag_code = normalize_additive_code(
                    str(tag)
                )

                if (
                    tag_code
                    and
                    keyword_found(
                        tag_code,
                        clean
                    )
                ):

                    additive_code = tag_code

                    break


        # ----------------------------------------------------
        # 4. EXACT KNOWLEDGE BASE
        # ----------------------------------------------------

        if matched_key:

            info = INGREDIENT_GUIDE[
                matched_key
            ]

            details.append({

                "ingredient": clean,

                "role": info["role"],

                "code": (
                    additive_code.upper()
                    if additive_code
                    else ""
                ),

                "description": info[
                    "description"
                ],

                "purpose": info[
                    "purpose"
                ],

                "confidence": info[
                    "confidence"
                ],

                "source": (
                    "Product label + "
                    "ProductLens ingredient "
                    "knowledge base"
                ),

                "percentage": percentage,

                "structured_id": structured_id,

                "structured_name": (
                    structured_text
                    or clean
                ),

                "evidence": [
                    "Exact/alias ingredient match"
                ]
            })

            continue


        # ----------------------------------------------------
        # 5. E-NUMBER / FUNCTIONAL RULE ENGINE
        # ----------------------------------------------------

        rule_info = (
            rule_based_ingredient_intelligence(
                clean,
                structured_text
            )
        )

        if rule_info:

            details.append({

                "ingredient": clean,

                "role": rule_info[
                    "role"
                ],

                "code": rule_info[
                    "code"
                ],

                "description": rule_info[
                    "description"
                ],

                "purpose": rule_info[
                    "purpose"
                ],

                "confidence": rule_info[
                    "confidence"
                ],

                "source": rule_info[
                    "source"
                ],

                "percentage": percentage,

                "structured_id": structured_id,

                "structured_name": (
                    structured_text
                    or clean
                ),

                "evidence": [
                    "Functional keyword/rule match"
                ]
            })

            continue


        # ----------------------------------------------------
        # 6. STRUCTURED DATABASE EVIDENCE
        # ----------------------------------------------------

        if structured_id:

            details.append({

                "ingredient": clean,

                "role": "Identified food ingredient",

                "code": "",

                "description": (
                    "This ingredient is represented "
                    "as a structured ingredient in the "
                    "product database."
                ),

                "purpose": (
                    "Its presence is supported by the "
                    "product's ingredient declaration. "
                    "A specific technological function "
                    "is not assigned without sufficient evidence."
                ),

                "confidence": "Medium",

                "source": (
                    "Product label + "
                    "Open Food Facts structured ingredient data"
                ),

                "percentage": percentage,

                "structured_id": structured_id,

                "structured_name": (
                    structured_text
                    or clean
                ),

                "evidence": [
                    "Structured database ingredient record"
                ]
            })

            continue


        # ----------------------------------------------------
        # 7. FINAL FALLBACK
        # ----------------------------------------------------

        details.append({

            "ingredient": clean,

            "role": "Identified ingredient — function not established",

            "code": (
                additive_code.upper()
                if additive_code
                else ""
            ),

            "description": (
                "The ingredient was found in the "
                "declared product composition, but the "
                "available evidence is not sufficient "
                "for ProductLens to assign a specific "
                "technological function."
            ),

            "purpose": (
                "The package declaration remains the "
                "primary evidence. ProductLens does "
                "not invent a function when the evidence "
                "is insufficient."
            ),

            "confidence": (
                "Label confirmed; function unclassified"
            ),

            "source": (
                "Product label / database"
            ),

            "percentage": percentage,

            "structured_id": structured_id,

            "structured_name": clean,

            "evidence": [
                "Ingredient declaration found"
            ]
        })

    return details


# ============================================================
# INGREDIENT CATEGORIES
# ============================================================

def get_ingredient_categories(
    ingredients
):

    if not ingredients:
        return []

    text = normalize_text(
        ingredients
    )

    categories_data = {

        "🌾": (
            "Cereals / Grains",
            [
                "wheat",
                "flour",
                "rice",
                "maida",
                "atta",
                "corn",
                "maize",
                "barley",
                "semolina",
                "suji",
                "sooji",
                "rava",
                "oat",
                "millet"
            ]
        ),

        "🍬": (
            "Sugars / Sweeteners",
            [
                "sugar",
                "glucose",
                "fructose",
                "syrup",
                "maltose",
                "dextrose",
                "honey",
                "sweetener",
                "jaggery"
            ]
        ),

        "🛢️": (
            "Oils / Fats",
            [
                "oil",
                "fat",
                "butter",
                "palm",
                "sunflower",
                "vegetable oil",
                "coconut oil",
                "ghee"
            ]
        ),

        "🧂": (
            "Salt / Minerals",
            [
                "salt",
                "sodium",
                "potassium",
                "calcium",
                "magnesium"
            ]
        ),

        "🌿": (
            "Spices / Herbs",
            [
                "spice",
                "spices",
                "pepper",
                "chilli",
                "chili",
                "turmeric",
                "cumin",
                "coriander",
                "ginger",
                "garlic",
                "cardamom",
                "cinnamon"
            ]
        ),

        "🧪": (
            "Food Additives",
            [
                "preservative",
                "emulsifier",
                "stabilizer",
                "stabiliser",
                "colour",
                "color",
                "flavour",
                "flavor",
                "acidity regulator",
                "thickener",
                "raising agent",
                "antioxidant",
                "humectant",
                "e100",
                "e200",
                "e300",
                "e400",
                "e500",
                "e600"
            ]
        ),

        "🥛": (
            "Dairy",
            [
                "milk",
                "whey",
                "casein",
                "butter",
                "cream",
                "cheese",
                "lactose"
            ]
        ),

        "🥜": (
            "Nuts / Legumes",
            [
                "almond",
                "cashew",
                "walnut",
                "pistachio",
                "peanut",
                "groundnut",
                "soy",
                "soya",
                "chickpea",
                "lentil"
            ]
        )
    }

    categories = []

    for icon, data in categories_data.items():

        title, keywords = data

        found = []

        for keyword in keywords:

            if keyword_found(
                keyword,
                text
            ):

                found.append(
                    keyword
                )

        if found:

            categories.append({

                "icon": icon,

                "title": title,

                "ingredients": list(
                    dict.fromkeys(found)
                )
            })

    return categories


# ============================================================
# REGULATORY INSIGHTS
# ============================================================

def get_regulatory_insights(
    ingredients,
    additive_tags=None
):

    if not ingredients:
        return []

    additive_tags = (
        additive_tags
        or []
    )

    combined = (
        str(ingredients)
        + " "
        + " ".join(
            str(x)
            for x in additive_tags
        )
    )

    results = []

    seen = set()

    # Search both ingredient text and database tags.
    for code, data in ADDITIVE_GUIDE.items():

        if keyword_found(
            code,
            combined
        ):

            if code in seen:
                continue

            seen.add(code)

            name, role, purpose = data

            results.append({

                "code": code.upper(),

                "name": name,

                "role": role,

                "purpose": purpose,

                "source": (
                    "Product declaration + "
                    "ProductLens additive reference"
                ),

                "regulatory_authority": "FSSAI",

                "regulatory_note": (
                    "For an India-specific regulatory "
                    "determination, refer to current "
                    "FSSAI food additive regulations."
                )
            })

    return results


# ============================================================
# FSSAI LICENSE EXTRACTION
# ============================================================

def extract_fssai_license(
    *texts
):

    combined = " ".join(
        str(x)
        for x in texts
        if x
    )

    # Common FSSAI licence/registration numbers are
    # 14-digit numeric identifiers.
    matches = re.findall(
        r"\b\d{14}\b",
        combined
    )

    for value in matches:

        return value

    return ""


# ============================================================
# FSSAI REGULATORY INFORMATION
# ============================================================

def build_fssai_info(
    product
):

    license_number = extract_fssai_license(
        product.get(
            "fssai_license",
            ""
        ),

        product.get(
            "labels",
            ""
        ),

        product.get(
            "categories",
            ""
        )
    )

    return {

        "authority": "FSSAI",

        "primary": True,

        "license_number": license_number,

        "verification_url": FSSAI_VERIFY_URL,

        "regulatory_source": (
            FSSAI_REGULATORY_SOURCE
        ),

        "status": (
            "License number detected — "
            "verify through official FSSAI/FoSCoS"
            if license_number
            else
            "No FSSAI licence number was available "
            "in the retrieved product data."
        )
    }


# ============================================================
# SMART HIGHLIGHTS
# ============================================================

def make_smart_highlights(
    product
):

    highlights = []

    sugar = safe_number(
        product.get("sugar")
    )

    fat = safe_number(
        product.get("fat")
    )

    protein = safe_number(
        product.get("protein")
    )

    salt = safe_number(
        product.get("salt")
    )

    allergens = product.get(
        "detected_allergens",
        []
    )

    ingredient_details = product.get(
        "ingredient_details",
        []
    )

    additives = product.get(
        "regulatory_insights",
        []
    )


    if sugar > 15:

        highlights.append({

            "icon": "🍬",

            "title": "High Sugar",

            "text": (
                "Sugar is relatively high per 100 g."
            )
        })

    elif 0 < sugar <= 5:

        highlights.append({

            "icon": "✅",

            "title": "Lower Sugar",

            "text": (
                "Sugar is relatively low per 100 g."
            )
        })


    if fat > 17.5:

        highlights.append({

            "icon": "🛢️",

            "title": "Higher Fat",

            "text": (
                "Total fat is relatively high per 100 g."
            )
        })


    if protein >= 10:

        highlights.append({

            "icon": "💪",

            "title": "Higher Protein",

            "text": (
                "Protein is relatively high per 100 g."
            )
        })


    if salt > 1.5:

        highlights.append({

            "icon": "🧂",

            "title": "High Salt",

            "text": (
                "Salt is relatively high per 100 g."
            )
        })


    if allergens:

        names = ", ".join(
            item["name"]
            for item in allergens
        )

        highlights.append({

            "icon": "🚨",

            "title": "Allergens Detected",

            "text": names
        })


    if additives:

        highlights.append({

            "icon": "🧪",

            "title": "Food Additives Identified",

            "text": (
                f"{len(additives)} "
                "declared additive type(s) identified."
            )
        })


    if ingredient_details:

        total = len(
            ingredient_details
        )

        classified = len([
            x
            for x in ingredient_details
            if (
                "unclassified"
                not in str(
                    x.get(
                        "confidence",
                        ""
                    )
                ).lower()
            )
        ])

        if total:

            percentage = round(
                (
                    classified / total
                ) * 100
            )

            highlights.append({

                "icon": "🔬",

                "title": "Ingredient Intelligence",

                "text": (
                    f"{classified} of {total} "
                    f"ingredients received an evidence-based "
                    f"classification ({percentage}%)."
                )
            })


    if not highlights:

        highlights.append({

            "icon": "🔬",

            "title": "Product Analysis",

            "text": (
                "Review nutrition, ingredients, "
                "allergens and regulatory information."
            )
        })

    return highlights


# ============================================================
# HEALTH CAUTIONS
# ============================================================

def disease_cautions(
    product
):

    cautions = []

    sugar = safe_number(
        product.get("sugar")
    )

    salt = safe_number(
        product.get("salt")
    )

    fat = safe_number(
        product.get("fat")
    )

    allergens = product.get(
        "detected_allergens",
        []
    )


    if sugar > 15:

        cautions.append({

            "icon": "🩸",

            "title": "High Sugar Caution",

            "text": (
                "This product contains a relatively "
                "high amount of sugar per 100 g. "
                "People managing blood glucose may "
                "need to consider portion size and "
                "their overall dietary pattern."
            ),

            "class": "danger"
        })


    if salt > 1.5:

        cautions.append({

            "icon": "❤️",

            "title": "High Salt Caution",

            "text": (
                "This product contains a relatively "
                "high amount of salt per 100 g. "
                "People monitoring sodium or salt "
                "intake may need to consider portion size."
            ),

            "class": "danger"
        })


    if fat > 17.5:

        cautions.append({

            "icon": "❤️",

            "title": "Higher Fat Caution",

            "text": (
                "This product is relatively high in "
                "total fat per 100 g. The type of fat "
                "and overall dietary pattern also matter."
            ),

            "class": "caution"
        })


    if allergens:

        names = ", ".join(
            item["name"]
            for item in allergens
        )

        cautions.insert(
            0,
            {

                "icon": "🚨",

                "title": "ALLERGEN ALERT",

                "text": (
                    "Potential allergens detected: "
                    + names
                    + ". Always check the actual "
                    "package allergen declaration."
                ),

                "class": "danger"
            }
        )


    return cautions


# ============================================================
# FINALIZE PRODUCT
# ============================================================

def finalize_product(
    product
):

    for nutrient in [

        "energy",
        "sugar",
        "fat",
        "protein",
        "salt",
        "saturated_fat",
        "sodium"
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


    ingredients = (
        product.get(
            "ingredients",
            ""
        )
        or ""
    )

    declared_allergens = (
        product.get(
            "allergens",
            ""
        )
        or ""
    )

    allergen_tags = (
        product.get(
            "allergen_tags",
            ""
        )
        or ""
    )


    # --------------------------------------------------------
    # ALLERGENS
    # --------------------------------------------------------

    product[
        "detected_allergens"
    ] = detect_allergens(

        ingredients,

        declared_allergens,

        allergen_tags
    )


    # --------------------------------------------------------
    # INGREDIENTS
    # --------------------------------------------------------

    product[
        "ingredient_order"
    ] = get_ingredient_order(
        ingredients
    )


    product[
        "ingredient_categories"
    ] = get_ingredient_categories(
        ingredients
    )


    product[
        "ingredient_details"
    ] = get_ingredient_details(

        ingredients,

        product.get(
            "structured_ingredients",
            []
        ),

        product.get(
            "additives_tags",
            []
        )
    )


    # Backwards compatibility
    product[
        "decoded_ingredients"
    ] = product[
        "ingredient_details"
    ]


    # --------------------------------------------------------
    # ADDITIVES
    # --------------------------------------------------------

    product[
        "regulatory_insights"
    ] = get_regulatory_insights(

        ingredients,

        product.get(
            "additives_tags",
            []
        )
    )


    # --------------------------------------------------------
    # FSSAI
    # --------------------------------------------------------

    product[
        "fssai"
    ] = build_fssai_info(
        product
    )


    # --------------------------------------------------------
    # HIGHLIGHTS
    # --------------------------------------------------------

    product[
        "smart_highlights"
    ] = make_smart_highlights(
        product
    )


    # --------------------------------------------------------
    # CAUTIONS
    # --------------------------------------------------------

    product[
        "disease_cautions"
    ] = disease_cautions(
        product
    )


    # --------------------------------------------------------
    # NUTRITION BARS
    # --------------------------------------------------------

    product[
        "energy_bar"
    ] = progress_bar(
        product["energy"],
        "energy"
    )

    product[
        "sugar_bar"
    ] = progress_bar(
        product["sugar"],
        "sugar"
    )

    product[
        "fat_bar"
    ] = progress_bar(
        product["fat"],
        "fat"
    )

    product[
        "protein_bar"
    ] = progress_bar(
        product["protein"],
        "protein"
    )

    product[
        "salt_bar"
    ] = progress_bar(
        product["salt"],
        "salt"
    )


    # --------------------------------------------------------
    # ANALYSIS QUALITY
    # --------------------------------------------------------

    total = len(
        product[
            "ingredient_details"
        ]
    )

    classified = len([

        x

        for x in product[
            "ingredient_details"
        ]

        if (
            "unclassified"
            not in str(
                x.get(
                    "confidence",
                    ""
                )
            ).lower()
        )
    ])


    if total:

        product[
            "ingredient_coverage"
        ] = round(
            (
                classified / total
            ) * 100
        )

    else:

        product[
            "ingredient_coverage"
        ] = 0


    product[
        "analysis_engine"
    ] = {

        "version": APP_VERSION,

        "primary_regulatory_authority": "FSSAI",

        "product_database": "Open Food Facts",

        "nutrition_fallback": (
            "USDA FoodData Central"
        ),

        "ingredient_engine": (
            "ProductLens multi-layer "
            "ingredient intelligence"
        )
    }


    return product


# ============================================================
# OPEN FOOD FACTS
# ============================================================

def get_from_open_food_facts(
    barcode
):

    cache_key = (
        "off:"
        + str(barcode)
    )

    cached = cache_get(
        cache_key
    )

    if cached is not None:

        return cached


    print(
        "\n"
        + "=" * 65
    )

    print(
        "DATABASE: OPEN FOOD FACTS"
    )

    print(
        "Barcode:",
        barcode
    )


    try:

        url = OFF_API.format(
            barcode
        )

        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT
        )

        print(
            "OFF STATUS:",
            response.status_code
        )

        response.raise_for_status()

        data = response.json()

    except requests.exceptions.RequestException as error:

        print(
            "Open Food Facts error:",
            error
        )

        return None

    except ValueError:

        print(
            "Invalid Open Food Facts JSON."
        )

        return None


    if data.get(
        "status"
    ) != 1:

        print(
            "Product not found in Open Food Facts."
        )

        return None


    raw = (
        data.get(
            "product",
            {}
        )
        or {}
    )


    ingredients = (
        raw.get(
            "ingredients_text",
            ""
        )
        or ""
    )


    declared_allergens = (
        raw.get(
            "allergens",
            ""
        )
        or ""
    )


    allergen_tags = (
        raw.get(
            "allergens_tags",
            []
        )
        or []
    )


    additives_tags = (
        raw.get(
            "additives_tags",
            []
        )
        or []
    )


    allergen_tags_text = " ".join(

        str(item)

        for item in allergen_tags
    )


    nutrition = (
        raw.get(
            "nutriments",
            {}
        )
        or {}
    )


    energy = nutrition.get(
        "energy-kcal_100g",
        nutrition.get(
            "energy-kcal",
            0
        )
    )


    # --------------------------------------------------------
    # PRODUCT
    # --------------------------------------------------------

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

        "additives_tags": additives_tags,

        "structured_ingredients": (
            raw.get(
                "ingredients",
                []
            )
            or []
        ),

        "categories": raw.get(
            "categories",
            ""
        ),

        "labels": raw.get(
            "labels",
            ""
        ),

        "countries": raw.get(
            "countries",
            ""
        ),

        "quantity": raw.get(
            "quantity",
            ""
        ),

        "packaging": raw.get(
            "packaging",
            ""
        ),

        "fssai_license": raw.get(
            "fssai_license_number",
            raw.get(
                "fssai_license",
                ""
            )
        ),

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

        "saturated_fat": nutrition.get(
            "saturated-fat_100g",
            0
        ),

        "sodium": nutrition.get(
            "sodium_100g",
            0
        ),

        "source": (
            "Open Food Facts"
        ),

        "verified": True,

        "data_quality": raw.get(
            "data_quality_tags",
            []
        ),

        "nova_group": raw.get(
            "nova_group",
            ""
        ),

        "nutriscore_grade": raw.get(
            "nutriscore_grade",
            ""
        )
    }


    product = finalize_product(
        product
    )


    cache_set(
        cache_key,
        product
    )


    print(
        "Product found:",
        product["name"]
    )

    print(
        "Ingredients:",
        len(
            product[
                "ingredient_details"
            ]
        )
    )

    print(
        "Ingredient coverage:",
        product[
            "ingredient_coverage"
        ],
        "%"
    )


    return product


# ============================================================
# USDA FOODDATA CENTRAL
# ============================================================

def get_from_usda(
    barcode
):

    if not USDA_API_KEY:

        print(
            "USDA skipped: no API key configured."
        )

        return None


    cache_key = (
        "usda:"
        + str(barcode)
    )

    cached = cache_get(
        cache_key
    )

    if cached is not None:

        return cached


    print(
        "\n"
        + "=" * 65
    )

    print(
        "DATABASE: USDA FOODDATA CENTRAL"
    )

    print(
        "Barcode:",
        barcode
    )


    try:

        params = {

            "api_key": USDA_API_KEY,

            "query": barcode,

            "pageSize": 10
        }


        response = session.get(

            USDA_API,

            params=params,

            timeout=REQUEST_TIMEOUT
        )


        print(
            "USDA STATUS:",
            response.status_code
        )


        response.raise_for_status()

        data = response.json()


    except requests.exceptions.RequestException as error:

        print(
            "USDA error:",
            error
        )

        return None


    except ValueError:

        print(
            "Invalid USDA response."
        )

        return None


    foods = (
        data.get(
            "foods",
            []
        )
        or []
    )


    if not foods:

        return None


    food = foods[0]


    nutrients = (
        food.get(
            "foodNutrients",
            []
        )
        or []
    )


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


        if (
            "energy"
            in name
            and
            "kcal"
            in name
        ):

            energy = value


        elif (
            "sugars, total"
            in name
        ):

            sugar = value


        elif (
            name
            ==
            "total lipid (fat)"
        ):

            fat = value


        elif (
            name
            ==
            "protein"
        ):

            protein = value


        elif (
            name
            ==
            "sodium"
        ):

            sodium = value


    # Sodium mg -> approximate salt g
    salt = (
        sodium
        * 2.5
        / 1000
    )


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
        )
        or "",

        "allergens": "",

        "allergen_tags": "",

        "additives_tags": [],

        "structured_ingredients": [],

        "categories": "",

        "labels": "",

        "countries": "",

        "quantity": "",

        "packaging": "",

        "fssai_license": "",

        "energy": energy,

        "sugar": sugar,

        "fat": fat,

        "protein": protein,

        "salt": salt,

        "saturated_fat": 0,

        "sodium": sodium,

        "source": (
            "USDA FoodData Central"
        ),

        "verified": True
    }


    product = finalize_product(
        product
    )


    cache_set(
        cache_key,
        product
    )


    return product


# ============================================================
# SEARCH PRODUCT
# ============================================================

def search_product(
    barcode
):

    barcode = str(
        barcode
    ).strip()


    if not barcode.isdigit():

        return None


    # --------------------------------------------------------
    # 1. OPEN FOOD FACTS
    # --------------------------------------------------------

    product = get_from_open_food_facts(
        barcode
    )


    if product:

        return product


    print(
        "Open Food Facts failed."
    )


    # --------------------------------------------------------
    # 2. USDA
    # --------------------------------------------------------

    product = get_from_usda(
        barcode
    )


    if product:

        return product


    return None


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# ============================================================
# BARCODE SEARCH
# ============================================================

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

            error=(
                "Please enter or scan a barcode."
            ),

            auto_scroll=True
        )


    if not barcode.isdigit():

        return render_template(

            "index.html",

            error=(
                "Barcode should contain "
                "numbers only."
            ),

            auto_scroll=True
        )


    product = search_product(
        barcode
    )


    if product:

        return render_template(

            "index.html",

            product=product,

            auto_scroll=True,

            analysis_complete=True
        )


    return render_template(

        "index.html",

        show_manual_form=True,

        missing_barcode=barcode,

        error=(

            "Product was not found in "
            "the available product databases. "
            "You can enter the product information "
            "manually below."
        ),

        auto_scroll=True,

        analysis_complete=False
    )


# ============================================================
# JSON SEARCH API
# ============================================================

@app.route(
    "/api/search/<barcode>",
    methods=["GET"]
)
def api_search(
    barcode
):

    barcode = str(
        barcode
    ).strip()


    if not barcode.isdigit():

        return jsonify({

            "success": False,

            "error": (
                "Barcode should contain "
                "numbers only."
            )

        }), 400


    product = search_product(
        barcode
    )


    if not product:

        return jsonify({

            "success": False,

            "error": (
                "Product was not found."
            )

        }), 404


    return jsonify({

        "success": True,

        "product": product

    })


# ============================================================
# MANUAL ENTRY
# ============================================================

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

            error=(
                "Product name is required."
            ),

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

        "additives_tags": [],

        "structured_ingredients": [],

        "categories": "",

        "labels": "",

        "countries": "",

        "quantity": "",

        "packaging": "",

        "fssai_license": "",

        "energy": energy,

        "sugar": sugar,

        "fat": fat,

        "protein": protein,

        "salt": salt,

        "saturated_fat": 0,

        "sodium": 0,

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
            barcode
            and
            barcode.isdigit()
        ),

        auto_scroll=True,

        analysis_complete=True
    )


# ============================================================
# COMPARE
# ============================================================

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

            compare_error=(
                "Please enter both barcodes."
            )
        )


    if (
        not barcode1.isdigit()
        or
        not barcode2.isdigit()
    ):

        return render_template(

            "index.html",

            compare_error=(
                "Both barcodes should contain "
                "numbers only."
            )
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

            compare_error=(
                "One or both products "
                "could not be found."
            ),

            auto_scroll=True
        )


    rows = []


    nutrients = [

        (
            "Energy",
            "energy",
            "kcal"
        ),

        (
            "Sugar",
            "sugar",
            "g"
        ),

        (
            "Fat",
            "fat",
            "g"
        ),

        (
            "Protein",
            "protein",
            "g"
        ),

        (
            "Salt",
            "salt",
            "g"
        )
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

                result = (
                    "Product 1 has more protein"
                )

            elif value2 > value1:

                result = (
                    "Product 2 has more protein"
                )

            else:

                result = "Same"

        else:

            if value1 < value2:

                result = (
                    "Product 1 is lower"
                )

            elif value2 < value1:

                result = (
                    "Product 2 is lower"
                )

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


    if (
        product1["sugar"]
        <
        product2["sugar"]
    ):

        insights.append(
            product1["name"]
            +
            " has less sugar."
        )

    elif (
        product2["sugar"]
        <
        product1["sugar"]
    ):

        insights.append(
            product2["name"]
            +
            " has less sugar."
        )


    if (
        product1["protein"]
        >
        product2["protein"]
    ):

        insights.append(
            product1["name"]
            +
            " has more protein."
        )

    elif (
        product2["protein"]
        >
        product1["protein"]
    ):

        insights.append(
            product2["name"]
            +
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

        auto_scroll=True,

        analysis_complete=True
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "status": "ok",

        "application": APP_NAME,

        "version": APP_VERSION,

        "regulatory_authority": "FSSAI",

        "product_database": (
            "Open Food Facts"
        ),

        "nutrition_fallback": (
            "USDA FoodData Central"
        )
    })


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return jsonify({

        "success": False,

        "error": "Page not found."
    }), 404


@app.errorhandler(500)
def server_error(error):

    print(
        "SERVER ERROR:",
        error
    )

    return jsonify({

        "success": False,

        "error": (
            "ProductLens encountered an "
            "internal error."
        )
    }), 500


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    print()

    print(
        "=" * 65
    )

    print(
        "PRODUCTLENS"
    )

    print(
        "Food Ingredient & Nutrition Intelligence"
    )

    print(
        "Version:",
        APP_VERSION
    )

    print(
        "=" * 65
    )

    print()

    print(
        "Intelligence architecture:"
    )

    print(
        "1. FSSAI → Indian regulatory authority"
    )

    print(
        "2. Open Food Facts → barcode/product/label data"
    )

    print(
        "3. ProductLens → ingredient intelligence engine"
    )

    print(
        "4. USDA → nutrition fallback when configured"
    )

    print()

    print(
        "Starting Flask server..."
    )

    print(
        "Open on this PC:"
    )

    print(
        "http://127.0.0.1:5000"
    )

    print()

    print(
        "For phone on same Wi-Fi:"
    )

    print(
        "http://YOUR-PC-IP:5000"
    )

    print()

    app.run(

        host="0.0.0.0",

        port=5000,

        debug=True
    )
