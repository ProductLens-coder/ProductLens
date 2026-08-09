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
# INGREDIENT INTELLIGENCE
# =========================================================

def decode_ingredients(ingredients):

    if not ingredients:
        return []

    text = str(ingredients).lower()

    ingredient_guide = {

        "sugar": (
            "🍬 Sugar",
            "Sweetener used to provide sweetness and contribute to the product's carbohydrate and sugar content.",
            "Why it is used: Provides sweetness and can also contribute to texture and browning."
        ),

        "glucose": (
            "🍬 Glucose",
            "A simple sugar used as a carbohydrate and sweetening ingredient.",
            "Why it is used: Adds sweetness and can contribute to texture and food processing."
        ),

        "dextrose": (
            "🍬 Dextrose",
            "A form of glucose commonly used as a sweetening and carbohydrate ingredient.",
            "Why it is used: Provides sweetness and can support texture and browning."
        ),

        "fructose": (
            "🍯 Fructose",
            "A simple sugar that provides sweetness.",
            "Why it is used: Provides sweetness and can contribute to the overall sugar profile."
        ),

        "sucrose": (
            "🍬 Sucrose",
            "Common table sugar composed of glucose and fructose.",
            "Why it is used: Primarily provides sweetness and can influence texture."
        ),

        "maltose": (
            "🍬 Maltose",
            "A sugar made from two glucose units.",
            "Why it is used: Provides sweetness and can contribute to flavour and browning."
        ),

        "syrup": (
            "🍯 Syrup",
            "A concentrated sweetening ingredient.",
            "Why it is used: Adds sweetness and can contribute to texture and moisture."
        ),

        "honey": (
            "🍯 Honey",
            "A naturally derived sweetener produced by bees.",
            "Why it is used: Provides sweetness, flavour and moisture."
        ),

        "salt": (
            "🧂 Salt",
            "A mineral ingredient mainly used for flavour.",
            "Why it is used: Enhances flavour and contributes sodium to the product."
        ),

        "sodium": (
            "🧂 Sodium",
            "A mineral that contributes to the sodium content of food.",
            "Why it is used: Can be present naturally or through sodium-containing ingredients and additives."
        ),

        "citric acid": (
            "🍋 Citric Acid",
            "An organic acid commonly used as an acidity regulator.",
            "Why it is used: Controls acidity, provides tartness and can support product stability."
        ),

        "acidity regulator": (
            "⚖️ Acidity Regulator",
            "An ingredient used to control the acidity or pH of a food.",
            "Why it is used: Helps maintain flavour, stability and processing characteristics."
        ),

        "vegetable oil": (
            "🛢️ Vegetable Oil",
            "Plant-derived oil used as a source of fat.",
            "Why it is used: Provides texture, mouthfeel and helps with cooking or processing."
        ),

        "palm oil": (
            "🌴 Palm Oil",
            "A vegetable oil derived from the fruit of oil palm trees.",
            "Why it is used: Provides texture, stability and helps give products a suitable mouthfeel."
        ),

        "palm fat": (
            "🌴 Palm Fat",
            "A palm-derived fat used in food formulations.",
            "Why it is used: Provides texture, structure and stability."
        ),

        "sunflower oil": (
            "🌻 Sunflower Oil",
            "A plant-based oil obtained from sunflower seeds.",
            "Why it is used: Provides fat and contributes to texture and cooking properties."
        ),

        "coconut oil": (
            "🥥 Coconut Oil",
            "A plant-derived oil from coconut.",
            "Why it is used: Provides fat, texture and characteristic flavour."
        ),

        "olive oil": (
            "🫒 Olive Oil",
            "A plant-derived oil obtained from olives.",
            "Why it is used: Provides dietary fat, flavour and texture."
        ),

        "canola oil": (
            "🌱 Canola Oil",
            "A plant-derived edible oil.",
            "Why it is used: Provides fat and contributes to texture and cooking properties."
        ),

        "butter": (
            "🧈 Butter",
            "A dairy fat used in food products.",
            "Why it is used: Provides flavour, richness and texture."
        ),

        "milk": (
            "🥛 Milk",
            "A dairy ingredient containing milk proteins and other milk components.",
            "Why it is used: Provides flavour, nutrients and functional properties."
        ),

        "milk powder": (
            "🥛 Milk Powder",
            "Dried milk containing concentrated milk solids.",
            "Why it is used: Provides dairy solids, protein, flavour and texture."
        ),

        "whey": (
            "🥛 Whey",
            "A milk-derived ingredient containing proteins and other milk components.",
            "Why it is used: Can provide protein and functional properties."
        ),

        "whey protein": (
            "🥛 Whey Protein",
            "A protein ingredient derived from milk.",
            "Why it is used: Adds protein and can contribute functional properties."
        ),

        "casein": (
            "🥛 Casein",
            "A major protein naturally found in milk.",
            "Why it is used: Provides protein and can contribute texture and stability."
        ),

        "lactose": (
            "🥛 Lactose",
            "The naturally occurring sugar found in milk.",
            "Why it is used: May be present as part of dairy ingredients and contributes sweetness and milk solids."
        ),

        "cream": (
            "🥛 Cream",
            "A dairy ingredient containing milk fat.",
            "Why it is used: Provides richness, flavour and creamy texture."
        ),

        "cheese": (
            "🧀 Cheese",
            "A dairy ingredient containing milk components.",
            "Why it is used: Provides flavour, texture and protein."
        ),

        "curd": (
            "🥛 Curd",
            "A fermented dairy ingredient.",
            "Why it is used: Provides dairy solids, flavour and texture."
        ),

        "ghee": (
            "🧈 Ghee",
            "Clarified dairy fat.",
            "Why it is used: Provides fat, flavour and cooking properties."
        ),

        "lecithin": (
            "🔄 Lecithin",
            "An emulsifier that helps ingredients such as oil and water remain mixed.",
            "Why it is used: Improves consistency and helps maintain a uniform product."
        ),

        "soy lecithin": (
            "🫘 Soy Lecithin",
            "A soy-derived emulsifier.",
            "Why it is used: Helps ingredients remain evenly mixed and can improve texture."
        ),

        "emulsifier": (
            "🔄 Emulsifier",
            "An ingredient that helps normally difficult-to-mix ingredients remain combined.",
            "Why it is used: Helps maintain consistency and texture."
        ),

        "sodium benzoate": (
            "🧪 Sodium Benzoate",
            "A preservative used in many food formulations.",
            "Why it is used: Helps slow microbial spoilage and extend shelf stability."
        ),

        "potassium sorbate": (
            "🧪 Potassium Sorbate",
            "A preservative commonly used to control mould and yeast.",
            "Why it is used: Helps protect the product from microbial spoilage."
        ),

        "preservative": (
            "🧪 Preservative",
            "An ingredient used to slow deterioration caused by microorganisms or other processes.",
            "Why it is used: Helps maintain product quality and extend shelf life."
        ),

        "xanthan gum": (
            "⚗️ Xanthan Gum",
            "A polysaccharide commonly used as a thickener and stabilizer.",
            "Why it is used: Improves thickness, texture and stability."
        ),

        "guar gum": (
            "⚗️ Guar Gum",
            "A plant-derived thickening agent.",
            "Why it is used: Improves thickness, consistency and texture."
        ),

        "starch": (
            "🌽 Starch",
            "A carbohydrate commonly used in food formulations.",
            "Why it is used: Can provide thickness, structure and texture."
        ),

        "modified starch": (
            "🌽 Modified Starch",
            "Starch that has been processed to provide specific functional properties.",
            "Why it is used: Helps control thickness, texture and stability."
        ),

        "stabilizer": (
            "⚗️ Stabilizer",
            "An ingredient used to help maintain the physical properties of a food.",
            "Why it is used: Helps maintain texture, consistency and stability during storage."
        ),

        "thickener": (
            "🥣 Thickener",
            "An ingredient used to increase the thickness of a food.",
            "Why it is used: Improves consistency and mouthfeel."
        ),

        "msg": (
            "✨ MSG",
            "Monosodium glutamate, a flavour enhancer.",
            "Why it is used: Enhances savoury or umami flavour."
        ),

        "monosodium glutamate": (
            "✨ Monosodium Glutamate",
            "A flavour-enhancing ingredient.",
            "Why it is used: Enhances savoury or umami taste."
        ),

        "flavour": (
            "👃 Flavouring",
            "An ingredient or mixture used to provide or enhance flavour.",
            "Why it is used: Gives the product its intended taste or aroma."
        ),

        "flavor": (
            "👃 Flavouring",
            "An ingredient or mixture used to provide or enhance flavour.",
            "Why it is used: Gives the product its intended taste or aroma."
        ),

        "natural flavour": (
            "🌿 Natural Flavour",
            "A flavouring ingredient described as being derived from natural sources.",
            "Why it is used: Provides or enhances the characteristic flavour of the product."
        ),

        "natural flavor": (
            "🌿 Natural Flavour",
            "A flavouring ingredient described as being derived from natural sources.",
            "Why it is used: Provides or enhances the characteristic flavour of the product."
        ),

        "colour": (
            "🎨 Food Colour",
            "A colouring ingredient used to give or restore colour.",
            "Why it is used: Improves or restores the visual appearance of the food."
        ),

        "color": (
            "🎨 Food Colour",
            "A colouring ingredient used to give or restore colour.",
            "Why it is used: Improves or restores the visual appearance of the food."
        ),

        "wheat flour": (
            "🌾 Wheat Flour",
            "Flour made from wheat grains.",
            "Why it is used: Provides structure, bulk and carbohydrates."
        ),

        "wheat": (
            "🌾 Wheat",
            "A cereal grain commonly used as a carbohydrate source.",
            "Why it is used: Provides structure, bulk and carbohydrates in many foods."
        ),

        "whole wheat": (
            "🌾 Whole Wheat",
            "A wheat ingredient containing the grain's main components.",
            "Why it is used: Provides grain structure, carbohydrates and dietary fibre."
        ),

        "semolina": (
            "🌾 Semolina",
            "A coarse flour usually made from durum wheat.",
            "Why it is used: Provides structure, texture and carbohydrates."
        ),

        "suji": (
            "🌾 Suji",
            "A coarse wheat-based flour commonly used in Indian foods.",
            "Why it is used: Provides bulk, structure and carbohydrates."
        ),

        "sooji": (
            "🌾 Sooji",
            "A coarse wheat-based flour commonly used in Indian foods.",
            "Why it is used: Provides bulk, structure and carbohydrates."
        ),

        "rava": (
            "🌾 Rava",
            "A coarse wheat-based flour commonly used in Indian foods.",
            "Why it is used: Provides bulk, structure and carbohydrates."
        ),

        "rice": (
            "🍚 Rice",
            "A cereal grain and carbohydrate source.",
            "Why it is used: Provides bulk, texture and carbohydrates."
        ),

        "corn": (
            "🌽 Corn",
            "A cereal grain used as a carbohydrate source.",
            "Why it is used: Provides carbohydrates, structure or texture depending on the formulation."
        ),

        "barley": (
            "🌾 Barley",
            "A cereal grain containing carbohydrates and dietary fibre.",
            "Why it is used: Provides grain-based structure, flavour or nutrients."
        ),

        "oats": (
            "🌾 Oats",
            "A cereal grain that provides carbohydrates and dietary fibre.",
            "Why it is used: Provides texture, bulk and grain nutrients."
        ),

        "almond": (
            "🥜 Almond",
            "A tree nut commonly used for flavour and texture.",
            "Why it is used: Provides characteristic flavour, texture, fat and protein."
        ),

        "cashew": (
            "🥜 Cashew",
            "A tree nut used as a food ingredient.",
            "Why it is used: Provides flavour, creamy texture, fat and protein."
        ),

        "walnut": (
            "🥜 Walnut",
            "A tree nut containing fat, protein and other nutrients.",
            "Why it is used: Provides flavour and texture."
        ),

        "pistachio": (
            "🥜 Pistachio",
            "A tree nut used as a food ingredient.",
            "Why it is used: Provides flavour, colour and texture."
        ),

        "hazelnut": (
            "🥜 Hazelnut",
            "A tree nut commonly used for flavour and texture.",
            "Why it is used: Provides characteristic nutty flavour and texture."
        ),

        "peanut": (
            "🥜 Peanut",
            "A legume commonly used as a source of protein and fat.",
            "Why it is used: Provides flavour, protein, fat and texture."
        ),

        "groundnut": (
            "🥜 Groundnut",
            "Another name for peanut.",
            "Why it is used: Provides protein, fat, flavour and texture."
        ),

        "soy": (
            "🫘 Soy",
            "A soybean-derived ingredient.",
            "Why it is used: Can provide protein or functional properties such as emulsification."
        ),

        "soya": (
            "🫘 Soya",
            "A soybean-derived ingredient.",
            "Why it is used: Can provide protein or functional properties."
        ),

        "soybean": (
            "🫘 Soybean",
            "A legume used as a source of plant protein and other nutrients.",
            "Why it is used: Provides protein and can be used for functional properties."
        ),

        "sesame": (
            "🌱 Sesame",
            "A seed commonly used for flavour and texture.",
            "Why it is used: Provides characteristic flavour, texture and dietary fat."
        ),

        "mustard": (
            "🌿 Mustard",
            "A seed or spice used mainly for flavour.",
            "Why it is used: Provides characteristic aroma and taste."
        ),

        "egg": (
            "🥚 Egg",
            "An animal-derived ingredient that provides protein and functional properties.",
            "Why it is used: Can provide structure, binding, texture and protein."
        ),

        "albumin": (
            "🥚 Albumin",
            "A protein that can be derived from egg white.",
            "Why it is used: Provides protein and can contribute binding or foaming properties."
        ),

        "cocoa": (
            "🍫 Cocoa",
            "A cocoa-derived ingredient used for chocolate flavour and colour.",
            "Why it is used: Provides characteristic chocolate flavour and colour."
        ),

        "cocoa powder": (
            "🍫 Cocoa Powder",
            "Ground cocoa solids.",
            "Why it is used: Provides chocolate flavour, colour and cocoa solids."
        ),

        "chocolate": (
            "🍫 Chocolate",
            "A cocoa-based ingredient commonly combined with sugar and other ingredients.",
            "Why it is used: Provides chocolate flavour and contributes to texture."
        ),

        "vanilla": (
            "🌼 Vanilla",
            "A flavouring ingredient with a characteristic sweet aroma.",
            "Why it is used: Provides vanilla aroma and flavour."
        ),

        "cinnamon": (
            "🌿 Cinnamon",
            "A spice used for aroma and flavour.",
            "Why it is used: Provides characteristic warm flavour and aroma."
        ),

        "pepper": (
            "🌿 Pepper",
            "A spice used primarily for flavour and aroma.",
            "Why it is used: Provides characteristic spicy flavour."
        ),

        "turmeric": (
            "🌿 Turmeric",
            "A spice commonly used for flavour and natural yellow colour.",
            "Why it is used: Provides flavour and colour."
        ),

        "cumin": (
            "🌿 Cumin",
            "A spice used to provide aroma and flavour.",
            "Why it is used: Provides characteristic aroma and taste."
        ),

        "coriander": (
            "🌿 Coriander",
            "An herb or spice used to provide flavour and aroma.",
            "Why it is used: Adds characteristic flavour and aroma."
        ),

        "chilli": (
            "🌶️ Chilli",
            "A pepper ingredient used to provide heat and flavour.",
            "Why it is used: Provides spiciness and flavour."
        ),

        "ginger": (
            "🌿 Ginger",
            "A plant ingredient commonly used for flavour and aroma.",
            "Why it is used: Provides characteristic flavour and aroma."
        ),

        "garlic": (
            "🧄 Garlic",
            "A plant ingredient commonly used to provide flavour and aroma.",
            "Why it is used: Provides characteristic savoury flavour and aroma."
        )
    }

    result = []

    already_added = set()

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

            name, explanation, purpose = ingredient_guide[keyword]

            if name not in already_added:

                result.append({

                    "name": name,

                    "explanation": explanation,

                    "purpose": purpose

                })

                already_added.add(name)

    return result


