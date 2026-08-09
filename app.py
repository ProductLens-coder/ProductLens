from flask import Flask, render_template, request
import requests
import re
import os
import json

app = Flask(__name__)

# =========================================================
# API SETTINGS
# =========================================================

OFF_API = "https://world.openfoodfacts.org/api/v2/product/{}.json"

USDA_API = "https://api.nal.usda.gov/fdc/v1/foods/search"

# DEMO_KEY has limited usage.
# Replace with your own USDA API key later if needed.
USDA_API_KEY = os.getenv("USDA_API_KEY", "DEMO_KEY")

# Optional AI fallback. ProductLens remains fully functional without a key.
AI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
AI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")

HEADERS = {
    "User-Agent": "ProductLens/1.0 (student project)"
}


# =========================================================
# ALLERGEN DATABASE
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
        "sooji",
        "rava",
        "en:wheat",
        "en:gluten"
    ],

    "Milk / Dairy": [
        "milk",
        "milk powder",
        "milk solids",
        "skimmed milk",
        "skim milk",
        "milk protein",
        "milk fat",
        "milk solids non fat",
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
        "ghee",
        "milk derivative",
        "en:milk"
    ],

    "Tree Nuts": [
        "tree nut",
        "tree nuts",
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
        "macadamia",
        "macadamia nuts",
        "nuts",
        "nut",
        "en:nuts",
        "en:tree-nuts",
        "en:almond",
        "en:cashew",
        "en:walnut",
        "en:pistachio"
    ],

    "Peanuts": [
        "peanut",
        "peanuts",
        "groundnut",
        "groundnuts",
        "ground nut",
        "peanut oil",
        "peanut flour",
        "en:peanuts"
    ],

    "Soy": [
        "soy",
        "soya",
        "soybean",
        "soybeans",
        "soy protein",
        "soy lecithin",
        "soya lecithin",
        "soy flour",
        "en:soy",
        "en:soybeans"
    ],

    "Sesame": [
        "sesame",
        "sesame seeds",
        "sesame seed",
        "til",
        "en:sesame"
    ],

    "Mustard": [
        "mustard",
        "mustard seeds",
        "mustard seed",
        "en:mustard"
    ],

    "Egg": [
        "egg",
        "eggs",
        "egg powder",
        "egg white",
        "egg yolk",
        "albumin",
        "en:eggs",
        "en:egg"
    ]
}


