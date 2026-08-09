from flask import Flask, render_template, request, jsonify
import requests
import re
import os
import json
import sqlite3
from datetime import datetime

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None


app = Flask(__name__)


# =========================================================
# PRODUCTLENS - API SETTINGS
# =========================================================

OFF_API = "https://world.openfoodfacts.org/api/v2/product/{}.json"
USDA_API = "https://api.nal.usda.gov/fdc/v1/foods/search"
USDA_API_KEY = "DEMO_KEY"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

SQLITE_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "productlens.db"
)

FSSAI_REFERENCE_URL = (
    "https://www.fssai.gov.in/cms/Compendium-FSS-FPS-FA.php"
)


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
        "skim milk", "milk protein", "milk fat",
        "milk solids non fat", "whey", "whey powder",
        "whey protein", "casein", "caseinate",
        "sodium caseinate", "calcium caseinate", "lactose",
        "butter", "cream", "dairy", "cheese", "curd",
        "ghee", "milk derivative"
    ],

    "Tree Nuts": [
        "nut", "nuts", "tree nut", "tree nuts",
        "almond", "almonds", "cashew", "cashews",
        "walnut", "walnuts", "pistachio", "pistachios",
        "hazelnut", "hazelnuts", "pecan", "pecans",
        "macadamia", "macadamia nuts"
    ],

    "Peanuts": [
        "peanut", "peanuts", "groundnut", "groundnuts",
        "ground nut", "peanut oil", "peanut flour"
    ],

    "Soy": [
        "soy", "soya", "soybean", "soybeans",
        "soy protein", "soy lecithin",
        "soya lecithin", "soy flour"
    ],

    "Sesame": [
        "sesame", "sesame seeds", "sesame seed", "til"
    ],

    "Mustard": [
        "mustard", "mustard seeds", "mustard seed"
    ],

    "Egg": [
        "egg", "eggs", "egg powder",
        "egg white", "egg yolk", "albumin"
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
# REGULATORY / INGREDIENT KNOWLEDGE
# =========================================================

FSSAI_INGREDIENT_GUIDE = {

    "e100": (
        "Curcumin / Turmeric Colour",
        "Food colour",
        "Used to provide yellow colour."
    ),

    "e102": (
        "Tartrazine",
        "Food colour",
        "A synthetic food colour used to provide yellow colour."
    ),

    "e110": (
        "Sunset Yellow FCF",
        "Food colour",
        "A food colour used to provide yellow-orange colour."
    ),

    "e122": (
        "Carmoisine",
        "Food colour",
        "A food colour used to provide red colour."
    ),

    "e124": (
        "Ponceau 4R",
        "Food colour",
        "A food colour used to provide red colour."
    ),

    "e129": (
        "Allura Red AC",
        "Food colour",
        "A food colour used to provide red colour."
    ),

    "e133": (
        "Brilliant Blue FCF",
        "Food colour",
        "A food colour used to provide blue colour."
    ),

    "e150": (
        "Caramel Colours",
        "Food colour",
        "Used to provide brown colour to foods and beverages."
    ),

    "e160a": (
        "Carotenes / Beta-carotene",
        "Food colour",
        "Used to provide yellow-orange colour."
    ),

    "e200": (
        "Sorbic Acid",
        "Preservative",
        "Used to help control spoilage microorganisms."
    ),

    "e202": (
        "Potassium Sorbate",
        "Preservative",
        "Used to help control mould and yeast growth."
    ),

    "e211": (
        "Sodium Benzoate",
        "Preservative",
        "Used to help control microbial spoilage in suitable foods."
    ),

    "e220": (
        "Sulphur Dioxide",
        "Preservative / Antioxidant",
        "Used for preservation and to help limit oxidation in permitted foods."
    ),

    "e223": (
        "Sodium Metabisulphite",
        "Preservative / Antioxidant",
        "Used for preservation or antioxidant purposes in permitted applications."
    ),

    "e250": (
        "Sodium Nitrite",
        "Preservative",
        "Used in permitted food applications, particularly for preservation of certain processed foods."
    ),

    "e260": (
        "Acetic Acid",
        "Acidity Regulator",
        "Used to control acidity and contribute to sour taste."
    ),

    "e270": (
        "Lactic Acid",
        "Acidity Regulator",
        "Used to regulate acidity and contribute to flavour."
    ),

    "e300": (
        "Ascorbic Acid / Vitamin C",
        "Antioxidant",
        "Used as an antioxidant and for functional food-processing purposes."
    ),

    "e306": (
        "Tocopherol-rich Extract",
        "Antioxidant",
        "Used to help slow oxidation of fats and oils."
    ),

    "e322": (
        "Lecithins",
        "Emulsifier",
        "Help ingredients such as oil and water remain evenly mixed."
    ),

    "e330": (
        "Citric Acid",
        "Acidity Regulator",
        "Used to control acidity and provide sour taste."
    ),

    "e331": (
        "Sodium Citrates",
        "Acidity Regulator",
        "Used to regulate acidity and buffering properties."
    ),

    "e407": (
        "Carrageenan",
        "Thickener / Stabilizer",
        "Used to thicken, stabilize or improve texture."
    ),

    "e410": (
        "Locust Bean Gum",
        "Thickener / Stabilizer",
        "Used to improve viscosity and texture."
    ),

    "e412": (
        "Guar Gum",
        "Thickener / Stabilizer",
        "Used to thicken and stabilize food formulations."
    ),

    "e415": (
        "Xanthan Gum",
        "Thickener / Stabilizer",
        "Used to improve viscosity, consistency and stability."
    ),

    "e440": (
        "Pectins",
        "Gelling / Thickening Agent",
        "Used to form gels and improve texture."
    ),

    "e450": (
        "Phosphates",
        "Leavening / Stabilizer",
        "Used for functional purposes such as buffering, leavening or stabilization depending on the specific phosphate."
    ),

    "e471": (
        "Mono- and Diglycerides of Fatty Acids",
        "Emulsifier",
        "Used to help maintain a uniform mixture and improve texture."
    ),

    "e472": (
        "Esters of Mono- and Diglycerides",
        "Emulsifier",
        "Used for emulsification and texture control."
    ),

    "e481": (
        "Sodium Stearoyl Lactylate",
        "Emulsifier / Dough Conditioner",
        "Used for emulsification and functional dough properties."
    ),

    "e500": (
        "Sodium Carbonates",
        "Leavening / Acidity Regulator",
        "Used in food processing for leavening or acidity control depending on the formulation."
    ),

    "e503": (
        "Ammonium Carbonates",
        "Leavening Agent",
        "Used as a leavening agent in suitable baked foods."
    ),

    "e621": (
        "Monosodium Glutamate (MSG)",
        "Flavour Enhancer",
        "Used to enhance savoury or umami flavour."
    ),

    "e627": (
        "Disodium Guanylate",
        "Flavour Enhancer",
        "Used to enhance savoury flavour, often with other flavour enhancers."
    ),

    "e631": (
        "Disodium Inosinate",
        "Flavour Enhancer",
        "Used to enhance savoury flavour, often with other flavour enhancers."
    )
}


def normalize_ingredient_code(text):
    value = str(text or "").lower().strip()
    value = value.replace(" ", "").replace("-", "")
    return value


def get_regulatory_insights(ingredients):

    if not ingredients:
        return []

    text = str(ingredients).lower()
    found = []

    for code, (name, role, purpose) in FSSAI_INGREDIENT_GUIDE.items():

        number = code[1:] if code.startswith("e") else code

        patterns = [
            r"(?<![a-z0-9])"
            + re.escape(code)
            + r"(?![a-z0-9])",

            r"(?<![a-z0-9])ins\s*[- ]?"
            + re.escape(number)
            + r"(?![a-z0-9])"
        ]

        if any(re.search(pattern, text) for pattern in patterns):

            found.append({
                "code": "INS " + number,
                "name": name,
                "role": role,
                "purpose": purpose,
                "source": "FSSAI food-additive reference"
            })

    return found


# =========================================================
# PRODUCT DATABASE
# =========================================================

def db_connection():

    if DATABASE_URL and psycopg2:
        return psycopg2.connect(
            DATABASE_URL,
            sslmode="require"
        )

    return sqlite3.connect(SQLITE_DB)


def init_database():

    try:

        conn = db_connection()
        cur = conn.cursor()

        if DATABASE_URL and psycopg2:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    barcode TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

        else:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    barcode TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

        conn.commit()
        cur.close()
        conn.close()

    except Exception as exc:

        print(
            "Product database initialization warning:",
            exc
        )


def get_saved_product(barcode):

    try:

        conn = db_connection()
        cur = conn.cursor()

        if DATABASE_URL and psycopg2:

            cur.execute(
                "SELECT payload FROM products WHERE barcode = %s",
                (barcode,)
            )

        else:

            cur.execute(
                "SELECT payload FROM products WHERE barcode = ?",
                (barcode,)
            )

        row = cur.fetchone()

        cur.close()
        conn.close()

        if not row:
            return None

        product = json.loads(row[0])

        return finalize_product(product)

    except Exception as exc:

        print(
            "Product database read warning:",
            exc
        )

        return None


def save_product(product):

    barcode = str(
        product.get("barcode", "")
    ).strip()

    if not barcode:
        return

    try:

        payload = json.dumps(
            product,
            ensure_ascii=False
        )

        now = datetime.utcnow().isoformat()

        conn = db_connection()
        cur = conn.cursor()

        if DATABASE_URL and psycopg2:

            cur.execute(
                """
                INSERT INTO products
                (barcode, payload, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)

                ON CONFLICT (barcode)
                DO UPDATE SET
                    payload = EXCLUDED.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (barcode, payload)
            )

        else:

            cur.execute(
                """
                INSERT OR REPLACE INTO products
                (barcode, payload, updated_at)
                VALUES (?, ?, ?)
                """,
                (barcode, payload, now)
            )

        conn.commit()

        cur.close()
        conn.close()

    except Exception as exc:

        print(
            "Product database save warning:",
            exc
        )


init_database()


# =========================================================
# SAFE NUMBER
# =========================================================

def safe_number(value, default=0):

    try:

        if value is None:
            return default

        if isinstance(value, str):

            value = value.replace(
                ",",
                ""
            ).strip()

            if value == "":
                return default

        return float(value)

    except (ValueError, TypeError):

        return default


# =========================================================
# TEXT MATCHING
# =========================================================

def keyword_found(keyword, text):
    """
    Safer ingredient matching.
    Prevents 'egg' from matching words such as 'eggplant'.
    """

    keyword = str(
        keyword
    ).lower().strip()

    text = str(text).lower()

    keyword = keyword.replace(
        "en:",
        ""
    )

    keyword = keyword.replace(
        "-",
        " "
    )

    keyword = keyword.replace(
        "_",
        " "
    )

    parts = keyword.split()

    if not parts:
        return False

    pattern = (
        r"(?<![a-z])"
        + r"\s+".join(
            re.escape(part)
            for part in parts
        )
        + r"(?![a-z])"
    )

    return re.search(
        pattern,
        text
    ) is not None


# =========================================================
# ALLERGEN DETECTION
# =========================================================

def detect_allergens(*texts):

    combined_text = " ".join(
        str(text)
        for text in texts
        if text
    ).lower()

    if not combined_text:
        return []

    combined_text = combined_text.replace(
        "en:",
        " "
    )

    combined_text = combined_text.replace(
        "-",
        " "
    )

    combined_text = combined_text.replace(
        "_",
        " "
    )

    combined_text = combined_text.replace(
        ";",
        " "
    )

    combined_text = combined_text.replace(
        ",",
        " "
    )

    detected = []

    for allergen, keywords in ALLERGEN_GUIDE.items():

        found_keyword = None

        for keyword in sorted(
            keywords,
            key=len,
            reverse=True
        ):

            if keyword_found(
                keyword,
                combined_text
            ):

                found_keyword = keyword
                break

        if found_keyword:

            detected.append({
                "name": allergen,
                "icon": ALLERGEN_ICONS.get(
                    allergen,
                    "⚠️"
                ),
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
            return {
                "level": "Low",
                "class": "low"
            }

        elif value <= 15:
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

        elif value <= 17.5:
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

        elif value <= 1.5:
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

        elif value >= 5:
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


# =========================================================
# INGREDIENT ORDER
# =========================================================

def get_ingredient_order(ingredients):

    if not ingredients:
        return []

    text = str(
        ingredients
    ).replace(
        ";",
        ","
    )

    parts = text.split(",")

    return [
        part.strip()
        for part in parts
        if part.strip()
    ]


# =========================================================
# INGREDIENT CATEGORIES
# =========================================================

def get_ingredient_categories(ingredients):

    if not ingredients:
        return []

    text = str(
        ingredients
    ).lower()

    categories_data = {

        "🌾 Cereals / Grains": [
            "wheat",
            "flour",
            "rice",
            "maida",
            "atta",
            "corn",
            "barley",
            "semolina",
            "suji",
            "sooji",
            "rava",
            "oat"
        ],

        "🍬 Sugars / Sweeteners": [
            "sugar",
            "glucose",
            "fructose",
            "syrup",
            "maltose",
            "dextrose",
            "honey",
            "sweetener"
        ],

        "🛢️ Oils / Fats": [
            "oil",
            "fat",
            "butter",
            "palm",
            "sunflower",
            "vegetable oil",
            "coconut oil"
        ],

        "🧂 Salt / Minerals": [
            "salt",
            "sodium"
        ],

        "🌿 Spices / Herbs": [
            "spice",
            "spices",
            "pepper",
            "chilli",
            "chili",
            "turmeric",
            "cumin",
            "coriander"
        ],

        "🧪 Additives": [
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
            "raising agent"
        ]
    }

    categories = []

    for category, keywords in categories_data.items():

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
                "icon": category.split()[0],
                "title": category[2:],
                "ingredients": list(
                    dict.fromkeys(found)
                )
            })

    return categories


# =========================================================
# INGREDIENT DETECTIVE
# =========================================================

INGREDIENT_GUIDE = {

    "sugar": (
        "🍬 Sugar",
        "A sweetening ingredient used to provide sweetness and energy."
    ),

    "glucose": (
        "🍬 Glucose",
        "A simple sugar used as a carbohydrate source and sweetener."
    ),

    "dextrose": (
        "🍬 Dextrose",
        "A form of glucose commonly used for sweetness and carbohydrate content."
    ),

    "fructose": (
        "🍯 Fructose",
        "A naturally occurring simple sugar used mainly for sweetness."
    ),

    "syrup": (
        "🍯 Syrup",
        "A concentrated sweetening ingredient used to add sweetness and texture."
    ),

    "honey": (
        "🍯 Honey",
        "A natural sweetener used to provide sweetness and flavour."
    ),

    "salt": (
        "🧂 Salt",
        "Used mainly for flavour and preservation and contributes sodium."
    ),

    "sodium": (
        "🧂 Sodium",
        "A mineral naturally present in salt and other ingredients; important to monitor in excess."
    ),

    "citric acid": (
        "🍋 Citric Acid",
        "An acidity regulator used to control pH and provide a sour taste."
    ),

    "acidity regulator": (
        "⚖️ Acidity Regulator",
        "Used to control and maintain the acidity or pH of a food."
    ),

    "vegetable oil": (
        "🛢️ Vegetable Oil",
        "Plant-derived fat used for texture, cooking properties and flavour."
    ),

    "palm oil": (
        "🌴 Palm Oil",
        "A vegetable oil used for texture, stability and cooking properties."
    ),

    "sunflower oil": (
        "🌻 Sunflower Oil",
        "A plant-based oil used as a fat source and for texture."
    ),

    "coconut oil": (
        "🥥 Coconut Oil",
        "A plant-based fat used for texture and flavour."
    ),

    "butter": (
        "🧈 Butter",
        "A dairy fat used to provide flavour and texture."
    ),

    "lecithin": (
        "🔄 Lecithin",
        "An emulsifier that helps ingredients such as oil and water remain mixed."
    ),

    "soy lecithin": (
        "🫘 Soy Lecithin",
        "A soy-derived emulsifier used to help ingredients remain evenly mixed."
    ),

    "emulsifier": (
        "🔄 Emulsifier",
        "Helps normally difficult-to-mix ingredients, such as oil and water, stay combined."
    ),

    "sodium benzoate": (
        "🧪 Sodium Benzoate",
        "A preservative used to help slow microbial spoilage and extend shelf life."
    ),

    "potassium sorbate": (
        "🧪 Potassium Sorbate",
        "A preservative commonly used to help control mould and yeast growth."
    ),

    "preservative": (
        "🧪 Preservative",
        "Used to slow spoilage and help extend the product's shelf life."
    ),

    "xanthan gum": (
        "⚗️ Xanthan Gum",
        "A thickener and stabilizer used to improve texture and consistency."
    ),

    "guar gum": (
        "⚗️ Guar Gum",
        "A thickening ingredient used to improve texture and consistency."
    ),

    "modified starch": (
        "🌽 Modified Starch",
        "A starch modified for functional properties such as thickness, texture and stability."
    ),

    "starch": (
        "🌽 Starch",
        "A carbohydrate commonly used to provide thickness, structure or texture."
    ),

    "stabilizer": (
        "⚗️ Stabilizer",
        "Helps maintain the texture, consistency and physical stability of a food."
    ),

    "thickener": (
        "🥣 Thickener",
        "Used to increase viscosity and improve the texture of a food."
    ),

    "msg": (
        "✨ MSG",
        "A flavour enhancer used to increase savoury or umami taste."
    ),

    "monosodium glutamate": (
        "✨ Monosodium Glutamate",
        "A flavour enhancer used to increase savoury or umami taste."
    ),

    "natural flavour": (
        "🌿 Natural Flavour",
        "A flavouring ingredient used to provide or enhance flavour."
    ),

    "flavour": (
        "👃 Flavouring",
        "Added to provide or enhance the flavour of the product."
    ),

    "flavor": (
        "👃 Flavouring",
        "Added to provide or enhance the flavour of the product."
    ),

    "colour": (
        "🎨 Food Colour",
        "Used to provide, restore or improve the colour of a food."
    ),

    "color": (
        "🎨 Food Colour",
        "Used to provide, restore or improve the colour of a food."
    ),

    "wheat flour": (
        "🌾 Wheat Flour",
        "Ground wheat used to provide structure, bulk and carbohydrates."
    ),

    "wheat": (
        "🌾 Wheat",
        "A cereal grain commonly used as a carbohydrate source and structural ingredient."
    ),

    "semolina": (
        "🌾 Semolina",
        "A coarse flour usually made from durum wheat and used in foods such as pasta and bakery products."
    ),

    "rice": (
        "🍚 Rice",
        "A cereal grain and carbohydrate source."
    ),

    "corn": (
        "🌽 Corn",
        "A cereal grain used as a carbohydrate source or ingredient base."
    ),

    "milk powder": (
        "🥛 Milk Powder",
        "Dried milk solids used to provide dairy flavour, protein and texture."
    ),

    "milk": (
        "🥛 Milk",
        "A dairy ingredient that can provide protein, lactose, fat and flavour."
    ),

    "whey protein": (
        "🥛 Whey Protein",
        "A milk-derived protein used to increase protein content and improve functionality."
    ),

    "whey": (
        "🥛 Whey",
        "A milk-derived ingredient containing proteins and other milk components."
    ),

    "casein": (
        "🥛 Casein",
        "A milk protein used for nutritional and functional properties."
    ),

    "soy protein": (
        "🫘 Soy Protein",
        "Protein derived from soybeans and used as a nutritional or functional ingredient."
    ),

    "soy": (
        "🫘 Soy",
        "A soybean-derived ingredient used as a protein source or functional ingredient."
    ),

    "soya": (
        "🫘 Soya",
        "A soybean-derived ingredient used as a protein source or functional ingredient."
    ),

    "egg": (
        "🥚 Egg",
        "An ingredient used for protein, structure, binding, texture or emulsification."
    ),

    "egg powder": (
        "🥚 Egg Powder",
        "Dried egg used for protein, binding, structure and texture."
    ),

    "peanut": (
        "🥜 Peanut",
        "A legume commonly used for flavour, protein and fat."
    ),

    "almond": (
        "🥜 Almond",
        "A tree nut used for flavour, texture, protein and fat."
    ),

    "cashew": (
        "🥜 Cashew",
        "A tree nut used for flavour, texture and fat."
    )
}


def decode_ingredients(ingredients):

    if not ingredients:
        return []

    text = str(
        ingredients
    ).lower()

    result = []
    already_added = set()

    for keyword in sorted(
        INGREDIENT_GUIDE,
        key=len,
        reverse=True
    ):

        if keyword_found(
            keyword,
            text
        ):

            name, explanation = INGREDIENT_GUIDE[
                keyword
            ]

            if name not in already_added:

                result.append({
                    "name": name,
                    "explanation": explanation,
                    "keyword": keyword
                })

                already_added.add(name)

    return result


def get_ingredient_detail(ingredient):

    original = str(
        ingredient or ""
    ).strip()

    text = original.lower()

    if not text:

        return {
            "role": "Not available",
            "description": "No ingredient name was supplied.",
            "purpose": "No function can be assigned without the ingredient name.",
            "confidence": "Insufficient data",
            "source": "Product label / database"
        }

    for code, (
        name,
        role,
        purpose
    ) in FSSAI_INGREDIENT_GUIDE.items():

        number = (
            code[1:]
            if code.startswith("e")
            else code
        )

        patterns = [

            r"(?<![a-z0-9])"
            + re.escape(code)
            + r"(?![a-z0-9])",

            r"(?<![a-z0-9])ins\s*[- ]?"
            + re.escape(number)
            + r"(?![a-z0-9])"
        ]

        if any(
            re.search(
                pattern,
                text
            )
            for pattern in patterns
        ):

            return {
                "role": role,
                "description": (
                    name
                    + " is a recognised food-additive name/code."
                ),
                "purpose": purpose,
                "confidence": "Regulatory reference",
                "source": "FSSAI food-additive reference",
                "code": "INS " + number
            }

    for keyword in sorted(
        INGREDIENT_GUIDE,
        key=len,
        reverse=True
    ):

        if keyword_found(
            keyword,
            text
        ):

            name, explanation = INGREDIENT_GUIDE[
                keyword
            ]

            role = "Food ingredient"

            if any(
                x in keyword
                for x in [
                    "sugar",
                    "glucose",
                    "dextrose",
                    "fructose",
                    "syrup",
                    "honey"
                ]
            ):

                role = "Sweetener / Carbohydrate"

            elif any(
                x in keyword
                for x in [
                    "oil",
                    "butter",
                    "fat"
                ]
            ):

                role = "Oil / Fat"

            elif any(
                x in keyword
                for x in [
                    "lecithin",
                    "emulsifier"
                ]
            ):

                role = "Emulsifier"

            elif any(
                x in keyword
                for x in [
                    "preservative",
                    "benzoate",
                    "sorbate"
                ]
            ):

                role = "Preservative"

            elif any(
                x in keyword
                for x in [
                    "gum",
                    "starch",
                    "thickener",
                    "stabilizer"
                ]
            ):

                role = "Texture / Stabilizer"

            elif any(
                x in keyword
                for x in [
                    "colour",
                    "color"
                ]
            ):

                role = "Food Colour"

            elif any(
                x in keyword
                for x in [
                    "acid",
                    "acidity"
                ]
            ):

                role = "Acidity Regulator"

            return {
                "role": role,
                "description": name + ".",
                "purpose": explanation,
                "confidence": "Built-in ingredient reference",
                "source": "ProductLens knowledge layer"
            }

    return {
        "role": "Ingredient identified",
        "description": (
            "This exact ingredient was found in the "
            "product label/database, but ProductLens "
            "does not have enough evidence to assign "
            "a specific technological function."
        ),
        "purpose": (
            "No function is guessed. The package "
            "declaration remains the primary evidence "
            "for this ingredient."
        ),
        "confidence": "Insufficient evidence",
        "source": "Product label / database"
    }


def build_ingredient_details(ingredients):

    return [
        {
            "ingredient": item,
            **get_ingredient_detail(item)
        }

        for item in get_ingredient_order(
            ingredients
        )
    ]


# =========================================================
# SMART HIGHLIGHTS
# =========================================================

def make_smart_highlights(product):

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

    if not highlights:

        highlights.append({
            "icon": "🔬",
            "title": "Product Analysis",
            "text": (
                "Review the nutrition and ingredient "
                "information below."
            )
        })

    return highlights


# =========================================================
# HEALTH CAUTIONS
# =========================================================

def disease_cautions(product):

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
                "This product contains a high amount of "
                "sugar per 100 g. People managing blood "
                "glucose may need to consider portion size "
                "and their overall diet."
            ),
            "class": "danger"
        })

    if salt > 1.5:

        cautions.append({
            "icon": "❤️",
            "title": "High Salt Caution",
            "text": (
                "This product contains a relatively high "
                "amount of salt per 100 g. People managing "
                "blood pressure may need to monitor salt intake."
            ),
            "class": "danger"
        })

    if fat > 17.5:

        cautions.append({
            "icon": "❤️",
            "title": "Higher Fat Caution",
            "text": (
                "This product is relatively high in total "
                "fat per 100 g. The type of fat and overall "
                "dietary pattern also matter."
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
                    + ". Always check the package label "
                    "and allergen declaration."
                ),
                "class": "danger"
            }
        )

    ingredients_text = str(
        product.get(
            "ingredients",
            ""
        )
    ).lower()

    if (
        "palm oil" in ingredients_text
        or "palmolein" in ingredients_text
        or "palm kernel" in ingredients_text
    ):

        cautions.append({
            "icon": "🌴",
            "title": "Palm Oil Present",
            "text": (
                "Palm-derived oil is listed as an ingredient. "
                "ProductLens does not label it as inherently "
                "harmful; consider the total fat, saturated fat "
                "(if available), portion size and overall dietary pattern."
            ),
            "class": "caution"
        })

    return cautions


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

    ingredients = (
        product.get("ingredients", "")
        or ""
    )

    declared_allergens = (
        product.get("allergens", "")
        or ""
    )

    allergen_tags = (
        product.get("allergen_tags", "")
        or ""
    )

    product["detected_allergens"] = detect_allergens(
        ingredients,
        declared_allergens,
        allergen_tags
    )

    product["ingredient_order"] = (
        get_ingredient_order(
            ingredients
        )
    )

    product["ingredient_details"] = (
        build_ingredient_details(
            ingredients
        )
    )

    product["ingredient_categories"] = (
        get_ingredient_categories(
            ingredients
        )
    )

    product["decoded_ingredients"] = (
        decode_ingredients(
            ingredients
        )
    )

    product["regulatory_insights"] = (
        get_regulatory_insights(
            ingredients
        )
    )

    product["smart_highlights"] = (
        make_smart_highlights(
            product
        )
    )

    product["disease_cautions"] = (
        disease_cautions(
            product
        )
    )

    # -----------------------------------------------------
    # ProductLens score
    # Transparent data summary, NOT a medical judgement.
    # -----------------------------------------------------

    score = 100

    score -= min(
        product["sugar"] * 1.2,
        30
    )

    score -= min(
        product["salt"] * 8,
        20
    )

    score -= min(
        product["fat"] * 0.35,
        15
    )

    score += min(
        product["protein"] * 0.8,
        15
    )

    score = max(
        0,
        min(
            100,
            round(score)
        )
    )

    product["score"] = {
        "value": score,

        "label": (
            "Better balance"
            if score >= 70
            else "Moderate balance"
            if score >= 45
            else "Higher attention"
        )
    }

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

        url = OFF_API.format(
            barcode
        )

        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "ProductLens/1.0 "
                    "(food analysis application)"
                )
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
        "Detected allergens:",
        product["detected_allergens"]
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

        if (
            "energy" in name
            and "kcal" in name
        ):

            energy = value

        elif "sugars, total" in name:

            sugar = value

        elif name == "total lipid (fat)":

            fat = value

        elif name == "protein":

            protein = value

        elif name == "sodium":

            sodium = value

    # Convert sodium mg to approximate salt g

    salt = (
        sodium * 2.5 / 1000
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

    # -----------------------------------------------------
    # 1. ProductLens community database
    # -----------------------------------------------------

    product = get_saved_product(
        barcode
    )

    if product:

        product["source"] = (
            "ProductLens Community Database"
        )

        product["verified"] = bool(
            product.get(
                "verified",
                False
            )
        )

        return finalize_product(
            product
        )

    # -----------------------------------------------------
    # 2. Open Food Facts
    # -----------------------------------------------------

    product = get_from_open_food_facts(
        barcode
    )

    if product:

        save_product(
            product
        )

        return product

    # -----------------------------------------------------
    # 3. USDA FoodData Central
    # -----------------------------------------------------

    print(
        "Open Food Facts failed. "
        "Trying USDA FoodData Central..."
    )

    product = get_from_usda(
        barcode
    )

    if product:

        save_product(
            product
        )

    return product


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# BARCODE SEARCH - FORM
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
            error=(
                "Please enter or scan a barcode."
            )
        )

    if not barcode.isdigit():

        return render_template(
            "index.html",
            error=(
                "Barcode should contain numbers only."
            )
        )

    product = search_product(
        barcode
    )

    if product:

        return render_template(
            "index.html",
            product=product
        )

    return render_template(
        "index.html",

        show_manual_form=True,

        missing_barcode=barcode,

        error=(
            "Product was not found in "
            "Open Food Facts or USDA. "
            "You can enter the product "
            "information manually below."
        )
    )


# =========================================================
# BARCODE SEARCH - JSON API
# Useful for camera/scanner JavaScript
# =========================================================

@app.route(
    "/api/search/",
    methods=["GET"]
)
def api_search():

    barcode = request.args.get(
        "barcode",
        ""
    ).strip()

    if not barcode.isdigit():

        return jsonify({
            "success": False,
            "error": (
                "Barcode should contain numbers only."
            )
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

    if (
        barcode
        and barcode.isdigit()
    ):

        save_product(
            product
        )

    return render_template(
        "index.html",

        product=product,

        manual_success=True,

        manual_saved=bool(
            barcode
            and barcode.isdigit()
        )
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
            compare_error=(
                "Please enter both barcodes."
            )
        )

    if (
        not barcode1.isdigit()
        or not barcode2.isdigit()
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
            )
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

    for (
        label,
        key,
        unit
    ) in nutrients:

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
        < product2["sugar"]
    ):

        insights.append(
            product1["name"]
            + " has less sugar."
        )

    elif (
        product2["sugar"]
        < product1["sugar"]
    ):

        insights.append(
            product2["name"]
            + " has less sugar."
        )

    if (
        product1["protein"]
        > product2["protein"]
    ):

        insights.append(
            product1["name"]
            + " has more protein."
        )

    elif (
        product2["protein"]
        > product1["protein"]
    ):

        insights.append(
            product2["name"]
            + " has more protein."
        )

    comparison = {

        "product1": product1,

        "product2": product2,

        "rows": rows,

        "insights": insights
    }

    return render_template(
        "index.html",
        comparison=comparison
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    print()

    print("=" * 60)

    print("PRODUCTLENS")

    print(
        "Food Ingredient & Nutrition Intelligence"
    )

    print("=" * 60)

    print()

    print(
        "Starting Flask server..."
    )

    print(
        "Open on this PC: "
        "http://127.0.0.1:5000"
    )

    print(
        "For phone on same Wi-Fi, "
        "use your PC's local IP + :5000"
    )

    print()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
