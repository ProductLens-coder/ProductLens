from flask import Flask, render_template, request
import requests
import re

app = Flask(__name__)


# =========================================================
# API SETTINGS
# =========================================================

OFF_API = "https://world.openfoodfacts.org/api/v2/product/{}.json"

USDA_API = "https://api.nal.usda.gov/fdc/v1/foods/search"

USDA_API_KEY = "DEMO_KEY"


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
            clean_keyword = clean_keyword.replace("en:", "")
            clean_keyword = clean_keyword.replace("-", " ")
            clean_keyword = clean_keyword.replace("_", " ")

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
        "fat": 30,
        "protein": 20,
        "salt": 3
    }

    maximum = maximums.get(nutrient, 100)

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
        "percent": round(percent, 1),
        "class": level_class
    }


# =========================================================
# INGREDIENT ORDER
# =========================================================

def get_ingredient_order(ingredients):

    if not ingredients:
        return []

    text = str(ingredients)

    text = text.replace(";", ",")

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

    text = str(ingredients).lower()

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

        "🛢️ Oils / Fats": [
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

    if not ingredients:
        return []

    text = str(ingredients).lower()

    ingredient_guide = {

        "sugar": (
            "🍬 Sugar",
            "A sweetening ingredient that contributes to the product's sugar content."
        ),

        "glucose": (
            "🍬 Glucose",
            "A simple sugar used as a carbohydrate and sweetening ingredient."
        ),

        "dextrose": (
            "🍬 Dextrose",
            "A form of glucose commonly used as a sweetener and carbohydrate source."
        ),

        "fructose": (
            "🍯 Fructose",
            "A naturally occurring simple sugar that provides sweetness."
        ),

        "sucrose": (
            "🍬 Sucrose",
            "Common table sugar composed of glucose and fructose."
        ),

        "syrup": (
            "🍯 Syrup",
            "A sweetening ingredient commonly used to add sweetness and texture."
        ),

        "honey": (
            "🍯 Honey",
            "A naturally derived sweetener produced by bees."
        ),

        "salt": (
            "🧂 Salt",
            "Used mainly for flavour and contributes sodium to the diet."
        ),

        "sodium": (
            "🧂 Sodium",
            "A mineral that contributes to the sodium content of food."
        ),

        "citric acid": (
            "🍋 Citric Acid",
            "Used to control acidity and provide a sour taste."
        ),

        "acidity regulator": (
            "⚖️ Acidity Regulator",
            "Used to control and maintain food acidity or pH."
        ),

        "vegetable oil": (
            "🛢️ Vegetable Oil",
            "Plant-derived fat used for texture, cooking and flavour."
        ),

        "palm oil": (
            "🌴 Palm Oil",
            "Vegetable oil commonly used for texture and stability."
        ),

        "sunflower oil": (
            "🌻 Sunflower Oil",
            "Plant-based oil used as a fat source and for texture."
        ),

        "coconut oil": (
            "🥥 Coconut Oil",
            "Plant-based fat used for texture and flavour."
        ),

        "olive oil": (
            "🫒 Olive Oil",
            "Plant-derived oil commonly used as a source of dietary fat."
        ),

        "butter": (
            "🧈 Butter",
            "Dairy fat used to provide flavour and texture."
        ),

        "milk": (
            "🥛 Milk",
            "A dairy ingredient that can provide protein and flavour."
        ),

        "milk powder": (
            "🥛 Milk Powder",
            "Used to provide dairy solids, protein and flavour."
        ),

        "whey": (
            "🥛 Whey",
            "A milk-derived ingredient containing proteins and other milk components."
        ),

        "whey protein": (
            "🥛 Whey Protein",
            "A protein ingredient derived from milk."
        ),

        "casein": (
            "🥛 Casein",
            "A milk protein used for nutritional and functional properties."
        ),

        "lactose": (
            "🥛 Lactose",
            "The naturally occurring sugar found in milk and dairy products."
        ),

        "cream": (
            "🥛 Cream",
            "A dairy ingredient containing milk fat and used for flavour and texture."
        ),

        "cheese": (
            "🧀 Cheese",
            "A dairy product used for flavour, texture and protein."
        ),

        "curd": (
            "🥛 Curd",
            "A fermented dairy ingredient containing milk components."
        ),

        "ghee": (
            "🧈 Ghee",
            "Clarified dairy fat used for flavour and cooking."
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
            "Helps ingredients such as oil and water remain mixed."
        ),

        "sodium benzoate": (
            "🧪 Sodium Benzoate",
            "A preservative used to help slow microbial spoilage."
        ),

        "potassium sorbate": (
            "🧪 Potassium Sorbate",
            "A preservative used to help control mould and yeast growth."
        ),

        "preservative": (
            "🧪 Preservative",
            "Used to help slow spoilage and extend shelf life."
        ),

        "xanthan gum": (
            "⚗️ Xanthan Gum",
            "A thickener and stabilizer used to improve texture."
        ),

        "guar gum": (
            "⚗️ Guar Gum",
            "A thickening agent used to improve texture and consistency."
        ),

        "starch": (
            "🌽 Starch",
            "A carbohydrate commonly used for thickness and texture."
        ),

        "modified starch": (
            "🌽 Modified Starch",
            "Used to improve thickness, texture and stability."
        ),

        "stabilizer": (
            "⚗️ Stabilizer",
            "Helps maintain the texture and consistency of the product."
        ),

        "thickener": (
            "🥣 Thickener",
            "Used to increase thickness and improve texture."
        ),

        "msg": (
            "✨ MSG",
            "A flavour enhancer used to increase savoury or umami taste."
        ),

        "monosodium glutamate": (
            "✨ Monosodium Glutamate",
            "A flavour enhancer used to increase savoury or umami taste."
        ),

        "flavour": (
            "👃 Flavouring",
            "Added to provide or enhance flavour."
        ),

        "flavor": (
            "👃 Flavouring",
            "Added to provide or enhance flavour."
        ),

        "natural flavour": (
            "🌿 Natural Flavour",
            "Used to provide or enhance flavour using flavouring substances from natural sources."
        ),

        "natural flavor": (
            "🌿 Natural Flavour",
            "Used to provide or enhance flavour using flavouring substances from natural sources."
        ),

        "colour": (
            "🎨 Food Colour",
            "Used to provide or restore colour."
        ),

        "color": (
            "🎨 Food Colour",
            "Used to provide or restore colour."
        ),

        "wheat flour": (
            "🌾 Wheat Flour",
            "Used to provide structure and bulk in food products."
        ),

        "wheat": (
            "🌾 Wheat",
            "A cereal grain commonly used as a carbohydrate source."
        ),

        "whole wheat": (
            "🌾 Whole Wheat",
            "A whole-grain wheat ingredient containing the grain components."
        ),

        "semolina": (
            "🌾 Semolina",
            "A coarse flour usually made from durum wheat."
        ),

        "suji": (
            "🌾 Suji",
            "A coarse wheat-based flour commonly used in Indian foods."
        ),

        "sooji": (
            "🌾 Sooji",
            "A coarse wheat-based flour commonly used in Indian foods."
        ),

        "rava": (
            "🌾 Rava",
            "A coarse wheat-based flour commonly used in Indian foods."
        ),

        "rice": (
            "🍚 Rice",
            "A cereal grain and carbohydrate source."
        ),

        "corn": (
            "🌽 Corn",
            "A cereal grain used as a carbohydrate source."
        ),

        "barley": (
            "🌾 Barley",
            "A cereal grain containing carbohydrates and other nutrients."
        ),

        "oats": (
            "🌾 Oats",
            "A cereal grain that provides carbohydrates and dietary fibre."
        ),

        "almond": (
            "🥜 Almond",
            "A tree nut commonly used for flavour, texture and nutrients."
        ),

        "cashew": (
            "🥜 Cashew",
            "A tree nut used as a food ingredient and source of fat and protein."
        ),

        "walnut": (
            "🥜 Walnut",
            "A tree nut containing fats, protein and other nutrients."
        ),

        "pistachio": (
            "🥜 Pistachio",
            "A tree nut used for flavour and texture."
        ),

        "hazelnut": (
            "🥜 Hazelnut",
            "A tree nut commonly used for flavour and texture."
        ),

        "peanut": (
            "🥜 Peanut",
            "A legume commonly used as a source of protein and fat."
        ),

        "groundnut": (
            "🥜 Groundnut",
            "Another name for peanut, commonly used as a source of protein and fat."
        ),

        "soy": (
            "🫘 Soy",
            "A soybean-derived ingredient used as a protein or functional ingredient."
        ),

        "soya": (
            "🫘 Soya",
            "A soybean-derived ingredient used as a protein or functional ingredient."
        ),

        "soybean": (
            "🫘 Soybean",
            "A legume used as a source of plant protein and other nutrients."
        ),

        "sesame": (
            "🌱 Sesame",
            "A seed commonly used for flavour, texture and dietary fat."
        ),

        "mustard": (
            "🌿 Mustard",
            "A seed or spice used mainly for flavour."
        ),

        "egg": (
            "🥚 Egg",
            "An animal-derived ingredient that provides protein and functional properties."
        ),

        "albumin": (
            "🥚 Albumin",
            "A protein that can be derived from egg white."
        ),

        "cocoa": (
            "🍫 Cocoa",
            "A cocoa-derived ingredient used to provide chocolate flavour and colour."
        ),

        "cocoa powder": (
            "🍫 Cocoa Powder",
            "Ground cocoa solids used to provide chocolate flavour and colour."
        ),

        "chocolate": (
            "🍫 Chocolate",
            "A cocoa-based ingredient commonly combined with sugar and other ingredients."
        ),

        "vanilla": (
            "🌼 Vanilla",
            "A flavouring ingredient used to provide a characteristic sweet aroma and taste."
        ),

        "cinnamon": (
            "🌿 Cinnamon",
            "A spice used to provide aroma and flavour."
        ),

        "pepper": (
            "🌿 Pepper",
            "A spice used primarily to provide flavour and aroma."
        ),

        "turmeric": (
            "🌿 Turmeric",
            "A spice commonly used for flavour and natural yellow colour."
        ),

        "cumin": (
            "🌿 Cumin",
            "A spice used to provide aroma and flavour."
        ),

        "coriander": (
            "🌿 Coriander",
            "An herb or spice used to provide flavour and aroma."
        ),

        "chilli": (
            "🌶️ Chilli",
            "A spice or pepper ingredient used to provide heat and flavour."
        ),

        "ginger": (
            "🌿 Ginger",
            "A plant ingredient commonly used for flavour and aroma."
        ),

        "garlic": (
            "🧄 Garlic",
            "A plant ingredient commonly used to provide flavour and aroma."
        )
    }

    result = []

    already_added = set()

    # Longest ingredients are checked first
    keywords = sorted(
        ingredient_guide.keys(),
        key=len,
        reverse=True
    )

    for keyword in keywords:

        pattern = (
            r"(?<![a-z])"
            + re.escape(keyword)
            + r"(?![a-z])"
        )

        if re.search(pattern, text):

            name, explanation = ingredient_guide[keyword]

            if name not in already_added:

                result.append({

                    "name": name,

                    "explanation": explanation

                })

                already_added.add(name)

    return result


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

    # Diabetes
    if sugar > 15:

        cautions.append({

            "icon": "🩸",

            "title": "Diabetes Caution",

            "text":
                "This product contains a high amount of sugar per 100 g. People with diabetes may need to limit or carefully portion high-sugar foods.",

            "class": "danger"

        })

    # Hypertension
    if salt > 1.5:

        cautions.append({

            "icon": "❤️",

            "title": "Blood Pressure / Hypertension Caution",

            "text":
                "This product contains a relatively high amount of salt per 100 g. People managing high blood pressure may need to monitor their sodium and salt intake.",

            "class": "danger"

        })

    # Cardiovascular
    if fat > 17.5:

        cautions.append({

            "icon": "❤️",

            "title": "Cardiovascular Health Caution",

            "text":
                "This product is relatively high in total fat per 100 g. Overall dietary pattern and the type of fat are important when considering cardiovascular health.",

            "class": "caution"

        })

    # Allergens
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
                    + ". People with a relevant food allergy should check the package label and allergen declaration carefully.",

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

            "icon": "🛢️",

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

            "icon": "🔬",

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

    product["detected_allergens"] = detect_allergens(

        ingredients,

        declared_allergens,

        allergen_tags

    )

    product["ingredient_order"] = get_ingredient_order(
        ingredients
    )

    product["ingredient_categories"] = get_ingredient_categories(
        ingredients
    )

    product["decoded_ingredients"] = decode_ingredients(
        ingredients
    )

    product["smart_highlights"] = make_smart_highlights(
        product
    )

    product["disease_cautions"] = disease_cautions(
        product
    )

    product["score"] = calculate_score(
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
                    "ProductLens/1.0 student project"
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
    )

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

        "barcode": barcode,

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

    product = finalize_product(product)

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
    )

    if not foods:
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

            # Approximate conversion:
            # sodium mg -> salt g
            salt = value * 2.5 / 1000

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

    return finalize_product(product)


# =========================================================
# SEARCH PRODUCT
# =========================================================

def search_product(barcode):

    barcode = str(
        barcode
    ).strip()

    product = get_from_open_food_facts(
        barcode
    )

    if product:
        return product

    print(
        "Open Food Facts failed."
    )

    print(
        "Trying USDA..."
    )

    product = get_from_usda(
        barcode
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
            "Product was not found in Open Food Facts or USDA."

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

    if not barcode1.isdigit() or not barcode2.isdigit():

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

    if product1["score"]["value"] > product2["score"]["value"]:

        insights.append(
            product1["name"]
            + " has the higher ProductLens score."
        )

    elif product2["score"]["value"] > product1["score"]["value"]:

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
    print("🔬 PRODUCTLENS")
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