ALLERGEN_ICONS = {

    "Wheat / Gluten": "🌾",
    "Milk / Dairy": "🥛",
    "Tree Nuts": "🌰",
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
# BARCODE NORMALIZATION
# =========================================================

def normalize_barcodes(barcode):

    barcode = str(barcode).strip()

    # Keep numbers only
    barcode = re.sub(r"\D", "", barcode)

    codes = []

    if barcode:
        codes.append(barcode)

    # UPC-A -> EAN-13
    if len(barcode) == 12:
        codes.append("0" + barcode)

    # EAN-13 -> UPC-A
    if len(barcode) == 13 and barcode.startswith("0"):
        codes.append(barcode[1:])

    # GTIN-14 commonly stores an EAN-13 with a leading 0
    if len(barcode) == 14 and barcode.startswith("0"):
        codes.append(barcode[1:])
        if barcode[1] == "0":
            codes.append(barcode[2:])

    # EAN-8 is already directly searchable, but keep it explicit
    if len(barcode) == 8:
        codes.append(barcode)

    # Remove duplicates
    return list(dict.fromkeys(codes))


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

    combined_text = combined_text.replace("en:", " ")
    combined_text = combined_text.replace("-", " ")
    combined_text = combined_text.replace("_", " ")
    combined_text = combined_text.replace(";", " ")
    combined_text = combined_text.replace(",", " ")

    detected = []

    for allergen, keywords in ALLERGEN_GUIDE.items():

        found_keyword = None

        for keyword in keywords:

            clean_keyword = keyword.lower()

            clean_keyword = clean_keyword.replace(
                "en:", ""
            )

            clean_keyword = clean_keyword.replace(
                "-", " "
            )

            clean_keyword = clean_keyword.replace(
                "_", " "
            )

            pattern = (
                r"(?<![a-z])"
                + re.escape(clean_keyword)
                + r"(?![a-z])"
            )

            if re.search(pattern, combined_text):

                found_keyword = clean_keyword
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
# ALLERGEN SOURCE-AWARE DETECTION
# =========================================================

def detect_allergen_details(ingredients="", declared_allergens="", allergen_tags=""):
    """Return detected allergens plus whether they were explicitly declared."""
    declared_text = " ".join(
        str(value) for value in [declared_allergens, allergen_tags]
        if value
    )
    ingredient_text = str(ingredients or "")

    declared = detect_allergens(declared_text)
    inferred = detect_allergens(ingredient_text)

    ordered = []
    seen = set()
    declared_names = {item["name"] for item in declared}

    for item in declared + inferred:
        name = item["name"]
        if name in seen:
            continue
        seen.add(name)
        copy = dict(item)
        copy["source"] = "Declared allergen information" if name in declared_names else "Ingredient information"
        copy["declared"] = name in declared_names
        ordered.append(copy)

    return ordered


def allergen_data_status(ingredients="", declared_allergens="", allergen_tags=""):
    declared_text = " ".join(
        str(value) for value in [declared_allergens, allergen_tags]
        if value
    ).strip()
    if declared_text and detect_allergens(declared_text):
        return "declared"
    if ingredients and detect_allergens(ingredients):
        return "ingredient_detected"
    if declared_text or ingredients:
        return "checked_none"
    return "unavailable"


def ai_fill_missing_intelligence(product):
    """Optional AI fallback: interpret only evidence already present in the product record."""
    base = {
        "allergens": [],
        "additives": [],
        "attention_items": [],
        "summary_points": []
    }

    if not AI_API_KEY:
        return base

    evidence = {
        "name": product.get("name", ""),
        "brand": product.get("brands", ""),
        "ingredients": product.get("ingredients", ""),
        "declared_allergens": product.get("allergens", ""),
        "allergen_tags": product.get("allergen_tags", ""),
        "nutrition_per_100g": {
            "energy_kcal": product.get("energy", 0),
            "sugar_g": product.get("sugar", 0),
            "fat_g": product.get("fat", 0),
            "protein_g": product.get("protein", 0),
            "salt_g": product.get("salt", 0),
        }
    }

    prompt = (
        "You are the ProductLens backend intelligence layer. Use ONLY the supplied product evidence. "
        "Do not invent ingredients, allergens, additives, health effects, or adulteration claims. "
        "If evidence is missing, return an empty list. Normalize allergen synonyms such as soya/soy, "
        "nuts/tree nuts, wheat/gluten, and milk/dairy. Treat ordinary food ingredients as concerns only "
        "when there is a clear reason in the evidence. Never call an ingredient adulteration merely because "
        "it is processed. Return JSON with exactly these keys: allergens, additives, attention_items, summary_points. "
        "Each list must contain short plain-language strings.\n\nEvidence:\n"
        + json.dumps(evidence, ensure_ascii=False)
    )

    try:
        response = requests.post(
            AI_API_URL,
            headers={
                "Authorization": f"Bearer {AI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": AI_MODEL,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": "Return valid JSON only."},
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=20
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            for key in base:
                if isinstance(parsed.get(key), list):
                    base[key] = [str(x).strip() for x in parsed[key] if str(x).strip()]
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError) as exc:
        print("AI fallback unavailable:", exc)

    return base


# =========================================================
# NUTRITION LEVEL
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
        "fat": 50,
        "protein": 20,
        "salt": 3
    }

    maximum = maximums.get(
        nutrient,
        100
    )

    percent = (value / maximum) * 100

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

    text = str(ingredients)

    text = text.replace(
        ";",
        ","
    )

    parts = text.split(",")

    result = []

    for part in parts:

        part = part.strip()

        if part:
            result.append(part)

    return result


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
            "oat",
            "oats"
        ],

        "🍬 Sugars / Sweeteners": [
            "sugar",
            "glucose",
            "fructose",
            "syrup",
            "maltose",
            "dextrose",
            "sucrose",
            "honey",
            "sweetener"
        ],

        "🫒 Oils / Fats": [
            "oil",
            "fat",
            "butter",
            "palm",
            "sunflower",
            "vegetable oil",
            "coconut oil",
            "olive oil",
            "canola oil"
        ],

        "🧂 Salt / Minerals": [
            "salt",
            "sodium",
            "potassium"
        ],

        "🌿 Spices / Herbs": [
            "spice",
            "spices",
            "pepper",
            "chilli",
            "turmeric",
            "cumin",
            "coriander",
            "ginger",
            "garlic",
            "cinnamon"
        ],

        "🧪 Additives": [
            "preservative",
            "emulsifier",
            "stabilizer",
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

            if keyword in text:
                found.append(keyword)

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

def decode_ingredients(ingredients):
    """Explain every listed ingredient without silently dropping unknown items."""
    if not ingredients:
        return []

    raw_items = get_ingredient_order(ingredients)
    if not raw_items:
        return []

    guide = {
        "potato": ("Base vegetable ingredient", "Provides the main potato component and contributes carbohydrate and texture.", "Used as the primary food ingredient."),
        "refined palmolein oil": ("Vegetable oil", "A refined palm-derived oil used for cooking and texture.", "Used as a cooking fat and to provide crispness and texture."),
        "palmolein oil": ("Vegetable oil", "A refined palm-derived oil used for cooking and texture.", "Used as a cooking fat and to provide crispness and texture."),
        "palm oil": ("Vegetable oil", "A plant-derived oil used for cooking, texture and stability.", "Used as a fat source and to influence product texture."),
        "bengal gram hour": ("Legume flour", "Bengal gram flour is a chickpea-based flour that contributes carbohydrate and plant protein.", "Used to provide body, structure and characteristic flavour."),
        "bengal gram flour": ("Legume flour", "Flour made from Bengal gram (chickpea), providing carbohydrate and plant protein.", "Used to provide body, structure and characteristic flavour."),
        "besan": ("Legume flour", "Chickpea flour made from Bengal gram.", "Used to provide body, structure and flavour."),
        "potato flakes": ("Potato ingredient", "Dehydrated potato pieces used to provide potato solids and texture.", "Used to provide potato flavour, solids and texture."),
        "potato starch": ("Starch", "Starch extracted from potato and used as a carbohydrate-based functional ingredient.", "Used to improve crispness, binding or texture."),
        "tapioca starch": ("Starch", "Starch obtained from cassava/tapioca.", "Used to provide binding, crispness or texture."),
        "starch": ("Starch", "A carbohydrate-based ingredient commonly used for structure and texture.", "Used to thicken, bind or improve texture."),
        "salt": ("Seasoning", "Salt used mainly for flavour and sodium contribution.", "Used to season the product."),
        "sugar": ("Sweetener", "A sweetening ingredient that contributes to sweetness and sugar content.", "Used to provide sweetness."),
        "citric acid": ("Acidity regulator", "An organic acid used to control acidity and provide tartness.", "Used to regulate acidity and flavour."),
        "wheat flour": ("Cereal flour", "Flour made from wheat and used as a carbohydrate and structural ingredient.", "Used to provide structure and bulk."),
        "milk powder": ("Dairy ingredient", "Dried milk solids containing milk proteins and other dairy components.", "Used to provide dairy solids, flavour and body."),
        "lecithin": ("Emulsifier", "A phospholipid used to help oil and water-based components stay mixed.", "Used to improve mixing and product stability."),
        "natural flavour": ("Flavouring", "A flavouring ingredient used to provide or enhance taste or aroma.", "Used to provide or enhance flavour."),
        "natural flavor": ("Flavouring", "A flavouring ingredient used to provide or enhance taste or aroma.", "Used to provide or enhance flavour."),
        "preservative": ("Preservative", "An ingredient used to slow deterioration caused by microorganisms.", "Used to help maintain shelf life."),
        "xanthan gum": ("Thickener / stabilizer", "A polysaccharide commonly used to increase viscosity and stabilize texture.", "Used to thicken and stabilize the product."),
        "guar gum": ("Thickener", "A plant-derived gum used to increase viscosity.", "Used to improve thickness and texture."),
        "modified starch": ("Modified starch", "Starch modified for functional food properties.", "Used to improve texture, binding or stability."),
        "colour": ("Food colour", "A colouring ingredient used to provide or restore appearance.", "Used to provide or restore colour."),
        "color": ("Food colour", "A colouring ingredient used to provide or restore appearance.", "Used to provide or restore colour."),
        "flavour": ("Flavouring", "A flavouring ingredient used to provide or enhance taste or aroma.", "Used to provide or enhance flavour."),
        "flavor": ("Flavouring", "A flavouring ingredient used to provide or enhance taste or aroma.", "Used to provide or enhance flavour."),
        "whey": ("Dairy ingredient", "A milk-derived ingredient containing whey proteins and other milk components.", "Used for dairy solids, protein or functional properties."),
        "butter": ("Dairy fat", "A dairy fat used for flavour and texture.", "Used to provide flavour and fat-based texture."),
        "cheese": ("Dairy ingredient", "A dairy ingredient contributing flavour, protein and texture.", "Used for flavour, texture and dairy solids."),
        "cocoa": ("Cocoa ingredient", "Cocoa solids used to provide chocolate flavour and colour.", "Used to provide chocolate flavour and colour."),
        "vanilla": ("Flavouring", "A flavouring ingredient providing characteristic aroma and taste.", "Used to provide vanilla flavour and aroma."),
    }

    def find_match(item):
        clean = re.sub(r"\s+", " ", str(item).strip().lower())
        if clean in guide:
            return guide[clean]
        for key in sorted(guide, key=len, reverse=True):
            if key in clean:
                return guide[key]
        return None

    result = []
    for item in raw_items:
        data = find_match(item)
        if data:
            role, description, purpose = data
            confidence = "High"
            source = "ProductLens ingredient knowledge base"
        else:
            role = "Identified ingredient"
            description = "This ingredient is listed in the product database. Its exact technological function depends on the formulation."
            purpose = "Used as part of the product formulation; the package declaration is the primary source for its exact function."
            confidence = "Database-listed"
            source = "Open Food Facts ingredient data"

        result.append({
            "ingredient": item,
            "role": role,
            "code": "",
            "description": description,
            "purpose": purpose,
            "confidence": confidence,
            "source": source
        })

    return result

# =========================================================
# PRODUCT SUMMARY
# =========================================================

def create_product_summary(product):
    """Create a concise, confident, user-friendly product briefing."""
    points = []

    allergens = product.get("detected_allergens", []) or []
    if allergens:
        names = ", ".join(item["name"].replace(" / Gluten", "") for item in allergens)
        points.append({"icon": "🚨", "title": "Allergens Detected", "text": names})

    ingredients = str(product.get("ingredients", "") or "").lower()
    additive_terms = [
        ("preservative", "Preservative listed"),
        ("flavouring", "Flavouring listed"),
        ("flavoring", "Flavouring listed"),
        ("flavour", "Flavouring listed"),
        ("flavor", "Flavouring listed"),
        ("emulsifier", "Emulsifier listed"),
        ("stabilizer", "Stabilizer listed"),
        ("thickener", "Thickener listed"),
        ("colour", "Food colour listed"),
        ("color", "Food colour listed"),
        ("raising agent", "Raising agent listed"),
    ]
    additives = []
    for term, label in additive_terms:
        if term in ingredients and label not in additives:
            additives.append(label)
    if additives:
        points.append({"icon": "🧪", "title": "Additives Detected", "text": ", ".join(additives[:4])})

    if any(term in ingredients for term in ["hydrogenated", "partially hydrogenated"]):
        points.append({"icon": "⚠️", "title": "Hydrogenated Fat Detected", "text": "Hydrogenated fat wording is present in the ingredient list."})

    if any(term in ingredients for term in ["refined palmolein", "refined palm oil", "palmolein oil"]):
        points.append({"icon": "🛢️", "title": "Refined Oil Detected", "text": "Refined palm-derived oil is listed."})

    fat = safe_number(product.get("fat"))
    sugar = safe_number(product.get("sugar"))
    salt = safe_number(product.get("salt"))
    if fat > 17.5:
        points.append({"icon": "🔴", "title": "High Fat", "text": f"{fat:.1f} g per 100 g"})
    if sugar > 15:
        points.append({"icon": "🍬", "title": "High Sugar", "text": f"{sugar:.1f} g per 100 g"})
    if salt > 1.5:
        points.append({"icon": "🧂", "title": "High Salt", "text": f"{salt:.2f} g per 100 g"})

    if not points:
        points.append({"icon": "✅", "title": "No Major Flags", "text": "No major ProductLens flags were identified from the available data."})

    return points[:6]


# =========================================================
# LABEL AWARENESS
# =========================================================

def create_label_awareness(product):

    ingredients = str(
        product.get("ingredients", "")
    ).lower()

    awareness = []

    # Added sugars
    sugar_terms = [
        "sugar",
        "glucose",
        "dextrose",
        "fructose",
        "sucrose",
        "syrup",
        "maltose"
    ]

    found_sugars = [
        term
        for term in sugar_terms
        if term in ingredients
    ]

    if found_sugars:

        awareness.append({

            "icon": "🍬",

            "title": "Look beyond the word 'sweet'",

            "text":
                "The ingredient list contains sugar or sweetening ingredients. "
                "Check how early they appear in the ingredient list and compare "
                "this with the nutrition panel.",

            "class": "caution"

        })

    # Colours
    if any(
        term in ingredients
        for term in [
            "colour",
            "color",
            "food colour",
            "food color"
        ]
    ):

        awareness.append({

            "icon": "🎨",

            "title": "Added colour detected",

            "text":
                "A colouring ingredient appears in the available ingredient list. "
                "If this matters to you, check the package for the specific colour "
                "name or additive number.",

            "class": "info"

        })

    # Flavour
    if any(
        term in ingredients
        for term in [
            "flavour",
            "flavor",
            "flavouring",
            "flavoring"
        ]
    ):

        awareness.append({

            "icon": "👅",

            "title": "Flavouring detected",

            "text":
                "The product contains a flavouring term. The database may not "
                "show every detail of the flavouring mixture, so the physical "
                "package is the better source for the exact declaration.",

            "class": "info"

        })

    # Preservatives
    if any(
        term in ingredients
        for term in [
            "preservative",
            "sodium benzoate",
            "potassium sorbate"
        ]
    ):

        awareness.append({

            "icon": "🧪",

            "title": "Preservative detected",

            "text":
                "A preservative or preservative-related ingredient appears in "
                "the available ingredient information. Check the label for its "
                "specific name or additive number.",

            "class": "caution"

        })

    # Emulsifiers
    if any(
        term in ingredients
        for term in [
            "emulsifier",
            "lecithin"
        ]
    ):

        awareness.append({

            "icon": "🔬",

            "title": "Emulsifier detected",

            "text":
                "An emulsifier appears in the ingredient list. These ingredients "
                "are commonly used to help components such as oil and water stay mixed.",

            "class": "info"

        })

    # Palm oil
    if "palm oil" in ingredients:

        awareness.append({

            "icon": "🌴",

            "title": "Palm oil detected",

            "text":
                "Palm oil appears in the available ingredient information. "
                "ProductLens is flagging its presence for label awareness, "
                "not making a health claim about the ingredient.",

            "class": "info"

        })

    # Hydrogenated fat
    if any(
        term in ingredients
        for term in [
            "hydrogenated",
            "partially hydrogenated"
        ]
    ):

        awareness.append({

            "icon": "⚠️",

            "title": "Hydrogenated fat wording detected",

            "text":
                "Hydrogenated wording appears in the ingredient information. "
                "Check the physical nutrition label and ingredient declaration "
                "for the exact type and amount.",

            "class": "caution"

        })

    # Allergens
    if product.get("detected_allergens"):

        awareness.append({

            "icon": "🚨",

            "title": "Allergen declaration deserves attention",

            "text":
                "Potential allergens were identified from the available product "
                "data. Always verify the package allergen statement, especially "
                "for a known food allergy.",

            "class": "danger"

        })

    # Always give a useful final awareness message
    awareness.append({

        "icon": "📦",

        "title": "Database vs. physical label",

        "text":
            "Product information can change with reformulation or regional "
            "packaging. ProductLens should be used as an awareness tool; "
            "the current physical package remains the final label reference.",

        "class": "neutral"

    })

    return awareness


# =========================================================
# INGREDIENT REALITY CHECK
# =========================================================

def ingredient_reality_check(product):

    ingredients = str(
        product.get("ingredients", "")
    ).lower()

    checks = []

    # Sugar reality
    sugar_words = [
        "sugar",
        "glucose",
        "dextrose",
        "fructose",
        "sucrose",
        "syrup",
        "maltose"
    ]

    sugar_found = [
        word
        for word in sugar_words
        if word in ingredients
    ]

    if sugar_found:

        checks.append({

            "icon": "🍬",

            "title": "Sweetening ingredients present",

            "text":
                "The product uses one or more sweetening ingredients. "
                "Ingredient names and the nutrition panel should be considered together.",

            "severity": "attention"

        })

    # Additive reality
    additive_words = [
        "preservative",
        "emulsifier",
        "stabilizer",
        "thickener",
        "colour",
        "color",
        "flavour",
        "flavor",
        "acidity regulator"
    ]

    additive_found = [
        word
        for word in additive_words
        if word in ingredients
    ]

    if additive_found:

        checks.append({

            "icon": "🧪",

            "title": "Functional additives present",

            "text":
                "The ingredient list contains ingredients used for functions "
                "such as preservation, colour, flavour, stability or texture. "
                "Their presence alone does not determine whether a food is healthy or unhealthy.",

            "severity": "info"

        })

    # Refined grain reality
    if any(
        term in ingredients
        for term in [
            "maida",
            "refined wheat flour",
            "wheat flour"
        ]
    ):

        checks.append({

            "icon": "🌾",

            "title": "Wheat flour detected",

            "text":
                "Wheat flour appears in the ingredient list. If you are looking "
                "for a whole-grain product, check whether whole wheat or another "
                "whole grain is specifically declared.",

            "severity": "info"

        })

    # Fat reality
    oil_terms = [
        "palm oil",
        "vegetable oil",
        "sunflower oil",
        "coconut oil",
        "olive oil",
        "butter",
        "ghee"
    ]

    oil_found = [
        term
        for term in oil_terms
        if term in ingredients
    ]

    if oil_found:

        checks.append({

            "icon": "🫒",

            "title": "Added fat/oil detected",

            "text":
                "A fat or oil ingredient appears in the product. "
                "Compare this with total fat on the nutrition panel.",

            "severity": "info"

        })

    if not checks:

        checks.append({

            "icon": "🔎",

            "title": "No major ingredient pattern detected",

            "text":
                "ProductLens did not identify a major ingredient pattern from "
                "its current awareness rules. Review the full ingredient list "
                "for the most complete picture.",

            "severity": "neutral"

        })

    return checks


# =========================================================
# DISEASE / HEALTH CAUTIONS
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

            "icon": "⚠️",

            "title": "Diabetes Caution",

            "text":
                "This product contains a high amount of sugar per 100 g. "
                "People with diabetes may need to limit or carefully portion "
                "high-sugar foods.",

            "class": "danger"

        })

    if salt > 1.5:

        cautions.append({

            "icon": "⚠️",

            "title": "Blood Pressure / Hypertension Caution",

            "text":
                "This product contains a relatively high amount of salt per 100 g. "
                "People managing high blood pressure may need to monitor their "
                "sodium and salt intake.",

            "class": "danger"

        })

    if fat > 17.5:

        cautions.append({

            "icon": "🫒",

            "title": "Higher Total Fat",

            "text":
                "This product is relatively high in total fat per 100 g. "
                "Overall dietary pattern and the type of fat are important "
                "when considering cardiovascular health.",

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

                "text":
                    "Potential allergens detected: "
                    + names
                    + ". People with a relevant food allergy should check "
                    "the package label and allergen declaration carefully.",

                "class": "danger"

            }

        )

    return cautions


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

            "text":
                "Sugar is relatively high per 100 g."

        })

    elif 0 < sugar <= 5:

        highlights.append({

            "icon": "✅",

            "title": "Lower Sugar",

            "text":
                "Sugar is relatively low per 100 g."

        })

    if fat > 17.5:

        highlights.append({

            "icon": "🫒",

            "title": "Higher Fat",

            "text":
                "Total fat is relatively high per 100 g."

        })

    if protein >= 10:

        highlights.append({

            "icon": "💪",

            "title": "Higher Protein",

            "text":
                "Protein is relatively high per 100 g."

        })

    if salt > 1.5:

        highlights.append({

            "icon": "🧂",

            "title": "High Salt",

            "text":
                "Salt is relatively high per 100 g."

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

            "icon": "🔎",

            "title": "Product Analysis",

            "text":
                "Review the nutrition and ingredient information below."

        })

    return highlights