# =========================================================
# INGREDIENT-SPECIFIC HEALTH CAUTIONS
# =========================================================

def ingredient_health_cautions(product):

    cautions = []

    ingredients = str(
        product.get("ingredients", "")
    ).lower()

    def contains(keyword):

        return re.search(
            r"(?<![a-z])"
            + re.escape(keyword)
            + r"(?![a-z])",
            ingredients
        ) is not None

    # Palm oil
    if contains("palm oil") or contains("palm fat"):

        cautions.append({

            "icon": "🌴",

            "title": "Palm Oil Detected",

            "text":
                "Palm oil is listed as an ingredient. Palm oil contributes saturated fat, so the product's saturated-fat content and overall portion should be considered when evaluating its nutritional profile.",

            "class": "caution"

        })

    # Hydrogenated fats
    if (
        contains("hydrogenated oil")
        or contains("hydrogenated fat")
        or contains("partially hydrogenated")
    ):

        cautions.append({

            "icon": "⚠️",

            "title": "Hydrogenated Fat Detected",

            "text":
                "A hydrogenated fat ingredient is listed. Check the nutrition label for saturated fat and any available trans-fat information.",

            "class": "caution"

        })

    # Added sugar ingredients
    sugar_keywords = [
        "sugar",
        "glucose",
        "dextrose",
        "fructose",
        "sucrose",
        "maltose",
        "syrup"
    ]

    sugar_detected = any(
        contains(keyword)
        for keyword in sugar_keywords
    )

    if sugar_detected:

        sugar_value = safe_number(
            product.get("sugar")
        )

        if sugar_value > 15:

            cautions.append({

                "icon": "🍬",

                "title": "Added Sugar Ingredients Detected",

                "text":
                    "The ingredient list contains one or more sugar-based ingredients, and the product also has a relatively high sugar value per 100 g.",

                "class": "caution"

            })

    # Preservatives
    preservative_keywords = [
        "sodium benzoate",
        "potassium sorbate",
        "preservative"
    ]

    if any(
        contains(keyword)
        for keyword in preservative_keywords
    ):

        cautions.append({

            "icon": "🧪",

            "title": "Preservative Detected",

            "text":
                "A preservative is listed. Preservatives are commonly used to slow spoilage and help maintain shelf stability.",

            "class": "caution"

        })

    return cautions


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

    # Ingredient-specific cautions
    ingredient_cautions = ingredient_health_cautions(
        product
    )

    cautions.extend(
        ingredient_cautions
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
    ) or raw.get(
        "ingredients_text_en",
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
        nutrition.get(
            "sugars",
            0
        )
    )

    fat = nutrition.get(
        "fat_100g",
        nutrition.get(
            "fat",
            0
        )
    )

    protein = nutrition.get(
        "proteins_100g",
        nutrition.get(
            "proteins",
            0
        )
    )

    salt = nutrition.get(
        "salt_100g",
        nutrition.get(
            "salt",
            0
        )
    )

    # Product-name fallback hierarchy
    product_name = (
        raw.get("product_name")
        or raw.get("product_name_en")
        or raw.get("product_name_in")
        or raw.get("generic_name")
        or raw.get("generic_name_en")
        or ""
    )

    brands = (
        raw.get("brands")
        or raw.get("brand_owner")
        or ""
    )

    if not product_name:

        if brands:
            product_name = brands

        else:
            product_name = "Unknown Product"

    image = (
        raw.get("image_front_url")
        or raw.get("image_url")
        or raw.get("image_front_small_url")
        or ""
    )

    product = {

        "name": product_name,

        "brands": brands,

        "barcode": barcode,

        "image": image,

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

            salt = value * 2.5 / 1000

    product_name = (
        food.get("description")
        or food.get("lowercaseDescription")
        or food.get("brandName")
        or "Unknown Product"
    )

    brand = (
        food.get("brandOwner")
        or food.get("brandName")
        or ""
    )

    product = {

        "name": product_name,

        "brands": brand,

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