# =========================================================
# PRODUCT SCORE
# =========================================================

def calculate_score(product):

    score = 100

    sugar = safe_number(
        product.get("sugar")
    )

    fat = safe_number(
        product.get("fat")
    )

    salt = safe_number(
        product.get("salt")
    )

    protein = safe_number(
        product.get("protein")
    )

    if sugar > 15:
        score -= 20

    elif sugar > 5:
        score -= 8

    if fat > 17.5:
        score -= 15

    elif fat > 3:
        score -= 5

    if salt > 1.5:
        score -= 15

    elif salt > 0.3:
        score -= 5

    if protein >= 10:
        score += 5

    score = max(
        0,
        min(score, 100)
    )

    if score >= 75:

        label = "Good"
        css = "good"

    elif score >= 50:

        label = "Moderate"
        css = "moderate"

    else:

        label = "Needs Attention"
        css = "attention"

    return {

        "value": score,

        "label": label,

        "class": css

    }


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

    ingredients = product.get(
        "ingredients",
        ""
    ) or ""

    declared_allergens = product.get(
        "allergens",
        ""
    ) or ""

    allergen_tags = product.get(
        "allergen_tags",
        ""
    ) or ""

    product["detected_allergens"] = detect_allergen_details(
        ingredients,
        declared_allergens,
        allergen_tags
    )

    product["allergen_status"] = allergen_data_status(
        ingredients,
        declared_allergens,
        allergen_tags
    )

    product["ai_intelligence"] = ai_fill_missing_intelligence(product)

    # AI is a fallback, never a source of invented facts. Add only evidence-backed missing items.
    if not product["detected_allergens"] and product["ai_intelligence"].get("allergens"):
        for name in product["ai_intelligence"]["allergens"]:
            product["detected_allergens"].append({
                "name": name,
                "icon": ALLERGEN_ICONS.get(name, "🚨"),
                "keyword": "AI evidence",
                "source": "AI evidence from available product data",
                "declared": False
            })

    product["allergen_status"] = (
        "ai_detected" if product["ai_intelligence"].get("allergens") and not declared_allergens
        else product["allergen_status"]
    )

    product["ingredient_order"] = get_ingredient_order(
        ingredients
    )

    product["ingredient_categories"] = get_ingredient_categories(
        ingredients
    )

    product["ingredient_details"] = decode_ingredients(
        ingredients
    )

    product["decoded_ingredients"] = product["ingredient_details"]

    product["smart_highlights"] = make_smart_highlights(product) or [
        {
            "icon": "🔎",
            "title": "Product Analysis",
            "text": "Nutrition and ingredient information is available below."
        }
    ]

    product["disease_cautions"] = disease_cautions(
        product
    )

    product["score"] = calculate_score(
        product
    )

    # NEW INTELLIGENCE FEATURES
    product["product_summary"] = create_product_summary(
        product
    )

    product["label_awareness"] = create_label_awareness(
        product
    )

    product["ingredient_reality"] = ingredient_reality_check(
        product
    )

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
# FSSAI LICENCE / REGISTRATION EXTRACTION
# =========================================================
def extract_fssai_number(raw):
    """Extract a 14-digit FSSAI licence/registration number only from label-like data."""
    fields = [
        raw.get("ingredients_text_with_allergens"),
        raw.get("ingredients_text_with_allergens_en"),
        raw.get("ingredients_text"),
        raw.get("ingredients_text_en"),
        raw.get("generic_name"),
        raw.get("generic_name_en"),
        raw.get("manufacturing_places"),
        raw.get("packaging_text"),
        raw.get("labels"),
        raw.get("stores"),
    ]
    text = " ".join(str(x) for x in fields if x)
    # FSSAI licence/registration numbers are 14 digits; licence starts with 1, registration with 2.
    matches = re.findall(r"(?<!\d)([12]\d{13})(?!\d)", text)
    return matches[0] if matches else ""


# =========================================================
# OPEN FOOD FACTS
# =========================================================

def extract_off_ingredients(raw):

    candidates = [
        raw.get("ingredients_text_with_allergens"),
        raw.get("ingredients_text_with_allergens_en"),
        raw.get("ingredients_text"),
        raw.get("ingredients_text_en")
    ]

    for value in candidates:
        if value and str(value).strip():
            return str(value).strip()

    structured = raw.get("ingredients") or []
    parts = []

    if isinstance(structured, list):
        for item in structured:
            if not isinstance(item, dict):
                continue
            name = (
                item.get("text")
                or item.get("text_en")
                or item.get("id")
                or ""
            )
            if name and str(name).strip():
                parts.append(str(name).strip())

    return ", ".join(parts) if parts else ""


def get_from_open_food_facts(barcode):

    print()
    print("=" * 60)
    print("DATABASE 1: OPEN FOOD FACTS")
    print("Original barcode:", barcode)

    barcodes = normalize_barcodes(
        barcode
    )

    print(
        "Barcode variations:",
        barcodes
    )

    for code in barcodes:

        print(
            "Searching OFF barcode:",
            code
        )

        try:

            url = OFF_API.format(
                code
            )

            response = requests.get(

                url,

                headers=HEADERS,

                timeout=15

            )

            print(
                "OFF STATUS CODE:",
                response.status_code
            )

            if response.status_code == 404:

                print(
                    "Barcode not found:",
                    code
                )

                continue

            response.raise_for_status()

            data = response.json()

        except requests.exceptions.RequestException as e:

            print(
                "Open Food Facts error:",
                e
            )

            continue

        except ValueError:

            print(
                "Invalid Open Food Facts JSON."
            )

            continue

        if data.get("status") != 1:

            print(
                "No product in Open Food Facts for:",
                code
            )

            continue

        raw = data.get(
            "product",
            {}
        )

        ingredients = extract_off_ingredients(raw)

        declared_allergens = " ".join(
            str(value) for value in [
                raw.get("allergens", ""),
                raw.get("allergens_from_ingredients", ""),
                raw.get("allergens_hierarchy", ""),
                raw.get("traces", "")
            ] if value
        )

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

        sugar = nutrition.get(
            "sugars_100g",
            0
        )

        fat = nutrition.get(
            "fat_100g",
            0
        )

        protein = nutrition.get(
            "proteins_100g",
            0
        )

        salt = nutrition.get(
            "salt_100g",
            0
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

            "barcode": code,

            "image": raw.get(
                "image_front_url",
                ""
            ),

            "ingredients": ingredients,

            "allergens": declared_allergens,

            "allergen_tags": allergen_tags_text,

            "energy": energy,

            "sugar": sugar,

            "fat": fat,

            "protein": protein,

            "salt": salt,

            "source": "Open Food Facts",

            "verified": True

        }

        product = finalize_product(
            product
        )

        print(
            "PRODUCT FOUND:",
            product["name"]
        )

        print(
            "SOURCE:",
            product["source"]
        )

        return product

    print(
        "Product not found in Open Food Facts."
    )

    return None


# =========================================================
# USDA FOODDATA CENTRAL
# =========================================================

def get_from_usda(barcode):

    print()
    print("=" * 60)
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
    )

    if not foods:

        print(
            "No USDA result."
        )

        return None

    food = foods[0]

    nutrients = food.get(
        "foodNutrients",
        []
    )

    energy = 0
    sugar = 0
    fat = 0
    protein = 0
    salt = 0

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

        if "energy" in name:

            energy = value

        elif "sugars, total" in name:

            sugar = value

        elif name == "total lipid (fat)":

            fat = value

        elif name == "protein":

            protein = value

        elif "sodium" in name:

            # Sodium mg -> approximate salt g
            salt = (
                value * 2.5 / 1000
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

    print(
        "USDA PRODUCT FOUND:",
        product["name"]
    )

    return finalize_product(
        product
    )


# =========================================================
# OPEN FOOD FACTS SEARCH FALLBACK
# =========================================================
def get_from_off_search(barcode):
    """Fallback lookup for products whose direct barcode endpoint misses."""
    try:
        response = requests.get(
            "https://world.openfoodfacts.org/api/v2/search",
            params={
                "code": str(barcode),
                "page_size": 1,
                "fields": "code,product_name,product_name_en,brands,image_front_url,ingredients_text,ingredients_text_en,ingredients_text_with_allergens,ingredients_text_with_allergens_en,allergens,allergens_from_ingredients,allergens_tags,allergens_hierarchy,nutriments"
            },
            headers=HEADERS,
            timeout=12
        )
        response.raise_for_status()
        data = response.json()
        products = data.get("products") or []
        if not products:
            return None

        raw = products[0]
        raw["status"] = 1
        # Reuse the exact OFF parser by feeding the returned product through
        # a tiny local reconstruction of the fields it expects.
        nutrition = raw.get("nutriments", {}) or {}
        product = {
            "name": raw.get("product_name") or raw.get("product_name_en") or "Unknown Product",
            "brands": raw.get("brands", ""),
            "barcode": raw.get("code") or str(barcode),
            "image": raw.get("image_front_url", ""),
            "ingredients": extract_off_ingredients(raw),
            "allergens": " ".join(str(v) for v in [raw.get("allergens", ""), raw.get("allergens_from_ingredients", ""), raw.get("allergens_hierarchy", "")] if v),
            "allergen_tags": " ".join(str(v) for v in (raw.get("allergens_tags") or [])),
            "energy": safe_number(nutrition.get("energy-kcal_100g", nutrition.get("energy-kcal", 0))),
            "sugar": safe_number(nutrition.get("sugars_100g", nutrition.get("sugar_100g", 0))),
            "fat": safe_number(nutrition.get("fat_100g", 0)),
            "protein": safe_number(nutrition.get("proteins_100g", nutrition.get("protein_100g", 0))),
            "salt": safe_number(nutrition.get("salt_100g", 0)),
            "source": "Open Food Facts",
            "verified": True
        }
        return finalize_product(product)
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        print("OFF search fallback error:", exc)
        return None


# =========================================================
# SEARCH PRODUCT
# =========================================================

def search_product(barcode):

    barcode = str(
        barcode
    ).strip()

    print()
    print("=" * 60)
    print("PRODUCTLENS SEARCH")
    print("Barcode:", barcode)
    print("=" * 60)

    # -----------------------------------------
    # DATABASE 1
    # -----------------------------------------

    product = get_from_open_food_facts(
        barcode
    )

    if product:

        print(
            "SUCCESS: Product found in Open Food Facts."
        )

        return product

    print(
        "OFF: Product not found by direct barcode endpoint."
    )

    # -----------------------------------------
    # OPEN FOOD FACTS SEARCH FALLBACK
    # -----------------------------------------
    for code in normalize_barcodes(barcode):
        product = get_from_off_search(code)
        if product:
            print("SUCCESS: Product found using Open Food Facts search fallback.")
            return product

    # -----------------------------------------
    # DATABASE 2
    # -----------------------------------------

    print(
        "Trying USDA FoodData Central..."
    )

    product = get_from_usda(
        barcode
    )

    if product:

        print(
            "SUCCESS: Product found in USDA."
        )

        return product

    print(
        "USDA: Product not found."
    )

    return None


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# SEARCH
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

            error="Please enter a barcode."

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

            product=product

        )

    return render_template(

        "index.html",

        show_manual_form=True,

        missing_barcode=barcode,

        error=
            "Barcode recognized, but product information was not found "
            "in the available databases."

    )


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

        manual_success=True

    )


# =========================================================
# COMPARE PRODUCTS
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

            compare_error=
                "Please enter both barcodes."

        )

    if (
        not barcode1.isdigit()
        or not barcode2.isdigit()
    ):

        return render_template(

            "index.html",

            compare_error=
                "Barcodes should contain numbers only."

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

            compare_error=
                "One or both products could not be found."

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
            product1["name"]
            + " has less sugar."
        )

    elif product2["sugar"] < product1["sugar"]:

        insights.append(
            product2["name"]
            + " has less sugar."
        )

    if product1["protein"] > product2["protein"]:

        insights.append(
            product1["name"]
            + " has more protein."
        )

    elif product2["protein"] > product1["protein"]:

        insights.append(
            product2["name"]
            + " has more protein."
        )

    if (
        product1["score"]["value"]
        > product2["score"]["value"]
    ):

        insights.append(
            product1["name"]
            + " has the higher ProductLens score."
        )

    elif (
        product2["score"]["value"]
        > product1["score"]["value"]
    ):

        insights.append(
            product2["name"]
            + " has the higher ProductLens score."
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
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("🔎 PRODUCTLENS")
    print("Food Ingredient & Nutrition Intelligence")
    print("=" * 60)
    print()
    print("Starting Flask server...")
    print("Open http://127.0.0.1:5000")
    print()

    app.run(

        host="0.0.0.0",

        port=5000,

        debug=True

    )
